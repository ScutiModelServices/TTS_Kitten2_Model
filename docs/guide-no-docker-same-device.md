# TTS_Kitten2_Model: without Docker, on Windows

Run KittenTTS 2 text to speech with voice cloning on the CPU (about 6 GB of RAM) directly with Python: one process, no load balancer, listening on `127.0.0.1:29323`.

## Requirements
- Windows with Python 3.11 or newer and uv (`winget install astral-sh.uv`).
- Enough RAM: about 6 GB free. The `uv.lock` pins the CPU build of torch.
- Internet on the first start (about 2 GB of weights).

## Start
Double-click `run.bat`, or run it in a terminal from `TTS_Kitten2_Model\`. Choose **1 Run the service** in the menu, or run `run.bat run` to skip the menu. It runs `uv sync` to create or update `.venv`, then starts
`python src/app.py`. The first start downloads about 2 GB of weights. `run.bat` sets `PYTHONUTF8=1` (the model package reads files without an encoding, which fails on the Windows legacy code page); set it yourself when you start `python src/app.py` another way.

Linux or macOS:
```bash
cd TTS_Kitten2_Model
uv sync
uv run python src/app.py
```
On macOS the CPU build of torch comes from PyPI; this was not tried here.

## Settings
`run.bat` loads `.env` in this folder (copy `.env.example`) through `--dotenv` and prints the names it loaded, never the values; a real environment variable wins over it. A plain `python src/app.py` does not read `.env`. Set variables in `.env` or in the environment before starting:

| Variable | Default | Effect |
|---|---|---|
| `SERVICE_HOST` | `127.0.0.1` | Bind address. Use `0.0.0.0` only if other devices must reach it. |
| `SERVICE_PORT` | `29323` | Port. |
| `SERVICE_ADMIN_PASSWORD` | empty | Unlocks `/admin/` and requires tokens on every call but `/health`. Empty = no auth. |
| `SERVICE_WARM` | `1` | Load the model at start; with `0` the first request pays the load time. |
| `SERVICE_DEVICE` | `cpu` | `auto` = `cuda` when a GPU is visible, else `cpu`. `cuda` only with a GPU and a CUDA build of torch (the lock file pins the CPU build, so `auto` stays on `cpu` until you swap it). |
| `SERVICE_MODELS_DIR` | the library's default cache | Folder for downloaded model weights. Sets `HF_HOME` (and `OLLAMA_MODELS` to `<folder>\ollama`) at start; a real `HF_HOME` or `OLLAMA_MODELS` wins. Docker keeps weights in the `_models` volume and ignores it. |

PowerShell: `$env:SERVICE_ADMIN_PASSWORD = "secret"; .\run.bat`
Bash: `SERVICE_ADMIN_PASSWORD=secret uv run python src/app.py`

## Check
```bash
curl http://127.0.0.1:29323/health
```
`ready` is `false` until the model has loaded. Then open `http://127.0.0.1:29323/admin/` (see [guide-web-ui.md](guide-web-ui.md)),
make a token, and try a call:
```bash
curl -X POST http://127.0.0.1:29323/v1/speak -H "Content-Type: application/json" -H "X-Internal-Token: kitten2_..." -d '{"text":"Hello from the model service."}' -o hello.wav
```

## Stop
Ctrl+C in the terminal. Do not run this and the Docker stack together: both use port 29323.

## Tests
`uv run pytest`.
