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
echo  Stop     : Ctrl+C
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

echo [%date% %time%] === AIDI start (log mode) port %PORT% ===>>"%LOG_MAIN%"
echo [%date% %time%] === AIDI start (log mode) port %PORT% ===>>"%LOG_DAY%"

cd /d "%~dp0backend"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\aidi-log-run.ps1" -Port %PORT% -LogMain "%~dp0%LOG_MAIN%" -LogDay "%~dp0%LOG_DAY%"
set "EC=!ERRORLEVEL!"
cd /d "%~dp0"
echo [%date% %time%] === exit code !EC! ===>>"%LOG_MAIN%"
echo [%date% %time%] === exit code !EC! ===>>"%LOG_DAY%"
exit /b !EC!
