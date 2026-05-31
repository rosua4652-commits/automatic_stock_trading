@echo off
cd /d "%~dp0"
echo.
echo  Adds missing frontend\ and scripts\ — keeps backend\data
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\aidi-update-zip.ps1" -RepoRoot "%CD%"
if errorlevel 1 pause
exit /b %ERRORLEVEL%
