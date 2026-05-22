@echo off
setlocal EnableExtensions
title Reset 9Router Password

set "ROUTER_DIR=%USERPROFILE%\OneDrive\Desktop\Codex\9router"
set "DATA_DIR=%APPDATA%\9router"
set "DB_FILE=%DATA_DIR%\db.json"
set "NEW_PASSWORD=*123456"

if not exist "%ROUTER_DIR%\.env" (
  echo 9router .env was not found at:
  echo   %ROUTER_DIR%\.env
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$envPath=$env:USERPROFILE + '\OneDrive\Desktop\Codex\9router\.env';" ^
  "$lines=[System.Collections.Generic.List[string]]::new();" ^
  "foreach($line in [System.IO.File]::ReadAllLines($envPath)){ $lines.Add($line) }" ^
  "function Set-Line($k,$v){ $rx='^\s*'+[regex]::Escape($k)+'='; $found=$false; for($i=0;$i -lt $lines.Count;$i++){ if($lines[$i] -match $rx){ $lines[$i]=\"$k=$v\"; $found=$true } }; if(-not $found){ if($lines.Count -gt 0 -and $lines[$lines.Count-1].Trim()){ $lines.Add('') }; $lines.Add(\"$k=$v\") } }" ^
  "Set-Line 'INITIAL_PASSWORD' $env:NEW_PASSWORD;" ^
  "[System.IO.File]::WriteAllLines($envPath,$lines,[System.Text.UTF8Encoding]::new($false));" ^
  "$dbPath=$env:DB_FILE;" ^
  "if(Test-Path $dbPath){ $db=Get-Content $dbPath -Raw | ConvertFrom-Json; if(-not $db.settings){ $db | Add-Member -NotePropertyName settings -NotePropertyValue ([pscustomobject]@{}) }; if($db.settings.PSObject.Properties.Name -contains 'password'){ $db.settings.PSObject.Properties.Remove('password') }; $db | ConvertTo-Json -Depth 100 | Set-Content -Path $dbPath -Encoding UTF8 }"

if errorlevel 1 (
  echo Failed to reset 9router password.
  exit /b 1
)

echo 9Router password reset to: %NEW_PASSWORD%
echo Restarting 9Router...
call "%~dp0stop_9router.bat" >nul 2>nul
call "%~dp0start_9router_background.bat"

exit /b %errorlevel%
