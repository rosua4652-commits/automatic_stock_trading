@echo off
cd /d "%~dp0"

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git not installed or not in PATH.
  pause
  exit /b 1
)

if not exist "backend\app\main.py" (
  echo ERROR: Run from project root. backend\app\main.py not found.
  pause
  exit /b 1
)

if not exist ".git" (
  echo ERROR: Not a git repository. Run git-sync.bat first.
  pause
  exit /b 1
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo ERROR: No remote "origin". Run git-sync.bat first.
  pause
  exit /b 1
)

call :ensure_git_identity
if errorlevel 1 exit /b 1

echo.
echo  AIDI - commit and push to GitHub (upload code)
echo  ================================================
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
echo  Current changes:
echo  ----------------
git status -s
echo.

git status --porcelain | findstr /R "." >nul 2>&1
if errorlevel 1 (
  echo  Nothing to commit. Pushing existing commits only...
  goto :do_push
)

set "MSG=%~1"
if not defined MSG (
  set /p MSG=Commit message: 
)
if not defined MSG (
  echo ERROR: Commit message required.
  pause
  exit /b 1
)

echo.
echo  Staging all tracked changes ^(backend\data\ etc. stay ignored^)...
git add -A
if errorlevel 1 goto :fail

echo  Committing...
git commit -m "%MSG%"
if errorlevel 1 goto :fail

:do_push
echo.
echo  Pushing branch %BRANCH% to origin...
git push -u origin HEAD
if errorlevel 1 goto :push_fail

echo.
echo  OK. Committed and pushed to origin/%BRANCH%
echo  Note: backend\data\ is not in git — settings stay on this PC.
echo.
pause
exit /b 0

:push_fail
echo.
echo  ERROR: git push failed. Try git-sync.bat then run this again.
echo.
pause
exit /b 1

:fail
echo.
echo  ERROR: git add or commit failed.
echo  If you saw "Please tell me who you are", run this BAT again — it will ask name/email.
echo.
pause
exit /b 1

:ensure_git_identity
set "GIT_USER="
set "GIT_EMAIL="
for /f "delims=" %%a in ('git config user.name 2^>nul') do set "GIT_USER=%%a"
for /f "delims=" %%a in ('git config user.email 2^>nul') do set "GIT_EMAIL=%%a"
if defined GIT_USER if defined GIT_EMAIL exit /b 0

echo  Git author not set for this PC.
echo  Enter once — saved only in this project folder (not global).
echo.
if not defined GIT_USER set /p GIT_USER=Your name: 
if not defined GIT_EMAIL set /p GIT_EMAIL=Your email (GitHub account): 
if not defined GIT_USER (
  echo ERROR: Name required.
  pause
  exit /b 1
)
if not defined GIT_EMAIL (
  echo ERROR: Email required.
  pause
  exit /b 1
)
git config user.name "%GIT_USER%"
git config user.email "%GIT_EMAIL%"
echo  Saved: %GIT_USER% ^<%GIT_EMAIL%^>
echo.
exit /b 0
