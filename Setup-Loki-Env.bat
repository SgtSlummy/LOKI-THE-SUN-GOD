@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup-loki-env.ps1"
echo.
echo Setup finished. You can close this window.
pause

