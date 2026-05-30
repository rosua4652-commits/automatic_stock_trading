@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo  AIDI - update from GitHub
echo  =========================
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo git 이 없습니다. GitHub에서 ZIP 다시 받아 이 폴더에 덮어쓰세요.
  echo https://github.com/rosua4652-commits/automatic_stock_trading
  pause
  exit /b 1
)

git pull origin main
if errorlevel 1 (
  echo git pull 실패. ZIP으로 최신 받기를 권장합니다.
  pause
  exit /b 1
)

echo.
echo  완료. run.bat 창을 Ctrl+C 로 끈 뒤 run.bat 을 다시 실행하세요.
echo  그 다음: probe-upbit.bat
echo.
pause
