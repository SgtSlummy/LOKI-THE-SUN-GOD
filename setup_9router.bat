@echo off
setlocal EnableExtensions
title Setup 9Router

set "ROUTER_DIR=%USERPROFILE%\OneDrive\Desktop\Codex\9router"

if not exist "%ROUTER_DIR%\package.json" (
  echo 9router source was not found at:
  echo   %ROUTER_DIR%
  echo.
  echo Clone https://github.com/decolua/9router.git there, then rerun this file.
  pause
  exit /b 1
)

cd /d "%ROUTER_DIR%"

if not exist ".env" (
  copy ".env.example" ".env" >nul
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p='.env';" ^
  "$lines=[System.Collections.Generic.List[string]]::new();" ^
  "foreach($line in [System.IO.File]::ReadAllLines($p)){ $lines.Add($line) }" ^
  "function Set-Line($k,$v){ $rx='^\s*'+[regex]::Escape($k)+'='; $found=$false; for($i=0;$i -lt $lines.Count;$i++){ if($lines[$i] -match $rx){ $lines[$i]=\"$k=$v\"; $found=$true } }; if(-not $found){ if($lines.Count -gt 0 -and $lines[$lines.Count-1].Trim()){ $lines.Add('') }; $lines.Add(\"$k=$v\") } }" ^
  "Set-Line 'INITIAL_PASSWORD' '*123456';" ^
  "Set-Line 'PORT' '20128';" ^
  "Set-Line 'BASE_URL' 'http://localhost:20128';" ^
  "Set-Line 'NEXT_PUBLIC_BASE_URL' 'http://localhost:20128';" ^
  "Set-Line 'CLOUD_URL' 'https://9router.com';" ^
  "Set-Line 'NEXT_PUBLIC_CLOUD_URL' 'https://9router.com';" ^
  "Set-Line 'DATA_DIR' ($env:APPDATA + '\9router');" ^
  "Set-Line 'NODE_ENV' 'development';" ^
  "Set-Line 'AUTH_COOKIE_SECURE' 'false';" ^
  "Set-Line 'REQUIRE_API_KEY' 'false';" ^
  "[System.IO.File]::WriteAllLines($p,$lines,[System.Text.UTF8Encoding]::new($false))"

if errorlevel 1 (
  echo Failed to update 9router .env.
  pause
  exit /b 1
)

echo Installing 9router dependencies...
npm install
if errorlevel 1 (
  echo npm install failed.
  pause
  exit /b 1
)

echo.
echo 9router setup complete.
echo Use start_9router.bat to run it.
pause
