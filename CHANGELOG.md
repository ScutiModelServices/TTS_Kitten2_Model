# Changelog

## Unreleased

- Fix: a caller that hangs up before the first piece of speech is ready now stops the generation after the piece being made, instead of speaking the whole text for nobody (a following call waited 87 s on Audio8 and over 300 s on Kitten2 for a long text). The request timing moved from `@app.middleware("http")` to a plain ASGI middleware (`Measure` in `src/disconnect.py`), because the decorator form hides a hang-up from `request.is_disconnected()`; metrics are unchanged.

- Fix: a caller that hangs up before the first piece of speech is ready now stops the generation after the piece being made, instead of speaking the whole text for nobody (a following call waited 87 s on Audio8 and over 300 s on Kitten2 for a long text). The request timing moved from `@app.middleware("http")` to a plain ASGI middleware (`Measure` in `src/disconnect.py`), because the decorator form hides a hang-up from `request.is_disconnected()`; metrics are unchanged.

- Admin UI: separate hash-routed pages in a collapsible sidebar; health-first Overview, one main-header page title, capability-specific navigation, draft-preserving navigation and responsive desktop/mobile layout. Existing admin and public API actions are preserved.

- Admin page: the CPU threads card and tile are hidden when `CONFIG.tags` has `host-threads`, and the Project models card is shown only with `project-models`.

- Admin page: `CONFIG.tags` (same tags as `docs/purpose.md`) switch tag-driven notes: `gpu` shows a CPU-threads note, `license-restricted` shows a licence note on the Updates card.

- Admin page: **Cloned voices** card (add, list, delete) and `GET /admin/voices` (admin password; each voice with `cloned` true or false). The page shows it because `CONFIG.tags` in `web/index.html` holds `voice-cloning`; `purpose_audit.py` checks that `CONFIG.tags` equals the tags in `docs/purpose.md`.

- Fix: after Download, a CPU threads change or a sync from another replica drops the loaded model, the service now reloads it in the background (when "Load the model at start" is on) instead of showing "Starting" on `/admin/` until the first request.
- `POST /v1/speak` accepts a one-call cloned voice: `reference_audio_base64` + `reference_text` instead of `voice`. The clip lives in a temp file only while the speech is made, is deleted when the call ends, fails or is closed (streams too), is never stored in the voices volume, and its answers are never cached. `X-Voice` is `custom`; a token limited to certain voices gets 403. The audio may be a `data:` URL; the admin **Try it** panel has fields for it. Same change in TTS_Audio8_Model.

- Breaking: startup, warm-up and inference load downloaded weights only. Before the first call, open `/admin/` → Updates → Download (or POST `/admin/updates/weights` with the admin token). Missing weights leave health/admin available and speech returns 503. Checks never download; explicit Downloads invalidate every replica.

- `device` setting accepts `auto` (new default): `cuda` when torch sees a GPU, else `cpu`.
- Torch now comes from the CUDA index (`cu126`, pinned `torch==2.7.1` like TTS_Audio8_Model), so the venv and the image grow by about 4.5 GB. The Dockerfile no longer asserts CPU-only torch and compose reserves one NVIDIA GPU (needs the NVIDIA Container Toolkit; a host without a GPU must delete the `resources:` block in `docker-compose.yml`).

- `SERVICE_MODELS_DIR` sets where a local (no Docker) run keeps downloaded model weights: `settings.apply_models_dir()` maps it to `HF_HOME` and `OLLAMA_MODELS` at start.
- Docs: `docs/guide-cli.md`, a PowerShell-only way to test the service.

### Breaking: common service environment variables

Service-owned environment variables now use `SERVICE_*`. Old names are no longer read.
Rename old names once in your real `.env`, Compose `environment:` block, and CI/secret settings.

| Old name | New name |
|---|---|
| `KITTEN2_ADMIN_PASSWORD` | `SERVICE_ADMIN_PASSWORD` |
| `KITTEN2_CACHE_SIZE` | `SERVICE_CACHE_SIZE` |
| `KITTEN2_DECODER` | `SERVICE_DECODER` |
| `KITTEN2_DEVICE` | `SERVICE_DEVICE` |
| `KITTEN2_HOST` | `SERVICE_HOST` |
| `KITTEN2_MAX_INFLIGHT` | `SERVICE_MAX_INFLIGHT` |
| `KITTEN2_MAX_NEW_TOKENS` | `SERVICE_MAX_NEW_TOKENS` |
| `KITTEN2_MEM_LIMIT` | `SERVICE_MEM_LIMIT` |
| `KITTEN2_MODEL_REVISION` | `SERVICE_MODEL_REVISION` |
| `KITTEN2_NUM_THREAD` | `SERVICE_NUM_THREAD` |
| `KITTEN2_PORT` | `SERVICE_PORT` |
| `KITTEN2_REPLICAS` | `SERVICE_REPLICAS` |
| `KITTEN2_TOKENS_FILE` | `SERVICE_TOKENS_FILE` |
| `KITTEN2_UPDATE_CHECK_HOURS` | `SERVICE_UPDATE_CHECK_HOURS` |
| `KITTEN2_VOICES_DIR` | `SERVICE_VOICES_DIR` |
| `KITTEN2_WARM` | `SERVICE_WARM` |
| `KITTEN2_WEB_DIR` | `SERVICE_WEB_DIR` |
| `KITTEN2_WEIGHTS` | `SERVICE_WEIGHTS` |
| `KITTEN2_WEIGHTS_MARKER` | `SERVICE_WEIGHTS_MARKER` |

- Move the default service port from 9250 to 29323, including API replicas and the nginx load balancer. Update any explicit old port in your real `.env`, saved tool-service `backends.json` connections, and browser or MCP client configuration once. With Compose defaults, recreate the stack to use the new host and container ports; a custom host-port override stays as configured, while container ports still change to 29323.

- Renamed `TTSKitten2Model` to `TTS_Kitten2_Model`; Docker project, API image, services, load balancer and volumes now use `tts_kitten2_model` names. Callers on `citadel_core` connect to `tts_kitten2_model_lb` at the existing port.
- Docker volume migration: existing volumes with old names are orphaned; renaming does not move data. Stop the old stack before copying; never use `down -v`. The commands below assume the previous default Compose project name; substitute actual volume names if `-p` or `COMPOSE_PROJECT_NAME` overrode it.
  - `kitten2_models` → `tts_kitten2_model_models`: `docker volume inspect kitten2_models && docker volume create tts_kitten2_model_models && docker run --rm -v kitten2_models:/from:ro -v tts_kitten2_model_models:/to alpine:3.21 sh -c "cd /from && cp -a . /to/"`
  - `kitten2_voices` → `tts_kitten2_model_voices`: `docker volume inspect kitten2_voices && docker volume create tts_kitten2_model_voices && docker run --rm -v kitten2_voices:/from:ro -v tts_kitten2_model_voices:/to alpine:3.21 sh -c "cd /from && cp -a . /to/"`
  - `kitten2_tokens` → `tts_kitten2_model_data`: `docker volume inspect kitten2_tokens && docker volume create tts_kitten2_model_data && docker run --rm -v kitten2_tokens:/from:ro -v tts_kitten2_model_data:/to alpine:3.21 sh -c "cd /from && cp -a . /to/"`
- To retain an old volume instead, set its top-level volume definition to `external: true` and `name: <old-volume-name>` in a local Compose override. Rollback: stop the renamed stack, restore the previous checkout and folder name, and restart the old stack with its original volumes; copy back newer data first if the renamed stack accepted writes.

## 0.1.0

- First version: KittenTTS 2 (`KittenML/kitten-tts-2`, 1.7B, 115 built-in voices, voice cloning) on the CPU through the `kittenml` package, with the admin page, tokens (scope, rate limit, expiry), metrics, Settings card, update check, answer cache and Try it panel shared with the other model services.
- `POST /v1/speak` takes `text`, `voice`, `seed`, `temperature`, `preset`, `normalize` and `stream` and returns a WAV file. `GET /v1/voices` lists built-in and cloned voices (default `Bruno`).
- Cloned voices: `PUT`/`DELETE /admin/voices/{name}` (admin password); the transcript is required, so Whisper is never loaded. A built-in name gets 409.
- Settings: `model_revision` (pinned Hub commit), `device`, `weights`, `decoder`, `max_new_tokens`.
- Measured on a Ryzen 7 7445HS: 5.7 GB resident, 6.1 GB peak, 0.1 to 0.2 times real time.
