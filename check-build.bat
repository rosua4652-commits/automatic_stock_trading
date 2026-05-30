@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>nul
cd /d "%~dp0"
echo.
echo  AIDI build check
echo  ================
echo  Folder: %CD%
echo.

if not exist "backend\app\main.py" (
  echo ERROR: backend\app\main.py 없음. run.bat 이 있는 폴더에서 실행하세요.
  pause
  exit /b 1
)

set "DISK_OK=0"
findstr /C:"AIDI_BUILD" "backend\app\main.py" >nul 2>&1
if errorlevel 1 (
  echo [Disk] FAIL - 구버전 main.py ^(AIDI_BUILD 없음^)
) else (
  findstr /C:"upbit-only" "backend\app\main.py" >nul 2>&1
  if errorlevel 1 (
    echo [Disk] WARN - AIDI_BUILD 있으나 최신 빌드 ID 아님
    findstr "AIDI_BUILD" "backend\app\main.py"
  ) else (
    echo [Disk] OK - 최신 코드 파일 있음
    set "DISK_OK=1"
  )
)
echo.

if exist "backend\.venv\Scripts\python.exe" (
  echo [Python venv]
  pushd "%~dp0backend"
  ".venv\Scripts\python.exe" -c "from app.main import AIDI_BUILD; print('AIDI_BUILD=', AIDI_BUILD)" 2>nul
  if errorlevel 1 echo   ^(main.py import failed^)
  popd
  echo.
)

curl -s http://127.0.0.1:8000/api/status >nul 2>&1
if errorlevel 1 (
  echo [Server] not running - start run.bat first
  echo.
  if "!DISK_OK!"=="0" goto :need_update
  goto :endpause
)

set "VER_LINE="
for /f "usebackq delims=" %%A in (`curl -s http://127.0.0.1:8000/api/version 2^>nul`) do set "VER_LINE=%%A"
echo [Server /api/version]
if defined VER_LINE (echo !VER_LINE!) else (echo   ^(empty^))
echo.

set "NET_LINE="
for /f "usebackq delims=" %%B in (`curl -s http://127.0.0.1:8000/api/network/outbound-ip 2^>nul`) do set "NET_LINE=%%B"
echo [Server /api/network/outbound-ip]
if defined NET_LINE (echo !NET_LINE!) else (echo   ^(empty^))
echo.

set "OLD_SRV=0"
if defined VER_LINE echo !VER_LINE! | findstr /i "\"error\" not_found not found" >nul 2>&1 && set "OLD_SRV=1"
if defined NET_LINE echo !NET_LINE! | findstr /i "\"error\" not_found not found" >nul 2>&1 && set "OLD_SRV=1"

if "!OLD_SRV!"=="1" (
  echo ========================================
  echo  FAIL: 서버가 구버전입니다
  echo ========================================
  echo  run.bat 창에서 Ctrl+C 로 서버 종료
  echo  GitHub 로그인 - Code - Download ZIP
  echo  apply-manual-zip.bat 실행 ^(없으면 ZIP 압축해제 후 이 폴더에 복사^)
  echo  run.bat 다시 실행 후 check-build.bat
  echo  자세히: PC_404_해결.txt
  echo ========================================
  echo.
  goto :need_update
)

echo !VER_LINE! | findstr /i "upbit-only" >nul 2>&1
if errorlevel 1 (
  echo WARN: 서버 build ID 가 최신이 아닐 수 있음. run.bat 재시작.
) else (
  echo OK: 최신 서버 build 확인됨
)
echo.
goto :endpause

:need_update
if "!DISK_OK!"=="0" (
  echo [Disk] 이 폴더 파일도 구버전 - ZIP 으로 덮어쓰기 필요
  echo.
)
if exist "apply-manual-zip.bat" (
  echo Tip: apply-manual-zip.bat 를 실행하세요.
) else (
  echo Tip: GitHub ZIP 압축 해제 후 이 폴더에 파일 복사
  echo      ^(backend\data\credentials.json 은 유지^)
)

:endpause
pause
endlocal
