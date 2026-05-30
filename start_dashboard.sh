#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f ".env" ]; then
  echo "[INFO] .env file not found. Creating it from .env.example."
  cp ".env.example" ".env"
  echo "[WARN] Open .env and add UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY, and CURSOR_API_KEY."
fi

USE_VENV=true

if [ ! -x ".venv/bin/python" ] || [ ! -f ".venv/bin/activate" ]; then
  echo "[INFO] Creating Python virtual environment..."
  rm -rf ".venv"
  if ! python3 -m venv .venv; then
    echo "[WARN] Could not create .venv. Falling back to system Python with PYTHONPATH=src."
    USE_VENV=false
  fi
fi

if [ "$USE_VENV" = true ] && [ -x ".venv/bin/python" ] && [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"

  echo "[INFO] Installing/updating local package..."
  python -m pip install --upgrade pip
  python -m pip install -e .
else
  export PYTHONPATH="${PWD}/src:${PYTHONPATH:-}"
  PYTHON_BIN="python3"
fi

echo "[INFO] Starting AI Upbit Scalper dashboard..."
echo "[INFO] Browser URL: http://localhost:8080"

if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "http://localhost:8080" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then
  open "http://localhost:8080" >/dev/null 2>&1 || true
fi

"${PYTHON_BIN:-python}" -m upbit_scalper.cli web --host 127.0.0.1 --port 8080
