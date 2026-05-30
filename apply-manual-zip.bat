@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo  AIDI - apply ZIP from GitHub website
echo  ====================================
echo.

if not exist "backend\app\main.py" (
  echo ERROR: run from project folder with run.bat
  pause
  exit /b 1
)

if "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply-manual-zip.ps1"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply-manual-zip.ps1" -ZipPath "%~1"
)
exit /b %ERRORLEVEL%
