import pytest

from engine import Kitten2Engine
from voices import VoiceStore

WAV = b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 32  # passes the store's header check; the fake model never decodes it


@pytest.fixture(autouse=True)
def _tmp_files(tmp_path, monkeypatch):
    """Keeps tokens.json, settings.json and the voices out of the repo, and a saved setting from leaking into the next test."""
    monkeypatch.setenv("SERVICE_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("SERVICE_VOICES_DIR", str(tmp_path / "voices"))


BUILTIN = ["Bella", "Bruno", "Kiki"]


class FakeSpeaker:
    """Stands in for the loaded model: 0.1 s of audio per call (4800 bytes at 24 kHz), two pieces per stream, and a record of every call."""

    rate = 24000
    names = BUILTIN

    def __init__(self):
        self.calls = []
        self.fail = False

    def _record(self, text, voice, reference, seed, temperature, preset, normalize, max_new_tokens, threads):
        if not text.strip(" ."):
            raise ValueError("no text to speak")
        self.calls.append({"text": text, "voice": voice, "reference": reference, "seed": seed, "temperature": temperature,
                           "preset": preset, "normalize": normalize, "max_new_tokens": max_new_tokens, "threads": threads,
                           "reference_bytes": reference[0].read_bytes() if reference else None})  # read now: a one-call clip is deleted later
        if self.fail:
            raise RuntimeError("model crashed")

    def speak(self, *args):
        self._record(*args)
        return b"\1\0" * (self.rate // 10)

    def pieces(self, *args):
        self._record(*args)
        for _ in range(2):
            yield b"\1\0" * (self.rate // 10)


def make_engine(voices=(), **options):
    """An engine whose loader builds a FakeSpeaker; `engine.loads` lists the (revision, device, weights, decoder) it was asked for."""
    loads, made = [], []

    def loader(model_id, revision, device, weights, decoder):
        loads.append((revision, device, weights, decoder))
        made.append(FakeSpeaker())
        return made[-1]

    options.setdefault("loader", loader)
    options.setdefault("names", lambda *_: BUILTIN)
    engine = Kitten2Engine(**options)
    for name in voices:
        engine.store.put(name, WAV, f"Transcript of {name}.")
    engine.loads, engine.made = loads, made
    return engine
