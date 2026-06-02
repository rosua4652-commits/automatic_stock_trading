@echo off
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git not installed or not in PATH.
  echo Install Git, open a NEW CMD window, then run this again.
  pause
  exit /b 1
)

if not exist "backend\app\main.py" (
  echo ERROR: Run from project root. backend\app\main.py not found.
  pause
  exit /b 1
)

if not exist ".git" (
  echo ERROR: Not a git repository.
  echo Run git-sync.bat first to connect this folder to GitHub.
  pause
  exit /b 1
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo ERROR: No remote "origin".
  echo Run git-sync.bat to add origin, or: git remote add origin ^<your-repo-url^>
  pause
  exit /b 1
)

echo.
echo  AIDI - git push only (already committed)
echo  ========================================
echo  To upload NEW files: run git-commit-push.bat instead.
echo  Folder: %CD%
echo.

for /f "delims=" %%b in ('git branch --show-current 2^>nul') do set "BRANCH=%%b"
if not defined BRANCH (
  echo ERROR: Could not detect current branch.
  pause
  exit /b 1
)

echo  Branch: %BRANCH%
for /f "delims=" %%u in ('git remote get-url origin 2^>nul') do echo  Remote: %%u
echo.
echo  Status before push:
echo  --------------------
git status
echo.

git status --porcelain | findstr /R "." >nul 2>&1
if not errorlevel 1 (
  echo  STOP: Uncommitted changes were NOT pushed to GitHub.
  echo.
  echo  Commit and push now?  [Y/N]
  choice /C YN /N /M "  "
  if errorlevel 2 goto :push_stopped
  echo.
  call "%~dp0git-commit-push.bat"
  exit /b %ERRORLEVEL%
)

goto :do_push

:push_stopped
echo.
echo  Cancelled. Run git-commit-push.bat when ready to upload.
echo.
pause
exit /b 2

:do_push
echo  Pushing branch %BRANCH% to origin...
echo.
git push -u origin HEAD
if errorlevel 1 goto :push_fail

echo.
echo  OK. Pushed to origin/%BRANCH%
echo  Note: backend\data\ is not in git — only code changes are pushed.
echo.
pause
exit /b 0

:push_fail
echo.
echo  ERROR: git push failed.
echo.
echo  Common fixes:
echo    - Commit first:  git add -A   then   git commit -m "your message"
echo    - Pull first:    git-sync.bat   or   git pull --ff-only origin main
echo    - Auth: sign in to GitHub (browser / PAT / gh auth login)
echo    - Rejected: remote has newer commits — pull, resolve, then push again
echo.
echo  This script never force-pushes. Do not use git push --force unless you know why.
echo.
pause
exit /b 1
