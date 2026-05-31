@echo off
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git not installed or not in PATH.
  echo Install Git, open a NEW CMD window, then run this again.
  echo Or use update-zip.bat instead.
  pause
  exit /b 1
)

if not exist "backend\app\main.py" (
  echo ERROR: Run from project root. backend\app\main.py not found.
  pause
  exit /b 1
)

echo.
echo  AIDI - git sync with GitHub main
echo  =================================
echo  Folder: %CD%
echo.

if not exist ".git" (
  echo Initializing git...
  git init
  if errorlevel 1 goto fail
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin https://github.com/rosua4652-commits/automatic_stock_trading.git
) else (
  git remote set-url origin https://github.com/rosua4652-commits/automatic_stock_trading.git
)

echo Fetching origin...
git fetch origin
if errorlevel 1 goto fail

echo Switching to main...
git checkout -f -B main origin/main
if errorlevel 1 goto fail

git branch --set-upstream-to=origin/main main
if errorlevel 1 goto fail

echo.
echo  Note: backend\data\ (user_settings.json, credentials, portfolios) is NOT in git — kept on PC.
echo.
echo  OK. Branch main tracks origin/main
for /f "tokens=2 delims==" %%a in ('findstr /B /C:"AIDI_BUILD =" backend\app\main.py') do echo  Build %%a
echo.
echo  Next: run.bat
echo.
pause
exit /b 0

:fail
echo.
echo  ERROR: git sync failed. Try update-zip.bat
echo.
pause
exit /b 1
