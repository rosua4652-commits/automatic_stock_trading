@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>nul
set "PORT=8000"
if not "%PORT_OVERRIDE%"=="" set "PORT=%PORT_OVERRIDE%"

set "SILENT=0"
if /i "%~1"=="silent" set "SILENT=1"
if /i "%~1"=="/silent" set "SILENT=1"

if "%SILENT%"=="0" (
  echo Stopping AIDI on port %PORT%...
)

set "FOUND=0"
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%PORT%" ^| findstr LISTENING') do (
  set "FOUND=1"
  if "%SILENT%"=="0" echo   PID %%a
  taskkill /F /PID %%a 2>nul
)

if "%FOUND%"=="0" (
  if "%SILENT%"=="0" echo   No process listening on port %PORT%.
) else (
  timeout /t 2 /nobreak >nul
  if "%SILENT%"=="0" echo Done.
)

exit /b 0
