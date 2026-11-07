"""KittenTTS 2 (1.7B speech language model, in-context voice cloning) run in this process, on the CPU by default.

The `kittenml` package does the work: text -> S3 codec tokens (a ternary Qwen3-style LM) -> 24 kHz audio. The Hub
revision is pinned and downloaded here, then the package is pointed at the local folder, so nothing moves on its own.
A voice is a built-in one (115 in the repository) or a reference clip with its transcript (see voices.py). One
generation runs at a time per replica; scale with replicas.

shortcut: the update check only reports a change when the `model_revision` setting moves, and a non-streamed call joins
the model's own chunks (about 380 characters each) while a stream sends them untrimmed, one per chunk, not per sentence.
`seed` seeds torch globally, which is safe only because one generation runs at a time."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import threading
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator

from audio import wav_bytes
from voices import VoiceStore

_log = logging.getLogger(__name__)

MODEL_ID = "KittenML/kitten-tts-2"
DEFAULT_REVISION = "c93cb7c271baa51d9ae8204d5277988906f235a2"
DEFAULT_VOICE = "Bruno"  # the repository's own default (config.json)
SAMPLE_RATE = 24000
PRESETS = ("stable", "expressive")  # config.json `decode_presets`


class EngineError(RuntimeError):
    """The text could not be spoken. `status` is the HTTP status the service maps it to."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _pcm(wave: Any) -> bytes:
    import numpy

    return (numpy.clip(wave, -1.0, 1.0) * 32767).astype("<i2").tobytes()


class Speaker:
    """A loaded KittenTTS2 that turns text into 16-bit mono PCM."""

    def __init__(self, model: Any) -> None:
        self._model = model
        self.rate = int(model.sample_rate)
        self.names: list[str] = list(model.available_voices)

    def speak(self, text: str, voice: str, reference: tuple[Path, str] | None, seed: int, temperature: float | None,
              preset: str, normalize: bool, max_new_tokens: int, threads: int | None) -> bytes:
        """The whole text, chunks joined with the model's own seam handling."""
        return _pcm(self._model.generate(text, **self._args(voice, reference, seed, temperature, preset, normalize, max_new_tokens, threads)))

    def pieces(self, text: str, voice: str, reference: tuple[Path, str] | None, seed: int, temperature: float | None,
               preset: str, normalize: bool, max_new_tokens: int, threads: int | None) -> Iterator[bytes]:
        """One piece of audio per chunk of text, made as the caller asks for the next one."""
        for wave in self._model.generate_stream(text, **self._args(voice, reference, seed, temperature, preset, normalize, max_new_tokens, threads)):
            yield _pcm(wave)

    @staticmethod
    def _args(voice: str, reference: tuple[Path, str] | None, seed: int, temperature: float | None, preset: str,
              normalize: bool, max_new_tokens: int, threads: int | None) -> dict[str, Any]:
        import torch

        if threads:
            torch.set_num_threads(threads)
        args: dict[str, Any] = {"preset": preset, "normalize": normalize, "max_new_tokens": max_new_tokens,
                                "temperature": temperature, "advanced": {"seed": seed % 2**63}}
        if reference is not None:
            args.update(reference=str(reference[0]), reference_text=reference[1])  # the transcript is given, so Whisper is never loaded
        else:
            args["voice"] = voice
        return args


def _snapshot(model_id: str, revision: str, weights: str, decoder: str, local_only: bool = False) -> Path:
    """The files this setup needs, from the pinned revision. `_kitten2_files` is the package's own list of them
    (private, but it is what keeps the download at about 1 GB instead of 8)."""
    from huggingface_hub import hf_hub_download, snapshot_download
    from kittenml.get_model import _kitten2_files

    config = json.loads(Path(hf_hub_download(model_id, "config.json", revision=revision, local_files_only=local_only)).read_text("utf-8"))
    return Path(snapshot_download(model_id, revision=revision, allow_patterns=_kitten2_files(config, decoder, weights),
                                  local_files_only=local_only))


def load(model_id: str, revision: str, device: str, weights: str, decoder: str) -> Speaker:
    """Downloads (first time) and loads the model. Blocking: run it in a thread."""
    import torch
    from kittenml import KittenTTS

    if device.startswith("cuda") and not torch.cuda.is_available():
        raise EngineError("The device is cuda but no GPU is visible here. Set the device to cpu.", 503)
    try:
        model = KittenTTS(str(_snapshot(model_id, revision, weights, decoder)), device=device, weights=weights, decoder=decoder)
    except UnicodeError:
        raise  # a real fault (on Windows: run with PYTHONUTF8=1), not a bad setting
    except ValueError as error:  # an unknown weights or decoder name
        raise EngineError(str(error), 503) from None
    speaker = Speaker(model)
    speaker.speak("Warm up.", DEFAULT_VOICE, None, 0, None, "stable", True, 64, None)  # the first call builds caches
    return speaker


def _remote_sha(model_id: str, revision: str) -> str:
    from huggingface_hub import HfApi

    return HfApi().model_info(model_id, revision=revision, token=False).sha


def _cached_sha(model_id: str, revision: str) -> str | None:
    from huggingface_hub import snapshot_download

    try:
        return Path(snapshot_download(model_id, revision=revision, local_files_only=True, allow_patterns=["config.json"])).name
    except Exception:  # not downloaded yet
        return None


def _download(model_id: str, revision: str, weights: str, decoder: str) -> None:
    _snapshot(model_id, revision, weights, decoder)


def default_marker() -> Path:
    """File in the shared models volume whose content changes when one replica downloads new weights."""
    configured = os.environ.get("KITTEN2_WEIGHTS_MARKER")
    return Path(configured) if configured else Path(os.environ.get("HF_HOME") or "~/.cache/huggingface").expanduser() / ".kitten2-weights-version"


def builtin_names(model_id: str, revision: str, weights: str, decoder: str) -> list[str]:
    """The built-in voices from the downloaded `voices/voices.json`, or [] before the first download."""
    try:
        return sorted(json.loads((_snapshot(model_id, revision, weights, decoder, local_only=True) / "voices" / "voices.json").read_text("utf-8")))
    except Exception:
        return []


class Kitten2Engine:
    """The `loader`, `remote_sha`, `cached_sha`, `download` and `names` callables are injectable for tests."""

    def __init__(self, revision: str = DEFAULT_REVISION, device: str = "cpu", weights: str = "packed", decoder: str = "default",
                 max_new_tokens: int = 1000, *, store: VoiceStore | None = None, marker: Path | None = None,
                 loader: Callable[[str, str, str, str, str], Speaker] = load,
                 remote_sha: Callable[[str, str], str] = _remote_sha, cached_sha: Callable[[str, str], str | None] = _cached_sha,
                 download: Callable[[str, str, str, str], None] = _download,
                 names: Callable[[str, str, str, str], list[str]] = builtin_names) -> None:
        self.model = MODEL_ID
        self.revision, self.device, self.weights, self.decoder, self.max_new_tokens = revision, device, weights, decoder, max_new_tokens
        self.store = store or VoiceStore()
        self._threads: int | None = None
        self._marker = marker
        self._seen = self._read_marker()
        self._loader = loader
        self._remote_sha_of, self._cached_sha_of, self._download_of, self._names_of = remote_sha, cached_sha, download, names
        self._loaded: Speaker | None = None
        self._load_lock = threading.Lock()
        self._gate = asyncio.Semaphore(1)
        self.generation = 0  # part of the answer cache key; changes whenever the loaded model is dropped

    @property
    def builtin(self) -> list[str]:
        """Built-in voices: from the loaded model, else from the downloaded files, else just the default."""
        return list(self._loaded.names) if self._loaded else self._names_of(self.model, self.revision, self.weights, self.decoder) or [DEFAULT_VOICE]

    @property
    def voices(self) -> list[str]:
        return sorted({*self.builtin, *self.store.names()})

    @property
    def default_voice(self) -> str:
        return DEFAULT_VOICE

    @property
    def num_thread(self) -> int | None:
        return self._threads

    @num_thread.setter
    def num_thread(self, count: int) -> None:
        self._threads = count  # torch reads it on every call; the model stays loaded

    @property
    def ready(self) -> bool:
        return self._loaded is not None

    async def close(self) -> None:
        self._loaded = None

    async def warm(self) -> None:
        """Load the model now so the first request does not pay for it."""
        await asyncio.to_thread(self._speaker)

    def _speaker(self) -> Speaker:
        with self._load_lock:
            if self._loaded is None:
                self._loaded = self._loader(self.model, self.revision, self.device, self.weights, self.decoder)
            return self._loaded

    def _voice(self, voice: str | None) -> tuple[str, tuple[Path, str] | None]:
        """The voice name and its clone reference (None for a built-in voice). A cloned voice shadows nothing: the
        admin route refuses a name a built-in voice already has."""
        name = voice or DEFAULT_VOICE
        reference = self.store.get(name)
        if reference is not None:
            return name, reference
        if name not in self.builtin:
            raise EngineError(f"Voice {name!r} is not served here; GET /v1/voices lists them", 404)
        return name, None

    @staticmethod
    def _check(preset: str | None) -> str:
        if preset is not None and preset not in PRESETS:
            raise EngineError(f"preset must be one of {', '.join(PRESETS)}", 422)
        return preset or PRESETS[0]

    async def synthesize(self, text: str, voice: str | None, seed: int | None, temperature: float | None,
                         preset: str | None = None, normalize: bool = True) -> dict[str, Any]:
        name, reference = self._voice(voice)
        preset = self._check(preset)
        seed = random.getrandbits(62) if seed is None else seed
        async with self._gate:
            loaded = await asyncio.to_thread(self._speaker)
            try:
                pcm = await asyncio.to_thread(loaded.speak, text, name, reference, seed, temperature, preset, normalize,
                                              self.max_new_tokens, self._threads)
            except ValueError as error:  # "no text to speak", "no speech found in the reference clip"
                raise EngineError(str(error), 422) from None
            except RuntimeError as error:  # "the model produced no audio tokens"
                raise EngineError(str(error), 422) from None
        return {"wav": wav_bytes(pcm, loaded.rate), "seconds": len(pcm) / 2 / loaded.rate, "voice": name}

    async def stream(self, text: str, voice: str | None, seed: int | None, temperature: float | None, preset: str | None = None,
                     normalize: bool = True) -> AsyncIterator[tuple[int, bytes]]:
        """The audio as it is made: (sample rate, 16-bit mono PCM) per chunk of text. Holds the generation slot until
        the last piece, or until the caller closes the iterator."""
        name, reference = self._voice(voice)
        preset = self._check(preset)
        seed = random.getrandbits(62) if seed is None else seed
        async with self._gate:
            loaded = await asyncio.to_thread(self._speaker)
            pieces = loaded.pieces(text, name, reference, seed, temperature, preset, normalize, self.max_new_tokens, self._threads)
            while True:
                try:
                    piece = await asyncio.to_thread(next, pieces, None)
                except ValueError as error:
                    raise EngineError(str(error), 422) from None
                if piece is None:
                    break
                yield loaded.rate, piece

    # Updates: the Hub revision of the model files, shared by all replicas through one models volume.

    async def cached_sha(self) -> str | None:
        return await asyncio.to_thread(self._cached_sha_of, self.model, self.revision)

    async def remote_sha(self) -> str:
        return await asyncio.to_thread(self._remote_sha_of, self.model, self.revision)

    async def pull(self) -> None:
        await asyncio.to_thread(self._download_of, self.model, self.revision, self.weights, self.decoder)

    async def unload(self) -> None:
        """Forget the loaded model here and tell the other replicas to do the same; the next call loads the new files."""
        if self._marker is not None:
            self._marker.parent.mkdir(parents=True, exist_ok=True)
            self._seen = uuid.uuid4().hex
            self._marker.write_text(self._seen, "utf-8")
        self._forget()

    def sync(self) -> None:
        """Called every second: drop the loaded model when another replica downloaded new files."""
        current = self._read_marker()
        if current != self._seen:
            self._seen = current
            self._forget()

    def _forget(self) -> None:
        with self._load_lock:
            self._loaded = None
            self.generation += 1  # kept answers are from the old files

    def _read_marker(self) -> str | None:
        try:
            return self._marker.read_text("utf-8") if self._marker else None
        except OSError:
            return None
