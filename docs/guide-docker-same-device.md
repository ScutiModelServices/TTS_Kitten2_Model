# TTSKitten2Model: Docker Desktop on this PC

Run KittenTTS 2 text to speech with voice cloning on the CPU (about 6 GB of RAM) in Docker Desktop on the machine you work on, so other programs on it can call it.

## Requirements

- Docker Desktop with Compose v2 (Windows: WSL2 backend).
- Network access on the first start to download about 2 GB from Hugging Face into the `models` volume.
- RAM per replica: about 5.7 GB resident after loading and 6.1 GB peak (measured on a Ryzen 7 7445HS, `packed` weights). Plan for 8 GB free per replica.
- It runs on the CPU, so any Docker host works, but the model is heavy: see "Hardware" below before putting it on a small box.

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

## Settings

In `.env` next to `docker-compose.yml`:

| Variable | Default | Effect |
|---|---|---|
| `KITTEN2_REPLICAS` | `1` | Number of `kitten2` containers. Read by Compose. |
| `KITTEN2_PORT` | `9250` | Host port `kitten2_lb` publishes. |
| `KITTEN2_ADMIN_PASSWORD` | empty | Password for `/admin/`. When set, every call except `/health` must send a token as `X-Internal-Token`. Empty = no auth. |
| `KITTEN2_MEM_LIMIT` | `0` | RAM cap per replica (for example `8g`); 0 = no cap. A cap keeps an out-of-memory kill inside the container. Read by Compose. |
| `KITTEN2_NUM_THREAD` | torch decides | Starting value for the CPU threads card (torch threads, applied live without a reload); a value saved on `/admin/` wins. Use the number of physical cores, not logical CPUs. |

On the **Settings** card of `/admin/` (saved in `settings.json` beside the tokens, shared by all replicas; a saved
value beats the environment variable named in brackets): update check hours (`KITTEN2_UPDATE_CHECK_HOURS`, 6),
in-flight cap (`KITTEN2_MAX_INFLIGHT`, 0 = 4), answers kept per replica (`KITTEN2_CACHE_SIZE`, 32, 0 = off; seeded calls only, at most 1 MB each), model revision (`KITTEN2_MODEL_REVISION`, restart; the pinned Hub commit), device (`KITTEN2_DEVICE`, restart, `cpu`; `cuda` only on a host with a GPU and a CUDA torch, compose reserves none), weight variant (`KITTEN2_WEIGHTS`, restart, `packed`, `emb4` or `full`), decoder (`KITTEN2_DECODER`, restart, `default` or `student_w4`), most audio tokens per chunk (`KITTEN2_MAX_NEW_TOKENS`, restart, 1000) and load at start (`KITTEN2_WARM`, restart). Compose does not pass these;
add the variable under `environment:` of `kitten2` to use one as a starting value.

## Daily use

```bash
docker compose ps          # state
docker compose logs -f kitten2
docker compose down        # stop (the weights volume is kept)
docker compose up -d --build && docker compose restart kitten2_lb   # after a code change
```

## Time it

Try it and time it:

```bash
python tools/bench.py http://127.0.0.1:9250 --save out
```

## Problems

| Symptom | Fix |
|---|---|
| `address already in use` on 9250 | Another copy (`run.bat`, or the same stack on another compose project) is running. Stop it or change `KITTEN2_PORT`. |
| `/health` shows `ready: false` for minutes | First start: the weights are downloading or loading. Check `docker compose logs -f kitten2`. |
| 401 Invalid token | The caller's token is missing or revoked; make one on `/admin/`. |
| 503 `no GPU is visible here` | The `device` setting is `cuda` but the container has no GPU. Set it back to `cpu`. |
| Container restarts in a loop | Out of RAM (about 6 GB per replica). Close other programs, or set `KITTEN2_MEM_LIMIT` to find the limit. |
| `kitten2_lb` never starts | No replica is healthy yet (first download, or out of memory). `docker compose logs kitten2`. |
| Replicas restart in a loop | Out of RAM (about 6 GB per replica). Lower `KITTEN2_REPLICAS`, or check `docker compose logs kitten2`. |
| 403 "may not use voice" | The token's list on `/admin/` does not include that voice (or `Bruno`, the default, when `voice` is left out). |
| 404 on `/v1/speak` | The voice is not served here. `GET /v1/voices` lists them. |
| 422 on `format` or another field | Only `text`, `voice`, `seed`, `temperature`, `preset`, `normalize` and `stream` exist; the reply is always WAV. |
| Very slow speech | Expected: about 5 to 10 s of work per second of audio on a 6-core CPU. Set the CPU threads card to the physical core count. |
| 429 | Over the token's rate limit, or too many calls waiting for the model. |
| nginx 502 after scaling | `kitten2_lb` not restarted after the replica count changed. |
