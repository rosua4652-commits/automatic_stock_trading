@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo  AIDI - restart server (use after updating files)
echo  =================================================
echo  Folder: %CD%
echo.

call "%~dp0stop-aidi.bat" silent

timeout /t 2 /nobreak >nul

echo Starting run.bat ...
echo.
start "AIDI Server" cmd /k "%~dp0run.bat"
exit /b 0
