@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo  AIDI - PC setup (one-click)
echo  ===========================
echo  Folder: %CD%
echo.

if not exist "backend\app\main.py" goto wrongfolder

echo [OK] Project folder - run.bat is here.
echo.

where py >nul 2>&1
if errorlevel 1 goto checkpython
py -3.12 --version >nul 2>&1
if errorlevel 1 goto checkpython
echo [OK] Python 3.12 (py -3.12)
goto pyok

:checkpython
where python >nul 2>&1
if errorlevel 1 goto needpy
python -c "import sys; raise SystemExit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1
if errorlevel 1 goto needpy312
echo [OK] Python 3.12 (python)
goto pyok

:needpy
echo [ERROR] Python not found. Install 3.12 from https://www.python.org/downloads/
echo         Check "Add python.exe to PATH"
goto endpause

:needpy312
echo [ERROR] Python 3.12 required. Do not use 3.14.
echo         Install 3.12 then delete folder backend\.venv and run this again.
goto endpause

:pyok
echo.
echo [2] Starting run.bat (venv + server)...
echo     If you see errors like 'l' or 'exist', download latest ZIP from GitHub
echo     or run: powershell -ExecutionPolicy Bypass -File run.ps1
echo.
call "%~dp0run.bat"
goto :eof

:wrongfolder
echo [ERROR] backend\app\main.py not found.
echo         Open the INNER folder that contains run.bat, for example:
echo         ...\automatic_stock_trading-main\automatic_stock_trading-main
echo.
goto endpause

:endpause
pause
exit /b 1
