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
if errorlevel 1 goto use_download

echo [git pull origin main]
git pull origin main
if errorlevel 1 goto use_download

echo.
echo  OK. Next: run SETUP_PC.bat or run.bat
echo.
pause
exit /b 0

:use_download
echo git 없거나 pull 실패 - download-latest-pc.bat 으로 PC 파일을 받습니다.
echo.
call "%~dp0download-latest-pc.bat"
exit /b %ERRORLEVEL%

:wrongfolder
echo ERROR: backend\app\main.py not found.
echo Open folder (3) inner automatic_stock_trading-main
pause
exit /b 1
