# Deploying TTSKitten2Model

TTSKitten2Model is one HTTP service (port 9250). It runs as `kitten2` replicas behind an nginx load balancer,
`kitten2_lb`. Callers use `http://<host>:9250`; they never reach a replica directly.

## Requirements

- Docker with Compose v2.
- RAM per replica: about 5.7 GB resident after loading and 6.1 GB peak (measured on a Ryzen 7 7445HS, `packed` weights). Plan for 8 GB free per replica.
- Network access on the first start to download about 2 GB from Hugging Face into the `models` volume.
- It runs on the CPU, so any Docker host works, but the model is heavy: see "Hardware" below before putting it on a small box.

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

## Start

```bash
docker compose up -d --build
curl http://127.0.0.1:9250/health
```

Expect `"ready": true` once a replica has loaded the model. The first start downloads about 2 GB into the `models`
volume (then under a minute to load), so `kitten2_lb` can take a minute to appear (the health check allows 300 s before failures count; run
`docker compose ps` and wait).

Try it and time it:

```bash
python tools/bench.py http://127.0.0.1:9250 --save out
```

## Scaling

```bash
KITTEN2_REPLICAS=3 docker compose up -d --build
docker compose restart kitten2_lb
```

The restart is needed because nginx resolves replica addresses once at start.

## Updating the files

The model revision is pinned, so the **Updates** card only reports a missing download. To move to a newer commit, read its model card and licence, change the *Model revision* setting, restart, then press **Download new weights**.
That button fetches them into the models volume; every replica drops its old copy within a few seconds and loads the
new one on its next request. Updating the service itself: `docker compose up -d --build`, then
`docker compose restart kitten2_lb`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `kitten2_lb` never starts | No replica is healthy yet (first download, or out of memory). `docker compose logs kitten2`. |
| Replicas restart in a loop | Out of RAM (about 6 GB per replica). Lower `KITTEN2_REPLICAS`, or check `docker compose logs kitten2`. |
| 401 "Invalid token" | The caller sends no token, or a revoked one. |
| 403 "may not use voice" | The token's list on `/admin/` does not include that voice (or `Bruno`, the default, when `voice` is left out). |
| 404 on `/v1/speak` | The voice is not served here. `GET /v1/voices` lists them. |
| 422 on `format` or another field | Only `text`, `voice`, `seed`, `temperature`, `preset`, `normalize` and `stream` exist; the reply is always WAV. |
| 503 `no GPU is visible here` | The `device` setting is `cuda` but the container has no GPU. Set it back to `cpu`. |
| Very slow speech | Expected: about 5 to 10 s of work per second of audio on a 6-core CPU. Set the CPU threads card to the physical core count. |
| 429 | Over the token's rate limit, or too many calls waiting for the model. |
| nginx 502 after scaling | `kitten2_lb` not restarted after the replica count changed. |

## Releasing

A plain publish (`tools\deploy.bat` option 1) only updates the `live` branch. For a release set `VERSION` (and
`pyproject.toml` to the same number), commit, then run `tools\deploy.bat` option R or
`py tools\publish_live.py --release`. `tools\make_zip.bat` then builds `zip_versions\TTSKitten2Model-<VERSION>.zip`.


## Verify with Try it

After deployment, open `/admin/` and use **Try it** with a public service token to exercise the deployed public route. It uses normal scope, admission/rate limits and cache behavior, so busy or unauthorized requests remain visible as HTTP errors. No new environment setting or admin-to-public auth bypass is introduced. Deploy the complete `web/` directory, including `playground.js`. See [the web UI guide](docs/guide-web-ui.md#try-it-send-a-real-request) for input formats, limits and token handling.
