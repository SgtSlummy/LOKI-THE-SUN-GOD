@echo off
setlocal EnableExtensions
title Publish LOKI THE SUN GOD to GitHub
cd /d "%~dp0"

echo ============================================================
echo  Publish LOKI THE SUN GOD to GitHub
echo ============================================================
echo.
echo This creates a PRIVATE GitHub repo named:
echo   LOKI-THE-SUN-GOD
echo.
echo It pushes the current checked-out branch.
echo It does not add .env, dist, build, or venv files because they are gitignored.
echo.

where gh >nul 2>nul
if errorlevel 1 (
  echo ERROR: GitHub CLI 'gh' is not installed or not on PATH.
  echo Install it from: https://cli.github.com/
  pause
  exit /b 1
)

echo Checking GitHub authentication...
gh auth status >nul 2>nul
if errorlevel 1 (
  echo.
  echo You are not logged into GitHub CLI yet.
  echo A browser/device login will start now.
  echo Complete it, then return to this window.
  echo.
  gh auth login --hostname github.com --git-protocol https --web
  if errorlevel 1 (
    echo.
    echo ERROR: GitHub login did not complete.
    pause
    exit /b 1
  )
)

for /f "usebackq delims=" %%U in (`gh api user --jq ".login"`) do set "GH_USER=%%U"
if not defined GH_USER (
  echo ERROR: Could not determine GitHub username.
  pause
  exit /b 1
)

set "REPO_NAME=LOKI-THE-SUN-GOD"
set "OWNER_REPO=%GH_USER%/%REPO_NAME%"
set "REMOTE_URL=https://github.com/%OWNER_REPO%.git"

echo.
echo GitHub user: %GH_USER%
echo Target repo: %OWNER_REPO%
echo.

git remote get-url origin >nul 2>nul
if errorlevel 1 (
  echo No origin remote configured yet.
  echo Creating private repo and pushing current branch...
  gh repo create "%REPO_NAME%" --private --description "LOKI THE SUN GOD Discord bot, dashboard, desktop controller, and Hermes integration" --source . --remote origin --push
  if errorlevel 1 (
    echo.
    echo Repo create may have failed because it already exists. Trying to attach origin and push...
    git remote add origin "%REMOTE_URL%" 2>nul
    git push -u origin HEAD
    if errorlevel 1 (
      echo ERROR: Push failed.
      pause
      exit /b 1
    )
  )
) else (
  echo Existing origin remote:
  git remote -v
  echo.
  echo Pushing current branch to origin...
  git push -u origin HEAD
  if errorlevel 1 (
    echo ERROR: Push failed.
    pause
    exit /b 1
  )
)

echo.
echo ============================================================
echo  Done
echo ============================================================
echo Repo URL:
echo   https://github.com/%OWNER_REPO%
echo.
echo Current remotes:
git remote -v
echo.
pause
endlocal
