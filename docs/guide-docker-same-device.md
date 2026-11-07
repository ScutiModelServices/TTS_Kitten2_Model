# TTSKitten2Model: Docker Desktop on this PC

Run KittenTTS 2 text to speech with voice cloning on the CPU (about 6 GB of RAM) in Docker Desktop on the machine you work on, so other programs on it can call it.

## Requirements
- Docker Desktop with Compose v2 (Windows: WSL2 backend).
- Internet on the first start (about 2 GB of weights).

## Steps
1. Configure. In `TTSKitten2Model/`:
   ```bash
   cp .env.example .env
   ```
   Set `KITTEN2_ADMIN_PASSWORD` (empty = no auth and no admin page, fine for a local test). Leave `KITTEN2_PORT=9250`. Leave `KITTEN2_REPLICAS=1`.
2. Start:
   ```bash
   docker compose up -d --build
   ```
   The first start downloads about 2 GB of weights into the `models` volume. `kitten2_lb` starts only after the service is healthy
   (up to 300 s grace). Watch with `docker compose ps` and `docker compose logs -f kitten2`.
3. Check:
   ```bash
   curl http://127.0.0.1:9250/health
   ```
   `ready` is `false` until the model has loaded, then `true`.
4. Open the admin page: `http://127.0.0.1:9250/admin/` (see [guide-web-ui.md](guide-web-ui.md)) and make a token for each caller.
5. Try a call:
   ```bash
   curl -X POST http://127.0.0.1:9250/v1/speak -H "Content-Type: application/json" -H "X-Internal-Token: kitten2_..." -d '{"text":"Hello from the model service."}' -o hello.wav
   ```
   Expect a WAV file, `hello.wav`.
6. Callers connect to the published port. The caller holds the URL and token:
   - Caller on the host: `http://127.0.0.1:9250`.
   - Caller in another Docker stack on the same host: `http://host.docker.internal:9250`.

## Daily use
```bash
docker compose ps          # state
docker compose logs -f kitten2
docker compose down        # stop (the weights volume is kept)
docker compose up -d --build && docker compose restart kitten2_lb   # after a code change
```

## Problems
| Symptom | Fix |
|---|---|
| `address already in use` on 9250 | Another copy (`run.bat`, or the same stack on another compose project) is running. Stop it or change `KITTEN2_PORT`. |
| `/health` shows `ready: false` for minutes | First start: the weights are downloading or loading. Check `docker compose logs -f kitten2`. |
| 401 Invalid token | The caller's token is missing or revoked; make one on `/admin/`. |
| 503 `no GPU is visible here` | The `device` setting is `cuda` but the container has no GPU. Set it back to `cpu`. |
| Container restarts in a loop | Out of RAM (about 6 GB per replica). Close other programs, or set `KITTEN2_MEM_LIMIT` to find the limit. |
