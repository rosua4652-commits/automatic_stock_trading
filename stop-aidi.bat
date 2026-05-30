@echo off
chcp 65001 >nul 2>nul
echo.
echo  AIDI - stop server on port 8000
echo  ================================
echo.

set "PORT=8000"
if not "%PORT_OVERRIDE%"=="" set "PORT=%PORT_OVERRIDE%"

echo Checking port %PORT%...
set "FOUND=0"
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
  set "FOUND=1"
  echo Killing PID %%P ...
  taskkill /PID %%P /F >nul 2>&1
)

if "%FOUND%"=="0" (
  echo No process listening on port %PORT%.
  echo If run.bat is open, press Ctrl+C in that window too.
) else (
  echo Done. Wait 2 seconds, then run run.bat
)

echo.
if /i not "%~1"=="silent" pause
