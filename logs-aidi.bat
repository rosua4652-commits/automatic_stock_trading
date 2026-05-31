@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>nul
cd /d "%~dp0"

if not exist "logs" mkdir "logs"
set "LOG_MAIN=logs\aidi-server.log"

:menu
cls
echo.
echo   AIDI 로그
echo   =========
echo   폴더: %CD%\logs
echo.
if exist "%LOG_MAIN%" (
  for %%A in ("%LOG_MAIN%") do set "SZ=%%~zA"
  echo   메인 로그: %LOG_MAIN%  (!SZ! bytes^)
) else (
  echo   메인 로그: (아직 없음 — run-log.bat 으로 서버 실행^)
)
echo.
echo   1  실시간 로그 보기 (tail, Ctrl+C 종료)
echo   2  최근 150줄만 보기
echo   3  메모장으로 로그 열기
echo   4  로그 폴더 열기
echo   5  로그 파일 비우기 (백업 후 삭제)
echo   6  로그 모드로 서버 시작 (새 창, run-log.bat)
echo   7  일반 서버 시작 (run.bat)
echo   0  종료
echo.
set "CHO="
set /p CHO=선택 (0-7): 
if "%CHO%"=="1" goto :tail
if "%CHO%"=="2" goto :head
if "%CHO%"=="3" goto :notepad
if "%CHO%"=="4" goto :explorer
if "%CHO%"=="5" goto :clear
if "%CHO%"=="6" goto :runlog
if "%CHO%"=="7" goto :runnormal
if "%CHO%"=="0" exit /b 0
goto :menu

:tail
if not exist "%LOG_MAIN%" (
  echo.
  echo   로그 파일이 없습니다. 먼저 run-log.bat 으로 서버를 실행하세요.
  pause
  goto :menu
)
echo.
echo   실시간 로그 — %LOG_MAIN%
echo   Ctrl+C 로 메뉴로 돌아갑니다.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath '%CD%\%LOG_MAIN%' -Wait -Tail 60 -Encoding UTF8"
goto :menu

:head
if not exist "%LOG_MAIN%" (
  echo   로그 없음.
  pause
  goto :menu
)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -LiteralPath '%CD%\%LOG_MAIN%' -Tail 150 -Encoding UTF8"
echo.
pause
goto :menu

:notepad
if not exist "%LOG_MAIN%" (
  echo.> "%LOG_MAIN%"
  echo   빈 로그 파일을 만들었습니다.
)
start "" notepad "%CD%\%LOG_MAIN%"
goto :menu

:explorer
start "" explorer "%CD%\logs"
goto :menu

:clear
if not exist "%LOG_MAIN%" (
  echo   삭제할 로그 없음.
  pause
  goto :menu
)
set "BAK=logs\aidi-server-backup-%date:~-0,4%%date:~-5,2%%date:~-8,2%-%time:~0,2%%time:~3,2%%time:~6,2%.log"
set "BAK=!BAK: =0!"
copy /y "%LOG_MAIN%" "!BAK!" >nul
del /f /q "%LOG_MAIN%" 2>nul
echo   백업: !BAK!
echo   메인 로그를 비웠습니다.
pause
goto :menu

:runlog
echo   새 창에서 로그 모드 서버를 시작합니다...
start "AIDI Log Server" cmd /k "%~dp0run-log.bat"
timeout /t 2 /nobreak >nul
goto :menu

:runnormal
start "AIDI Server" cmd /k "%~dp0run.bat"
timeout /t 2 /nobreak >nul
goto :menu
