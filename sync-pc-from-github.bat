@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo  AIDI - sync PC folder from GitHub
echo  ==================================
echo  Folder: %CD%
echo.

if not exist "backend\app\main.py" goto wrongfolder

if exist "pc-path.txt" (
  echo Expected path ^(pc-path.txt^):
  type "pc-path.txt"
  echo.
)

where git >nul 2>&1
if errorlevel 1 goto no_git

echo [git pull origin main]
git pull origin main
if errorlevel 1 goto pull_fail

echo.
echo  OK. Next: run SETUP_PC.bat or run.bat
echo  Keep backend\data\credentials.json if you had API keys saved.
echo.
pause
exit /b 0

:no_git
echo git not found. Download ZIP from:
echo   https://github.com/rosua4652-commits/automatic_stock_trading
echo Extract over THIS folder ^(keep backend\data\credentials.json^).
echo.
pause
exit /b 1

:pull_fail
echo git pull failed. Use ZIP download instead.
pause
exit /b 1

:wrongfolder
echo ERROR: backend\app\main.py not found.
echo Open folder (3) inner automatic_stock_trading-main
pause
exit /b 1
