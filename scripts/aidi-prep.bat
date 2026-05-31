@echo off
setlocal
cd /d "%~dp0.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0aidi-prep.ps1" -RepoRoot "%CD%"
exit /b %ERRORLEVEL%
