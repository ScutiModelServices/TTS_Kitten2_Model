# TTS_Kitten2_Model

[KittenTTS 2](https://huggingface.co/KittenML/kitten-tts-2) text to speech (1.7B parameters, 115 built-in voices in 16 languages, zero-shot voice cloning), served over HTTP so projects send text instead of loading a model themselves. It has the same admin page, tokens, rate limits, metrics, settings and update checks as the other model services (`TTS_Paradee_Model`, `TTS_Piper_Model` and `TTS_Audio8_Model` have the same API shape).

The model runs in this process on the **CPU** by default (torch, the `kittenml` package). It is heavy for a CPU: see *Limits worth knowing*. The weights are under the [Stellon Labs Community License](https://huggingface.co/KittenML/kitten-tts-2) (free for research, non-commercial and limited commercial use; a separate licence is needed above USD 1M annual revenue or total funding), not Apache 2.0.

## API

| Call | Purpose |
|---|---|
| `POST /v1/speak` | `{"text", "voice", "seed", "temperature", "preset", "normalize", "stream", "reference_audio_base64", "reference_text"}` returns a WAV file (`audio/wav`, 16-bit mono, 24 kHz). Headers: `X-Audio-Seconds`, `X-Duration-Ms`, `X-Voice`, `X-Seed`, `X-Cache` (`hit` when the kept answer was sent). |
| `GET /v1/voices` | `{"voices", "default"}` (built-in and cloned); with a token limited to voices, only those. |
| `PUT /admin/voices/{name}` | Admin password. `{"audio_base64", "transcript"}`: a WAV clip (at most 10 MB; the model wants 5 to 30 seconds of one speaker) and exactly what it says. Adds or replaces a cloned voice. A built-in voice name gets 409. |
| `DELETE /admin/voices/{name}` | Admin password. Removes a cloned voice. |
| `GET /health` | `{"status": "ok", "model", "ready", "num_thread", "device", "voices"}`; `ready` is true once the model is loaded. No token needed. |

`text` is 1 to 5000 characters. Other fields are refused with 422. The model splits long text itself into chunks of about 380 characters and joins the audio.

**One-call voice (nothing kept).** Instead of a `voice`, send `reference_audio_base64` (a WAV, up to 10 MB) and `reference_text` (exactly what it says). The clip is written to a temp file only while the speech is made and deleted when the call ends, fails or the client disconnects, streams included. It is never added to the voices volume, and the answer is never cached, even with a `seed`. `X-Voice` is `custom`. Both fields are required together; a `voice` beside them gives 422, and a token limited to certain voices gets 403. The audio may also be a `data:audio/wav;base64,...` URL, which is what the Try it panel sends (its **One-call voice clip** and **What the clip says** fields).

**Voices.** The default is `Bruno`. Names such as `Bella`, `Jasper`, `Luna`, `Bruno`, `Rosie`, `Hugo`, `Kiki` and `Leo` are English; a voice named for a language (`SpanishAbuela`, `JapaneseTrainConductor`, `German`) is how you reach that language, since the voice carries the accent. A cloned voice is a reference clip and its transcript; the transcript is always given, so the model's Whisper step is never loaded. A token's *projects* list on the admin page limits the voices it may use.

**Preset, temperature, normalize.** `preset` is `stable` (default) or `expressive` (anything else is 422). `temperature` (0.1 to 1.5) overrides the preset's own (0.8 and 0.9). `normalize` (default true) expands written forms such as `$12.50`; send `false` for non-English text, because the normalizer is English-tuned. With the `expressive` preset the text can carry a leading `[joyful]`-style emotion tag, inline `<laugh>`-style events and `(((emphasis)))` spans (beta upstream; twenty tags are recognised, anything else is spoken as text).

**Seed.** `seed` makes the same text, voice, preset, temperature and normalize give the same speech on the same machine and model revision (the reply's `X-Seed` tells which seed a seed-less call got). It seeds torch globally, which is safe because one generation runs at a time per replica.

**Streaming.** With `"stream": true` the WAV is sent chunk by chunk while the rest is still being made. A chunk is up to about 380 characters, so on a CPU the first audio can still take many seconds. The header cannot know the length yet: its size fields are `0xFFFFFFFF` (read "until the connection ends"), and there is no `X-Audio-Seconds`. Players and `ffmpeg` read it; Python's `wave` module does not. Errors known early (unknown voice, no speech in the text, model not loaded) are normal HTTP errors; one after the first chunk cuts the stream off.

**Cache.** The *Answers kept per replica* setting (`SERVICE_CACHE_SIZE`, default 32, 0 = off) keeps the last answers **for calls with a `seed`**. An answer over 1 MB is not kept. It is per replica and in memory, and emptied when the model is reloaded. Replacing a cloned voice does not empty it: use a new voice name.

## Admin page

`/admin/` (password `SERVICE_ADMIN_PASSWORD`): tokens with voice scope, rate limit and expiry, usage numbers, CPU threads, the Settings card (update check hours, in-flight cap, answers kept, model revision, device, weight variant, decoder, token limit, load at start), and the Updates card. The Cloned voices card adds, lists and deletes cloned voices (shown because the service has the `voice-cloning` tag); the voice calls above do the same (see `docs/guide-web-ui.md`). `/metrics` (admin password) is Prometheus text per token.

## Run

Startup, warm-up and inference never download weights. With no downloaded weights, `/health` answers `ready: false` and speech calls return 503. Open `/admin/` → **Updates** → **Download** before the first call; see the [admin guide](docs/guide-web-ui.md#updates-and-first-download) for the curl alternative.

```bash
docker compose up -d --build        # http://<host>:29323
python tools/bench.py http://127.0.0.1:29323 --save out
```

Without Docker: `run.bat` (uv, listens on `127.0.0.1:29323`, sets `PYTHONUTF8=1`). Startup loads downloaded weights only; open `/admin/`, then **Updates → Download** before the first call. See `deployment.md`.

## Tests

```bash
uv sync
uv run pytest
```

The tests use a fake model. Before relying on a new revision, run the real model once and listen to the result (`tools/bench.py` times it).

## Limits worth knowing

- **Heavy on a CPU.** Measured on a Ryzen 7 7445HS (6 physical cores, 15 GB RAM), torch default threads, bf16, `packed` weights: 5.7 GB resident after loading, 6.1 GB peak, under a minute to load from a warm disk cache. Speech took about 9 s for 1.1 s of audio, 44 s for 6.8 s and 65 s for 10 s (0.1 to 0.2 times real time). A small CPU will be slower and may not fit the memory. The model card names a llama.cpp fork (`kitten-tts-2-cpp`, GGUF files in the repository's `cpp/` folder) as the fastest CPU route; this service does not use it. Not measured: a GPU (`device=cuda` needs a host GPU and a CUDA build of torch; compose reserves none), the Docker image size, and voice cloning with a real clip.
- One generation at a time per replica; extra calls wait, and more than the in-flight cap get 429. The rate limit is per replica.
- The `packed` weights (954 MB) are lossless; `emb4` (469 MB) is smaller on disk but has a lossy embedding; `full` (3.5 GB) is plain bf16. The `student_w4` decoder is smaller, not faster. Memory in use was not compared across them.
- Output is WAV only. Convert on the caller's side for MP3.
- The revision is pinned (`SERVICE_MODEL_REVISION`) and the update check only finds a missing download.
- Cloning a real person's voice needs their consent. Only the admin password can add voices.

## Try it from the admin page

Open `/admin/` and use **Try it** to call the public API with a service token held only in memory. Runs use normal token scopes, limits and caches; the panel shows HTTP status, latency, responses, cancellation and a curl equivalent with a token placeholder. See [the web UI guide](docs/guide-web-ui.md#try-it-send-a-real-request).

Speak sends text, voice, seed, temperature, preset and normalize to `POST /v1/speak`, then displays WAV audio with playback controls and a download. `GET /v1/voices` is filtered by the public token's allowed projects list. Only seeded calls are cached. A streaming request receives WAV chunks; the player is created when the bounded audio response finishes.

## Documentation

- [Purpose: input, output and what it is for](docs/purpose.md)
- [Deployment](deployment.md)
- [Changelog](CHANGELOG.md)
- [Design notes](docs/design.md)
- [Docker on another machine](docs/guide-docker-deployment-device.md)
- [Docker on this PC](docs/guide-docker-same-device.md)
- [Run without Docker](docs/guide-no-docker-same-device.md)
- [Test it from the command line](docs/guide-cli.md)
