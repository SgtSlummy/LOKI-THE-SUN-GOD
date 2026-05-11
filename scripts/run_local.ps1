$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}
Set-Location $root

& .\scripts\stop_dashboard_test_processes.ps1
& $python .\scripts\release_check.py --strict-env

$bot = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and ($_.CommandLine -match 'bot.py' -or $_.CommandLine -match '--run-bot' -or $_.CommandLine -match '-m bot')
}
if (-not $bot) {
    Start-Process $python -ArgumentList "-m", "bot" -WorkingDirectory $root -WindowStyle Hidden
}

$dash = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and ($_.CommandLine -match 'dashboard_app.py' -or $_.CommandLine -match '--run-dashboard')
}
if (-not $dash) {
    Start-Process $python -ArgumentList "dashboard_app.py" -WorkingDirectory $root -WindowStyle Hidden
}

Start-Process $python -ArgumentList "desktop_app.py" -WorkingDirectory $root
