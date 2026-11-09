# TTS_Kitten2_Model: Docker Desktop on this PC

Before the first call, open `/admin/` → **Updates** → **Download**. Startup never downloads weights. The [admin guide](guide-web-ui.md#updates-and-first-download) includes the curl alternative.

Run KittenTTS 2 text to speech with voice cloning on the GPU when one is reserved, else the CPU (about 6 GB of RAM on the CPU), in Docker Desktop on the machine you work on, so other programs on it can call it.

## Requirements

- Docker Desktop with Compose v2 (Windows: WSL2 backend).
- Network access for explicit Downloads from the Updates card; startup and inference use downloaded files only.
- RAM per replica: about 5.7 GB resident after loading and 6.1 GB peak (measured on a Ryzen 7 7445HS, `packed` weights). Plan for 8 GB free per replica.
- Compose reserves one NVIDIA GPU (NVIDIA Container Toolkit; Docker Desktop on Windows: WSL2 backend with GPU support). On a host without one, delete the `resources:` block under `deploy:` in `docker-compose.yml`; it then runs on the CPU, and the model is heavy there: see "Hardware" below.

## Steps

1. Configure. In `TTS_Kitten2_Model/`:
   ```bash
   cp .env.example .env
   ```
   Set `SERVICE_ADMIN_PASSWORD` (required to download weights through the admin page). Leave `SERVICE_PORT=29323`. Leave `SERVICE_REPLICAS=1`.
2. Start:
   ```bash
   docker compose up -d --build
   ```
   Startup loads downloaded weights only; open `/admin/`, then **Updates → Download** before the first call. `tts_kitten2_model_lb` starts once `/health` answers; readiness may still be false
   (300 s startup grace). Watch with `docker compose ps` and `docker compose logs -f tts_kitten2_model`.
3. Check:
   ```bash
   curl http://127.0.0.1:29323/health
   ```
   `ready` is `false` until the model has loaded, then `true`.
4. Open the admin page: `http://127.0.0.1:29323/admin/` (see [guide-web-ui.md](guide-web-ui.md)) and make a token for each caller.
5. Try a call:
   ```bash
   curl -X POST http://127.0.0.1:29323/v1/speak -H "Content-Type: application/json" -H "X-Internal-Token: kitten2_..." -d '{"text":"Hello from the model service."}' -o hello.wav
   ```
   Expect a WAV file, `hello.wav`.
6. Callers connect to the published port. The caller holds the URL and token:
   - Caller on the host: `http://127.0.0.1:29323`.
   - Caller in another Docker stack on the same host: `http://host.docker.internal:29323`.

## Settings

In `.env` next to `docker-compose.yml`:

| Variable | Default | Effect |
|---|---|---|
| `SERVICE_REPLICAS` | `1` | Number of `tts_kitten2_model` containers. Read by Compose. |
| `SERVICE_PORT` | `29323` | Host port `tts_kitten2_model_lb` publishes. |
| `SERVICE_ADMIN_PASSWORD` | empty | Password for `/admin/`. When set, every call except `/health` must send a token as `X-Internal-Token`. Empty = no auth. |
| `SERVICE_MEM_LIMIT` | `0` | RAM cap per replica (for example `8g`); 0 = no cap. A cap keeps an out-of-memory kill inside the container. Read by Compose. |
| `SERVICE_NUM_THREAD` | torch decides | Starting value for the CPU threads card (torch threads, applied live without a reload); a value saved on `/admin/` wins. Use the number of physical cores, not logical CPUs. |

On the **Settings** card of `/admin/` (saved in `settings.json` beside the tokens, shared by all replicas; a saved
value beats the environment variable named in brackets): update check hours (`SERVICE_UPDATE_CHECK_HOURS`, 6),
in-flight cap (`SERVICE_MAX_INFLIGHT`, 0 = 4), answers kept per replica (`SERVICE_CACHE_SIZE`, 32, 0 = off; seeded calls only, at most 1 MB each), model revision (`SERVICE_MODEL_REVISION`, restart; the pinned Hub commit), device (`SERVICE_DEVICE`, restart, `cpu`; `cuda` only on a host with a GPU and a CUDA torch, compose reserves none), weight variant (`SERVICE_WEIGHTS`, restart, `packed`, `emb4` or `full`), decoder (`SERVICE_DECODER`, restart, `default` or `student_w4`), most audio tokens per chunk (`SERVICE_MAX_NEW_TOKENS`, restart, 1000) and load at start (`SERVICE_WARM`, restart). Compose does not pass these;
add the variable under `environment:` of `tts_kitten2_model` to use one as a starting value.

## Daily use

```bash
docker compose ps          # state
docker compose logs -f tts_kitten2_model
docker compose down        # stop (the weights volume is kept)
docker compose up -d --build && docker compose restart tts_kitten2_model_lb   # after a code change
```

## Time it

Try it and time it:

```bash
python tools/bench.py http://127.0.0.1:29323 --save out
```

## Problems

| Symptom | Fix |
|---|---|
| `address already in use` on 29323 | Another copy (`run.bat`, or the same stack on another compose project) is running. Stop it or change `SERVICE_PORT`. |
| `/health` shows `ready: false` for minutes | Download weights from the Updates card first; otherwise the service stays available with `ready: false`. Check `docker compose logs -f tts_kitten2_model`. |
| 401 Invalid token | The caller's token is missing or revoked; make one on `/admin/`. |
| 503 `no GPU is visible here` | The `device` setting is `cuda` but the container has no GPU. Set it back to `cpu`. |
| Container restarts in a loop | Out of RAM (about 6 GB per replica). Close other programs, or set `SERVICE_MEM_LIMIT` to find the limit. |
| `tts_kitten2_model_lb` never starts | No replica is healthy yet (process failure or out of memory). `docker compose logs tts_kitten2_model`. |
| Replicas restart in a loop | Out of RAM (about 6 GB per replica). Lower `SERVICE_REPLICAS`, or check `docker compose logs tts_kitten2_model`. |
| 403 "may not use voice" | The token's list on `/admin/` does not include that voice (or `Bruno`, the default, when `voice` is left out). |
| 404 on `/v1/speak` | The voice is not served here. `GET /v1/voices` lists them. |
| 422 on `format` or another field | Only `text`, `voice`, `seed`, `temperature`, `preset`, `normalize` and `stream` exist; the reply is always WAV. |
| Very slow speech | Expected: about 5 to 10 s of work per second of audio on a 6-core CPU. Set the CPU threads card to the physical core count. |
| 429 | Over the token's rate limit, or too many calls waiting for the model. |
| nginx 502 after scaling | `tts_kitten2_model_lb` not restarted after the replica count changed. |

The load balancer also joins external `citadel_core` as `tts_kitten2_model_lb`. Start the Citadel stack first so that network exists; tool services on it use `http://tts_kitten2_model_lb:29323`. Docker project and API image are `tts_kitten2_model` and `tts_kitten2_model:latest`; persistent volumes have explicit `tts_kitten2_model_*` names. Volume migration and rollback instructions are in [CHANGELOG.md](../CHANGELOG.md).
