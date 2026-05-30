@echo off
echo Stopping AIDI on port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do (
  taskkill /F /PID %%a 2>nul
)
timeout /t 2 /nobreak >nul
echo Done.
