@echo off
setlocal EnableExtensions
title 9Router Background

set "ROUTER_DIR=%USERPROFILE%\OneDrive\Desktop\Codex\9router"
set "LOG_FILE=%ROUTER_DIR%\9router-dev.log"

if not exist "%ROUTER_DIR%\package.json" (
  echo 9router source was not found at:
  echo   %ROUTER_DIR%
  exit /b 1
)

cd /d "%ROUTER_DIR%"

if not exist ".env" (
  call "%~dp0setup_9router.bat"
  if errorlevel 1 exit /b 1
)

netstat -ano | findstr ":20128" | findstr "LISTENING" >nul
if not errorlevel 1 (
  echo 9router is already running on http://localhost:20128
  echo.
  echo 9Router dashboard: http://localhost:20128/dashboard
  echo 9Router API:       http://localhost:20128/v1
  echo.
  start "" "http://localhost:20128/dashboard"
  exit /b 0
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_9router_background.ps1"
if errorlevel 1 (
  echo.
  echo Failed to start 9router. Check:
  echo   %LOG_FILE%
  echo.
  pause
  exit /b 1
)

echo.
echo 9Router dashboard: http://localhost:20128/dashboard
echo 9Router API:       http://localhost:20128/v1
echo.
start "" "http://localhost:20128/dashboard"

exit /b 0
