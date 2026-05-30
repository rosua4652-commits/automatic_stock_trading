@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo  AIDI build check
echo  ================
echo  Folder: %CD%
echo.

if not exist "backend\app\main.py" (
  echo ERROR: backend\app\main.py 없음. run.bat 이 있는 폴더에서 실행하세요.
  pause
  exit /b 1
)

if exist "backend\.venv\Scripts\python.exe" (
  echo [Python - saved code]
  "backend\.venv\Scripts\python.exe" -c "from app.main import AIDI_BUILD; print('AIDI_BUILD=', AIDI_BUILD)" 2>nul
  if errorlevel 1 echo   ^(구버전 - AIDI_BUILD 없음^)
  echo.
)

curl -s http://127.0.0.1:8000/api/version >nul 2>&1
if errorlevel 1 (
  echo [Server] not running - start run.bat first for live check
  echo.
  pause
  exit /b 0
)

echo [Server /api/version]
curl -s http://127.0.0.1:8000/api/version
echo.
echo.
echo [Server /api/network/outbound-ip]
curl -s http://127.0.0.1:8000/api/network/outbound-ip
echo.
echo.
echo OK if version shows build 2026-03-24-pc-upbit and outbound_ip JSON not error not_found
echo.
pause
