@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo ERROR: backend\.venv 없음. 먼저 run.bat 을 한 번 실행하세요.
  pause
  exit /b 1
)
echo.
"backend\.venv\Scripts\python.exe" scripts\probe_upbit.py
echo.
pause
