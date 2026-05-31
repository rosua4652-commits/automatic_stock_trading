@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\aidi-update-zip.ps1" -RepoRoot "%CD%"
if errorlevel 1 pause
exit /b %ERRORLEVEL%
