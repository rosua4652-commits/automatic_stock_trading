@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
if not exist "logs\aidi-server.log" (
  echo 로그 없음. run-log.bat 으로 서버를 먼저 실행하세요.
  pause
  exit /b 1
)
echo 실시간 로그 — logs\aidi-server.log  (Ctrl+C 종료)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath '%CD%\logs\aidi-server.log' -Wait -Tail 60 -Encoding UTF8"
