@echo off
setlocal
cd /d "%~dp0"
where powershell.exe >nul 2>nul
if errorlevel 1 (
  echo PowerShell is required for the Loki Hermes Node installer.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-LokiHermesNode.ps1"
if errorlevel 1 (
  echo.
  echo Installer failed. See the log in %%LOCALAPPDATA%%\LokiHermesNode\install.log
  pause
  exit /b 1
)
echo.
echo Install completed. Loki Hermes Node is configured to start at Windows login.
pause
