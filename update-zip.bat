@echo off
cd /d "%~dp0"
echo.
echo  ZIP update + npm build — keeps backend\data
echo  Min buy setting: http://127.0.0.1:8000/min-buy-setting
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\aidi-update-zip.ps1" -RepoRoot "%CD%"
if errorlevel 1 pause
exit /b %ERRORLEVEL%
