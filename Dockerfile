# syntax=docker/dockerfile:1
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
# libsndfile: the soundfile wheel bundles it on x86-64 Linux. espeak-ng comes from the espeakng_loader wheel.
ENV SERVICE_WEB_DIR=/app/web SERVICE_TOKENS_FILE=/data/tokens.json SERVICE_VOICES_DIR=/voices PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" HF_HOME=/models SERVICE_HOST=0.0.0.0 SERVICE_PORT=29323
WORKDIR /app

COPY pyproject.toml uv.lock ./
# uv.lock pins torch to the CPU-only index (see pyproject.toml), so no CUDA/Triton wheels are pulled.
RUN uv sync --frozen --no-dev
RUN python -c "import torch; assert torch.version.cuda is None and torch.version.hip is None, 'CPU-only torch required'"
COPY src ./src
COPY web ./web

EXPOSE 29323
CMD ["python", "src/app.py"]
