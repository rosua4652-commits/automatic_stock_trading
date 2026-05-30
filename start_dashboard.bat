@echo off
setlocal

cd /d "%~dp0"

if not exist ".env" (
  echo [INFO] .env file not found. Creating it from .env.example.
  copy ".env.example" ".env" >nul
  echo [WARN] Open .env and add UPBIT_ACCESS_KEY, UPBIT_SECRET_KEY, and CURSOR_API_KEY.
)

if not exist ".venv\Scripts\python.exe" (
  echo [INFO] Creating Python virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment. Install Python 3.11+ and try again.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"

echo [INFO] Installing/updating local package...
python -m pip install --upgrade pip
python -m pip install -e .
if errorlevel 1 (
  echo [ERROR] Package install failed.
  pause
  exit /b 1
)

echo [INFO] Starting AI Upbit Scalper dashboard...
echo [INFO] Browser URL: http://localhost:8080
start "" "http://localhost:8080"
python -m upbit_scalper.cli web --host 127.0.0.1 --port 8080

pause
