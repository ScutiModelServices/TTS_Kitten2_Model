# TTSKitten2Model design notes

Built from `TTSAudio8Model` (API shape, cloned voices in a shared `voices` volume, WAV streaming, shared files) and `TTSParadeeModel` (CPU engine, built-in voices). Behaviour is in `README.md`; the differences from the other services are listed in `AI/ModelServices/_docs/SERVICE-SPECIFIC.md`.

Sources read: the Hub model `KittenML/kitten-tts-2` at commit `c93cb7c271baa51d9ae8204d5277988906f235a2` (model card, `config.json`, file list) and the `kittenml` 0.9.4 wheel (`get_model.py`, `kittentts2/model.py`).

## Decisions

- **Engine = the `kittenml` package.** `KittenTTS(<local folder>, device=, weights=, decoder=)` then `generate` / `generate_stream`. The package is Apache 2.0; the weights are not (Stellon Labs Community License).
- **Pinned revision, downloaded here.** The package would fetch `main` by itself, so `snapshot_download(revision=...)` with the package's own file list runs first and the package gets the local folder. `_kitten2_files` is private, so a `kittenml` bump needs a look at it.
- **Voices = built-in plus cloned.** Built-in names come from the model (115). A cloned voice is a clip plus transcript, always sent with the clip so Whisper never loads. The admin route refuses a built-in name (409), so a clone never hides a built-in voice. The old `none` voice of Audio8 does not exist here: the default is `Bruno`.
- **No own text splitting.** The package chunks at about 380 characters and handles seams; a non-streamed call uses `generate` (seams trimmed), a stream uses `generate_stream` (chunks untrimmed).
- **Seed = `advanced={"seed": n}`**, which calls `torch.manual_seed`. Global state, so one generation runs at a time per replica (the engine's semaphore already enforces it).
- **CPU torch from the CPU index** (`pyproject.toml`, like LFM3Model); the Dockerfile asserts there is no CUDA in the build. `device=cuda` is allowed for a host with a GPU but compose reserves none.
- **Windows needs `PYTHONUTF8=1`**: the first real load failed with a `charmap` decode error inside the package. `run.bat` sets it; `UnicodeError` is not turned into a 503 so such a fault is not mistaken for a bad setting.

## Measured

Ryzen 7 7445HS (6 cores, 15 GB RAM), CPU, bf16, `packed` weights: download about 2.0 GB (weights, decoder, 115 voice clips), 5.7 GB resident after load, 6.1 GB peak, 0.1 to 0.2 times real time. Not measured: GPU, Docker image, real-clip cloning, `emb4` / `student_w4` memory.
