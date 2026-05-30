@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "PORT=8000"
if not "%PORT_OVERRIDE%"=="" set "PORT=%PORT_OVERRIDE%"

echo.
echo  AIDI Windows 실행
echo  ==================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [오류] Python이 없습니다.
  echo   https://www.python.org/downloads/ 에서 Python 3.11+ 설치
  echo   설치 시 "Add python.exe to PATH" 체크
  pause
  exit /b 1
)

if not exist "backend\app\main.py" (
  echo [오류] backend 폴더를 찾을 수 없습니다. 프로젝트 루트에서 실행하세요.
  pause
  exit /b 1
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo 가상환경 생성 중...
  python -m venv backend\.venv
  if errorlevel 1 (
    echo [오류] venv 생성 실패
    pause
    exit /b 1
  )
)

echo Python 패키지 설치 중...
backend\.venv\Scripts\python.exe -m pip install -q --upgrade pip
backend\.venv\Scripts\pip.exe install -q -r backend\requirements.txt
if errorlevel 1 (
  echo [오류] pip install 실패
  pause
  exit /b 1
)

if exist "frontend\dist\index.html" (
  echo UI: frontend\dist 사용 ^(이미 빌드됨^)
) else (
  where npm >nul 2>&1
  if errorlevel 1 (
    echo [오류] frontend\dist 가 없고 Node.js/npm 도 없습니다.
    echo   Node.js 18+ 설치: https://nodejs.org/
    echo   또는 PC에서 npm run build 후 dist 폴더 포함해서 사용
    pause
    exit /b 1
  )
  echo 프론트엔드 빌드 중 ^(처음만 수 분^)...
  if not exist "frontend\node_modules" (
    pushd frontend
    call npm install
    if errorlevel 1 goto :npmfail
    popd
  )
  pushd frontend
  call npm run build
  if errorlevel 1 goto :npmfail
  popd
)

if not exist "frontend\dist\index.html" (
  echo [오류] frontend\dist\index.html 없음
  pause
  exit /b 1
)

if not exist "backend\data" mkdir backend\data

echo.
echo   브라우저에서 열기:
echo     http://127.0.0.1:%PORT%
echo.
echo   같은 Wi-Fi 태블릿에서: http://^<이 PC IP^>:%PORT%
echo   종료: 이 창에서 Ctrl+C
echo.

cd backend
backend\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port %PORT%
goto :eof

:npmfail
popd
echo [오류] npm 실패
pause
exit /b 1
