@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo  AIDI - PC files update from GitHub (no git required)
echo  =====================================================
echo  This folder: %CD%
echo.

if not exist "backend\app\main.py" (
  echo ERROR: Open the folder that contains run.bat first.
  if exist "pc-path.txt" type "pc-path.txt"
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download-latest-pc.ps1"
exit /b %ERRORLEVEL%
