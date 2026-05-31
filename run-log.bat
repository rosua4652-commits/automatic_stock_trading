@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>nul
cd /d "%~dp0"
set "PORT=8000"
if not "%PORT_OVERRIDE%"=="" set "PORT=%PORT_OVERRIDE%"

if not exist "backend\app\main.py" (
  echo ERROR: backend\app\main.py not found. Run from project root.
  pause
  exit /b 1
)

if not exist "logs" mkdir "logs"
set "LOG_MAIN=logs\aidi-server.log"
for /f "delims=" %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%d"
set "LOG_DAY=logs\aidi-!TODAY!.log"

echo.
echo  AIDI - log mode
echo  ==============
echo  Main log : %CD%\%LOG_MAIN%
echo  Today    : %CD%\%LOG_DAY%
echo  Browser  : http://127.0.0.1:%PORT%
echo  View log : logs-aidi.bat  (option 1)
echo  Detail   : buttons, scan, backtest  (chart poll hidden)
echo  Stop     : Ctrl+C in this window
echo.

if not exist "backend\.venv\Scripts\python.exe" (
  echo venv not found. Run run.bat once first to install.
  pause
  exit /b 1
)

if not exist "frontend\dist\index.html" (
  echo frontend\dist missing. Run run.bat once first.
  pause
  exit /b 1
)

if not exist "backend\data" mkdir "backend\data"

call "%~dp0scripts\aidi-port-check.bat" %PORT%
if errorlevel 1 (
  echo  [!] Port %PORT% is already in use.
  echo      Another run.bat window may be open.
  echo      Stopping old server on port %PORT% ...
  call "%~dp0stop-aidi.bat" silent
  timeout /t 2 /nobreak >nul
  call "%~dp0scripts\aidi-port-check.bat" %PORT%
  if errorlevel 1 (
    echo.
    echo  ERROR: Port %PORT% still busy.
    echo  Close other AIDI window or run: stop-aidi.bat
    echo  Then run run-log.bat again.
    pause
    exit /b 1
  )
  echo  Port %PORT% is free now.
  echo.
)

echo [%date% %time%] === AIDI start (log mode) port %PORT% ===>>"%LOG_MAIN%"
echo [%date% %time%] === AIDI start (log mode) port %PORT% ===>>"%LOG_DAY%"

cd /d "%~dp0backend"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\aidi-log-run.ps1" -Port %PORT% -LogMain "%~dp0%LOG_MAIN%" -LogDay "%~dp0%LOG_DAY%"
set "EC=!ERRORLEVEL!"
cd /d "%~dp0"
echo [%date% %time%] === exit code !EC! ===>>"%LOG_MAIN%"
echo [%date% %time%] === exit code !EC! ===>>"%LOG_DAY%"

if not "!EC!"=="0" (
  echo.
  echo  ERROR: Server failed to start ^(exit !EC!^).
  echo  Common cause: port %PORT% still in use.
  echo  Fix: stop-aidi.bat  then run-log.bat again
  echo  Log: %LOG_MAIN%
  pause
  exit /b !EC!
)

exit /b 0
