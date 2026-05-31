@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo  AIDI - restart (log mode)
echo  =======================
echo.

call "%~dp0stop-aidi.bat"
timeout /t 2 /nobreak >nul

echo Starting run-log.bat ...
start "AIDI Log Server" cmd /k "%~dp0run-log.bat"
exit /b 0
