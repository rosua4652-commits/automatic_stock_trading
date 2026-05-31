@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "PORT=8000"
if not "%PORT_OVERRIDE%"=="" set "PORT=%PORT_OVERRIDE%"

echo.
echo  AIDI - Windows
echo  ===============
echo.

if not exist "backend\app\main.py" goto :no_root

set "PY312="
where py >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%i in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set "PY312=%%i"
)

if not defined PY312 (
  where python >nul 2>&1
  if errorlevel 1 goto :no_python
  for /f "delims=" %%i in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PY312=%%i"
  "%PY312%" -c "import sys; v=sys.version_info; raise SystemExit(0 if v[:2]==(3,12) else 1)" 2>nul
  if errorlevel 1 goto :bad_python
)

if not defined PY312 goto :bad_python

echo Using Python: %PY312%
"%PY312%" --version
if errorlevel 1 goto :bad_python

if exist "backend\.venv\Scripts\python.exe" (
  "backend\.venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" 2>nul
  if errorlevel 1 (
    echo Removing old venv - not Python 3.12...
    rmdir /s /q "backend\.venv"
  )
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo Creating venv with Python 3.12...
  "%PY312%" -m venv backend\.venv
  if errorlevel 1 goto :venv_fail
)

"backend\.venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" 2>nul
if errorlevel 1 (
  echo ERROR: venv is not Python 3.12. Delete backend\.venv and retry.
  goto :bad_python
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
echo  Frontend / backend build sync...
pushd "%~dp0backend"
for /f "delims=" %%b in ('".venv\Scripts\python.exe" -c "from app.main import AIDI_BUILD; print(AIDI_BUILD)" 2^>nul') do set "EXPECTED_BUILD=%%b"
popd
set "NEED_FE_BUILD=0"
if not defined EXPECTED_BUILD set "NEED_FE_BUILD=1"
if not exist "frontend\dist\.aidi-ui-build" set "NEED_FE_BUILD=1"
if "!NEED_FE_BUILD!"=="0" (
  set /p STAMPED=<frontend\dist\.aidi-ui-build
  if /i not "!STAMPED!"=="!EXPECTED_BUILD!" set "NEED_FE_BUILD=1"
)
if "!NEED_FE_BUILD!"=="1" (
  where npm >nul 2>&1
  if errorlevel 1 goto :fe_skip_rebuild
  echo  Rebuilding frontend - UI build !EXPECTED_BUILD!...
  if not exist "frontend\node_modules" (
    pushd frontend
    call npm install
    popd
  )
  pushd frontend
  call npm run build
  if errorlevel 1 goto :npm_fail
  popd
  echo !EXPECTED_BUILD!> frontend\dist\.aidi-ui-build
  findstr /C:"!EXPECTED_BUILD!" "frontend\dist\assets\index-*.js" >nul 2>&1
  if errorlevel 1 (
    echo   WARNING: Built JS does not contain !EXPECTED_BUILD! - run: cd frontend ^&^& npm run build
  )
)
:fe_skip_rebuild

echo.
echo  Build check...
pushd "%~dp0backend"
".venv\Scripts\python.exe" -c "from app.main import AIDI_BUILD; print('  AIDI_BUILD =', AIDI_BUILD)" 2>nul
if errorlevel 1 (
  echo   WARNING: Could not read AIDI_BUILD. Check backend\app\main.py
  popd
) else (
  echo   OK - backend loaded
  popd
)

echo.
echo  Open in browser: http://127.0.0.1:%PORT%
echo  Tablet same Wi-Fi: http://YOUR-PC-IP:%PORT%
echo  Stop server: Ctrl+C in this window
echo  Log file mode: run-log.bat  ^|  View logs: logs-aidi.bat
echo.

cd /d "%~dp0backend"
"%~dp0backend\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%
goto :eof

:no_python
echo ERROR: Python not found.
echo Install Python 3.12 from https://www.python.org/downloads/
pause
exit /b 1

:bad_python
echo.
echo ERROR: Python 3.12 required.
echo   py -3.12 --version  must work.
echo   Do NOT use Python 3.14.
echo.
echo Fix now:
echo   rmdir /s /q backend\.venv
echo   py -3.12 -m venv backend\.venv
echo   run.bat
pause
exit /b 1

:no_root
echo ERROR: Run from project folder - backend\app\main.py not found.
pause
exit /b 1

:venv_fail
echo ERROR: Failed to create venv.
pause
exit /b 1

:pip_fail
echo.
echo ERROR: pip install failed.
echo Check: backend\.venv\Scripts\python.exe --version  must be 3.12.x
pause
exit /b 1

:no_npm
echo ERROR: frontend\dist missing and npm not found.
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
