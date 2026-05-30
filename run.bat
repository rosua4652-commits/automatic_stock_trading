@echo off
setlocal
cd /d "%~dp0"
set "PORT=8000"
if not "%PORT_OVERRIDE%"=="" set "PORT=%PORT_OVERRIDE%"

echo.
echo  AIDI - Windows
echo  ===============
echo.

where python >nul 2>&1
if errorlevel 1 goto :no_python

if not exist "backend\app\main.py" goto :no_root

if not exist "backend\.venv\Scripts\python.exe" (
  echo Creating venv...
  python -m venv backend\.venv
  if errorlevel 1 goto :venv_fail
)

echo Installing Python packages...
"backend\.venv\Scripts\python.exe" -m pip install -q --upgrade pip
"backend\.venv\Scripts\pip.exe" install -q --no-cache-dir -r backend\requirements.txt
if errorlevel 1 goto :pip_fail

if exist "frontend\dist\index.html" goto :have_dist

where npm >nul 2>&1
if errorlevel 1 goto :no_npm

echo Building frontend - first time may take a few minutes...
if not exist "frontend\node_modules" (
  pushd frontend
  call npm install
  if errorlevel 1 goto :npm_fail
  popd
)
pushd frontend
call npm run build
if errorlevel 1 goto :npm_fail
popd

:have_dist
if not exist "frontend\dist\index.html" goto :no_dist

if not exist "backend\data" mkdir "backend\data"

echo.
echo  Open in browser: http://127.0.0.1:%PORT%
echo  Tablet same Wi-Fi: http://YOUR-PC-IP:%PORT%
echo  Stop server: Ctrl+C in this window
echo.

cd /d "%~dp0backend"
"%~dp0backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
goto :eof

:no_python
echo ERROR: Python not found.
echo Install Python 3.11+ from https://www.python.org/downloads/
echo Check "Add python.exe to PATH" during install.
pause
exit /b 1

:no_root
echo ERROR: Run this from the project folder - backend\app\main.py not found.
pause
exit /b 1

:venv_fail
echo ERROR: Failed to create venv.
pause
exit /b 1

:pip_fail
echo ERROR: pip install failed.
pause
exit /b 1

:no_npm
echo ERROR: frontend\dist missing and npm not found.
echo Install Node.js from https://nodejs.org/ OR use zip with dist included.
pause
exit /b 1

:npm_fail
popd 2>nul
echo ERROR: npm failed.
pause
exit /b 1

:no_dist
echo ERROR: frontend\dist\index.html not found.
pause
exit /b 1
