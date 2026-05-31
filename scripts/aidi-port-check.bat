@echo off
REM Returns ERRORLEVEL 0 if port is free, 1 if in use
setlocal
set "PORT=%~1"
if "%PORT%"=="" set "PORT=8000"
netstat -ano 2>nul | findstr ":%PORT%" | findstr LISTENING >nul
if errorlevel 1 (
  endlocal & exit /b 0
)
endlocal & exit /b 1
