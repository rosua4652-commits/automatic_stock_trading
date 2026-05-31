@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>nul
cd /d "%~dp0"
set "PORT=8000"
if not "%PORT_OVERRIDE%"=="" set "PORT=%PORT_OVERRIDE%"

echo.
echo  AIDI - Windows
echo  ===============
echo.

if not exist "backend\app\main.py" goto :no_root

call "%~dp0scripts\aidi-prep.bat"
set "PREP_EC=%ERRORLEVEL%"
if not "%PREP_EC%"=="0" (
  if "%PREP_EC%"=="3" (
    echo.
    echo  GitHub ZIP으로 폴더를 덮어쓴 뒤 run.bat 을 다시 실행하세요.
  )
  pause
  exit /b %PREP_EC%
)

call "%~dp0scripts\aidi-port-check.bat" %PORT%
if errorlevel 1 (
  echo  Port %PORT% in use — stopping old server...
  call "%~dp0stop-aidi.bat" silent
  timeout /t 2 /nobreak >nul
)

echo  Browser: http://127.0.0.1:%PORT%
echo  Log mode: run-log.bat  ^|  Logs: logs-aidi.bat
echo  Stop: Ctrl+C
echo.

cd /d "%~dp0backend"
"%~dp0backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
goto :eof

:no_root
echo ERROR: Run from project folder - backend\app\main.py not found.
pause
exit /b 1
