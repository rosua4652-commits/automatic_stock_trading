@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo  AIDI - PC install verify (no server needed)
echo  ===========================================
echo  Folder: %CD%
echo.

if not exist "backend\app\main.py" (
  echo [FAIL] Not project root
  pause
  exit /b 1
)

findstr /C:"AIDI_BUILD" "backend\app\main.py" >nul 2>&1
if errorlevel 1 (
  echo [FAIL] Disk: OLD main.py - no AIDI_BUILD
  echo        GitHub ZIP did NOT apply to this folder.
  goto fix
)

findstr /C:"2026-03-30-pc-dongil3-final" "backend\app\main.py" >nul 2>&1
if errorlevel 1 (
  echo [WARN] Disk: AIDI_BUILD exists but not latest final build
  findstr "AIDI_BUILD" "backend\app\main.py"
) else (
  echo [OK] Disk: latest build in main.py
)

findstr /C:"HS512" "backend\app\market\upbit_auth.py" >nul 2>&1
if errorlevel 1 (
  echo [FAIL] Disk: upbit_auth.py missing HS512 - Upbit API will fail
) else (
  echo [OK] Disk: Upbit HS512 auth present
)

echo.
curl -s http://127.0.0.1:8000/api/version 2>nul | findstr /i "2026-03-30-pc-dongil3-final" >nul 2>&1
if not errorlevel 1 (
  echo [OK] Server: running latest build
  goto probe
)

curl -s http://127.0.0.1:8000/api/version 2>nul | findstr /i "not found error" >nul 2>&1
if not errorlevel 1 (
  echo [FAIL] Server: OLD - returns error not found
  echo        Ctrl+C run.bat, copy latest files, run.bat again
  goto fix
)

curl -s http://127.0.0.1:8000/api/status >nul 2>&1
if errorlevel 1 (
  echo [INFO] Server not running - start run.bat after disk is OK
) else (
  echo [WARN] Server running but build unknown - restart run.bat
)

:probe
if not exist "backend\.venv\Scripts\python.exe" (
  echo.
  echo [INFO] Run run.bat once, then probe-upbit.bat for API keys
  goto endpause
)
echo.
echo [Upbit probe - saved keys]
"backend\.venv\Scripts\python.exe" scripts\probe_upbit.py
goto endpause

:fix
echo.
echo Fix: PC_폴더6_구버전_해결.txt / apply-manual-zip.bat
echo.

:endpause
pause
