@echo off
chcp 65001 >nul 2>nul
setlocal
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git not installed. Use update-zip.bat instead.
  pause
  exit /b 1
)

if not exist "backend\app\main.py" (
  echo ERROR: Run from project root ^(backend\app\main.py missing^).
  pause
  exit /b 1
)

echo.
echo  AIDI — git sync with GitHub main
echo  =================================
echo  Folder: %CD%
echo.

if not exist ".git" (
  echo Initializing git...
  git init
  if errorlevel 1 goto :fail
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin https://github.com/rosua4652-commits/automatic_stock_trading.git
) else (
  git remote set-url origin https://github.com/rosua4652-commits/automatic_stock_trading.git
)

echo Fetching origin...
git fetch origin
if errorlevel 1 goto :fail

echo Switching to main and matching GitHub...
git checkout -f -B main origin/main
if errorlevel 1 goto :fail

git branch --set-upstream-to=origin/main main
if errorlevel 1 goto :fail

echo.
echo  OK. Local branch: main  ^(tracks origin/main^)
for /f "delims=" %%b in ('findstr /R "AIDI_BUILD" backend\app\main.py') do echo  %%b
echo.
echo  Next: run.bat
echo.
pause
exit /b 0

:fail
echo.
echo  ERROR: git sync failed.
echo  Try: update-zip.bat  ^(no git needed^)
echo.
pause
exit /b 1
