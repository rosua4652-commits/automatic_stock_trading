@echo off
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo  AIDI - PC folder check
echo  ======================
echo  Current: %CD%
echo.

if not exist "backend\app\main.py" (
  echo [FAIL] Not the project root - no backend\app\main.py
  goto endpause
)

if not exist "pc-path.txt" (
  echo [WARN] pc-path.txt missing
  goto ok_root
)

set "EXPECTED="
for /f "usebackq delims=" %%L in ("pc-path.txt") do set "EXPECTED=%%L"
if not defined EXPECTED goto ok_root

if /i "%CD%"=="%EXPECTED%" (
  echo [OK] Matches pc-path.txt
) else (
  echo [WARN] Different from pc-path.txt:
  echo        %EXPECTED%
  echo        You can still run here if run.bat exists.
)

:ok_root
echo [OK] Project root files present.
if exist "run.bat" echo [OK] run.bat
if exist "SETUP_PC.bat" echo [OK] SETUP_PC.bat
echo.
goto endpause

:endpause
pause
