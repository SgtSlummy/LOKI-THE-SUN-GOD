@echo off
setlocal EnableExtensions
title LOKI AI Dashboard

set "ROOT=%~dp0"
set "LOG_FILE=%ROOT%dashboard-dev.log"
set "DASHBOARD_URL=http://127.0.0.1:5000/dev/connect-loki-ai"

if exist "%ROOT%.venv\Scripts\python.exe" (
  set "PYTHON=%ROOT%.venv\Scripts\python.exe"
) else (
  set "PYTHON=python"
)

netstat -ano | findstr ":5000" | findstr "LISTENING" >nul
if not errorlevel 1 (
  echo LOKI dashboard is already running.
  echo Opening %DASHBOARD_URL%
  start "" "%DASHBOARD_URL%"
  exit /b 0
)

echo Starting LOKI AI dashboard...
echo Log: %LOG_FILE%
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start_loki_ai_dashboard.ps1"
if errorlevel 1 (
  echo.
  echo Failed to start the LOKI AI dashboard. Check:
  echo   %LOG_FILE%
  echo.
  pause
  exit /b 1
)

ping -n 4 127.0.0.1 >nul
start "" "%DASHBOARD_URL%"

exit /b 0
