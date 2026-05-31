@echo off
cd /d "%~dp0.."
call "%~dp0aidi-console-utf8.bat"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0aidi-prep.ps1" -RepoRoot "%CD%"
exit /b %ERRORLEVEL%
