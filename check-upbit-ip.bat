@echo off
setlocal EnableDelayedExpansion
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

echo [2] Outbound IP for Upbit whitelist (AIDI server):
set "NET_OUT="
for /f "delims=" %%A in ('curl -s http://127.0.0.1:8000/api/network/outbound-ip 2^>nul') do set "NET_OUT=%%A"
if defined NET_OUT (
  echo !NET_OUT!
  echo !NET_OUT! | findstr /i "outbound_ipv4_stack outbound_ip" >nul 2>&1
  if not errorlevel 1 goto :net_ok
  echo !NET_OUT! | findstr /i "api_not_found not_found" >nul 2>&1
  if not errorlevel 1 goto :net_fallback
) else (
  goto :net_fallback
)
:net_ok
echo.
goto :net_done

:net_fallback
echo   (Old AIDI build - /api/network/* missing. Using fallbacks.)
echo.
echo [2b] From /api/status - network field:
powershell -NoProfile -Command "try { $s=Invoke-RestMethod 'http://127.0.0.1:8000/api/status'; if ($s.network) { $s.network | ConvertTo-Json -Compress } else { 'network field missing - update code and restart run.bat' } } catch { $_.Exception.Message }" 2>nul
echo.
echo [2c] This PC public IP (curl - same network as browser):
for /f "delims=" %%B in ('curl -s --max-time 8 https://api.ipify.org 2^>nul') do (
  echo   %%B  ^<- register THIS on Upbit if AIDI network field is empty
)
echo.

:net_done
echo [3] Full diagnose:
set "DIAG="
for /f "delims=" %%C in ('curl -s http://127.0.0.1:8000/api/network/diagnose 2^>nul') do set "DIAG=%%C"
if defined DIAG (
  echo !DIAG!
) else (
  echo   not available - update from GitHub and restart run.bat
)
echo.
echo.

echo Checklist:
echo   1. Register outbound_ipv4_stack (or [2c] IP) on Upbit Open API for YOUR key
echo   2. Key in AIDI must match Upbit - see saved_access_key / api_access_key_masked
echo   3. Settings: paste BOTH keys - Save - Connection test
echo   4. Turn off VPN; wait 1-2 min after Upbit IP change
echo.
echo If api_not_found: stop run.bat, pull latest ZIP, run run.bat again.
echo.
pause
endlocal
