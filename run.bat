@echo off
setlocal
cd /d "%~dp0"
set "PORT=8000"
if not "%PORT_OVERRIDE%"=="" set "PORT=%PORT_OVERRIDE%"

echo.
echo  AIDI - Windows
echo  ===============
echo.

set "PYEXE=python"
where python >nul 2>&1
if errorlevel 1 goto :no_python

where py >nul 2>&1
if not errorlevel 1 (
  py -3.12 -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PYEXE=py -3.12"
)

call :check_py_version %PYEXE%
if errorlevel 1 goto :bad_python

if not exist "backend\app\main.py" goto :no_root

if exist "backend\.venv\Scripts\python.exe" (
  call :check_py_version "backend\.venv\Scripts\python.exe"
  if errorlevel 1 (
    echo Removing old venv - wrong Python version...
    rmdir /s /q "backend\.venv"
  )
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo Creating venv with %PYEXE% ...
  %PYEXE% -m venv backend\.venv
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

:check_py_version
%1 -c "import sys; v=sys.version_info; raise SystemExit(0 if (3,11)<=v[:2]<(3,14) else 1)"
exit /b %errorlevel%

:no_python
echo ERROR: Python not found.
echo Install Python 3.12 from https://www.python.org/downloads/
echo Check "Add python.exe to PATH" during install.
pause
exit /b 1

:bad_python
echo.
echo ERROR: Need Python 3.11 or 3.12 only.
echo Python 3.14 is NOT supported - pydantic install fails.
echo.
echo Fix:
echo   1. Install Python 3.12 from python.org
echo   2. cmd: rmdir /s /q backend\.venv
echo   3. Run run.bat again
echo.
echo Check version: python --version
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
echo.
echo ERROR: pip install failed.
echo If you saw pydantic-core / Python 3.14 error:
echo   Use Python 3.12, delete backend\.venv, run again.
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
