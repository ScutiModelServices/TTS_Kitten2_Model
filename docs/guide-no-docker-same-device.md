# TTSKitten2Model: without Docker, on Windows

Run KittenTTS 2 text to speech with voice cloning on the CPU (about 6 GB of RAM) directly with Python: one process, no load balancer, listening on `127.0.0.1:9250`.

## Requirements
- Windows with Python 3.11 or newer and uv (`winget install astral-sh.uv`).
- Enough RAM: about 6 GB free. The `uv.lock` pins the CPU build of torch.
- Internet on the first start (about 2 GB of weights).

## Start
Double-click `run.bat`, or run it in a terminal from `TTSKitten2Model\`. Choose **1 Run the service** in the menu, or run `run.bat run` to skip the menu. It runs `uv sync` to create or update `.venv`, then starts
`python src/app.py`. The first start downloads about 2 GB of weights. `run.bat` sets `PYTHONUTF8=1` (the model package reads files without an encoding, which fails on the Windows legacy code page); set it yourself when you start `python src/app.py` another way.

Linux or macOS:
```bash
cd TTSKitten2Model
uv sync
uv run python src/app.py
```
On macOS the CPU build of torch comes from PyPI; this was not tried here.

## Settings
`run.bat` and `app.py` read the real environment, **not** `.env`. Set variables before starting:

| Variable | Default | Effect |
|---|---|---|
| `KITTEN2_HOST` | `127.0.0.1` | Bind address. Use `0.0.0.0` only if other devices must reach it. |
| `KITTEN2_PORT` | `9250` | Port. |
| `KITTEN2_ADMIN_PASSWORD` | empty | Unlocks `/admin/` and requires tokens on every call but `/health`. Empty = no auth. |
| `KITTEN2_WARM` | `1` | Load the model at start; with `0` the first request pays the load time. |
| `KITTEN2_DEVICE` | `cpu` | `cuda` only with a GPU and a CUDA build of torch (the lock file pins the CPU build). |

PowerShell: `$env:KITTEN2_ADMIN_PASSWORD = "secret"; .\run.bat`
Bash: `KITTEN2_ADMIN_PASSWORD=secret uv run python src/app.py`

## Check
```bash
curl http://127.0.0.1:9250/health
```
`ready` is `false` until the model has loaded. Then open `http://127.0.0.1:9250/admin/` (see [guide-web-ui.md](guide-web-ui.md)),
make a token, and try a call:
```bash
curl -X POST http://127.0.0.1:9250/v1/speak -H "Content-Type: application/json" -H "X-Internal-Token: kitten2_..." -d '{"text":"Hello from the model service."}' -o hello.wav
```

## Stop
Ctrl+C in the terminal. Do not run this and the Docker stack together: both use port 9250.

## Tests
`uv run pytest`.
