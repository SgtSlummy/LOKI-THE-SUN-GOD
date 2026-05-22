@echo off
setlocal EnableExtensions
title 9Router

set "ROUTER_DIR=%USERPROFILE%\OneDrive\Desktop\Codex\9router"

if not exist "%ROUTER_DIR%\package.json" (
  echo 9router source was not found at:
  echo   %ROUTER_DIR%
  pause
  exit /b 1
)

cd /d "%ROUTER_DIR%"

if not exist ".env" (
  call "%~dp0setup_9router.bat"
  if errorlevel 1 exit /b 1
)

echo Starting 9router on http://localhost:20128
echo Dashboard: http://localhost:20128/dashboard
echo API:       http://localhost:20128/v1
echo.
npm run dev
