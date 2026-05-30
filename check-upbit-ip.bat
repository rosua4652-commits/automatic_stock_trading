@echo off
chcp 65001 >nul 2>nul
echo.
echo  AIDI - Upbit IP check
echo  =====================
echo.

curl -s http://127.0.0.1:8000/api/status >nul 2>&1
if errorlevel 1 (
  echo ERROR: Server not running. Start run.bat first.
  pause
  exit /b 1
)

echo [1] Server OK - /api/status
curl -s http://127.0.0.1:8000/api/status
echo.
echo.

echo [2] Outbound IP for Upbit whitelist:
curl -s http://127.0.0.1:8000/api/network/outbound-ip
echo.
echo.

echo [3] Full diagnose:
curl -s http://127.0.0.1:8000/api/network/diagnose
echo.
echo.

echo If you see api_not_found - stop run.bat, get latest ZIP from GitHub, run run.bat again.
echo Register outbound_ipv4_stack on Upbit Open API for YOUR new key.
echo.
pause
