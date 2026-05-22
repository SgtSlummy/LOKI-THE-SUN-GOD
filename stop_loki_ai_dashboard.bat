@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Stop LOKI AI Dashboard

set "FOUND="
set "STOPPED_PIDS= "

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5000" ^| findstr "LISTENING"') do (
  set "FOUND=1"
  echo !STOPPED_PIDS! | findstr /c:" %%P " >nul
  if errorlevel 1 (
    set "STOPPED_PIDS=!STOPPED_PIDS!%%P "
    echo Stopping LOKI dashboard process %%P...
    taskkill /PID %%P /T /F
  )
)

if not defined FOUND (
  echo LOKI dashboard is not listening on port 5000.
)

exit /b 0
