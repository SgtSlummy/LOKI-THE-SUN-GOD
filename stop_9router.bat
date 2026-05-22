@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Stop 9Router

set "FOUND="
set "STOPPED_PIDS= "

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":20128" ^| findstr "LISTENING"') do (
  set "FOUND=1"
  echo !STOPPED_PIDS! | findstr /c:" %%P " >nul
  if errorlevel 1 (
    set "STOPPED_PIDS=!STOPPED_PIDS!%%P "
    echo Stopping 9router process %%P...
    taskkill /PID %%P /T /F
  )
)

if not defined FOUND (
  echo 9router is not listening on port 20128.
)

exit /b 0
