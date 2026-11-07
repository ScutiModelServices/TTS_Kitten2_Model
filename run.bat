@echo off
REM Starts the kitten2 service on port 9250 (syncs .venv with uv on each run). The first start downloads about 1 GB of weights. Runs on the CPU.
REM LABEL: Kitten2 TTS Service
REM DESCRIPTION: Shared HTTP service that runs KittenTTS 2 text to speech with voice cloning on the CPU for every project.

cd /d "%~dp0"

uv sync
if errorlevel 1 (
    echo uv sync failed. Install uv: winget install astral-sh.uv
    pause
    exit /b 1
)
REM kittenml reads some files without an encoding; Windows would use its legacy code page and fail.
set PYTHONUTF8=1
".venv\Scripts\python.exe" src/app.py
pause
