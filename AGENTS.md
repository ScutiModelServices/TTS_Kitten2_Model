# TTS_Kitten2_Model

KittenTTS 2 (1.7B speech language model, 115 built-in voices, zero-shot voice cloning) text to speech, served over HTTP on the GPU when one is visible (device `auto`), else the CPU, behind the shared model-service admin page, tokens and settings. Port 29323, env prefix `SERVICE_`, token prefix `kitten2_`.

## Agent instructions
This file is the one instruction file for every coding agent; `CLAUDE.md` only imports it (`@AGENTS.md`). Edit this file, never `CLAUDE.md`.

## Commands (from this folder, venv `.venv`, managed by uv)
- Install: `uv sync` (`winget install astral-sh.uv` if uv is missing)
- Test: `uv run pytest -q`. `tests/test_admin_ui.py` needs Playwright and its browser and is skipped without it. On Windows, if uv fails with "cannot move the file to a different disk drive", set `UV_CACHE_DIR` to a folder on the same drive and `UV_LINK_MODE=copy`.
- Run: `run.bat run`, or `uv run python src/app.py` with `PYTHONUTF8=1` set (add `--dotenv` to load `.env`), or `docker compose up -d --build`

## Rules
- Follow the `model-service-parity` skill and `AI/ModelServices/_docs/SHARED-FEATURES.md` (what must match in every model service) and `AI/ModelServices/_docs/SERVICE-SPECIFIC.md` (what differs on purpose). A change to a shared feature goes to every service; a new difference goes into `SERVICE-SPECIFIC.md` in the same change.
- `web/index.html`, `web/playground.js`, `src/tokens.py`, `src/settings.py`, `src/updates.py` and `.dockerignore` are copies shared with the other model services. Change one, copy it to the others, run `python tools/check_sync.py` in each repo.
- `POST /v1/speak` takes `text`, `voice`, `seed`, `temperature`, `preset`, `normalize`, `stream` and returns WAV. A voice is one of the 115 built-in ones (default `Bruno`) or a cloned one: a reference clip plus transcript in the `tts_kitten2_model_voices` volume (`src/voices.py`), added with `PUT /admin/voices/{name}` (admin password; a built-in name gets 409). `src/audio.py` is the same file as in the other TTS services.
- The engine uses the `kittenml` package (pinned `==0.9.4`). It downloads the pinned `model_revision` itself (`_kitten2_files` from `kittenml.get_model` is private: check it after a version bump) and points the package at the local folder. The package has no `trust_remote_code`. The weights are under the Stellon Labs Community License (free below USD 1M revenue or funding); read its attribution rules before shipping a product on them.
- Run Python with `PYTHONUTF8=1` on Windows (`run.bat` sets it): the package reads files without an encoding.
- The cache keeps only seeded calls. A non-streamed call joins the model's chunks (about 380 characters each); a stream sends them untrimmed, one per chunk.
- CUDA torch (`cu126`, `torch==2.7.1`, same wheel as TTS_Audio8_Model); `device` setting default `auto` = cuda when a GPU is visible, else cpu. Compose reserves one NVIDIA GPU. Measured on CPU only (Ryzen 7 7445HS, 6 cores, bf16): 5.7 GB resident after load, 6.1 GB peak, 0.1 to 0.2 times real time; GPU speed and VRAM not measured. Tests use a fake model.
- Behaviour changes update `README.md`, `deployment.md`, `docs/guide-web-ui.md`, `.env.example` and `CHANGELOG.md` in the same commit.
- Never read or print `.env`, `tokens.json` or `settings.json`.
- Commit with the noreply author email `214214011+scutiii2@users.noreply.github.com` (another address is rejected on push). Push `main`, then run `python tools/publish_live.py`. Build Docker only when the Dockerfile or the dependencies changed.
