$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$logFile = Join-Path $root "dashboard-dev.log"
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$existing = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "LOKI dashboard is already running on http://127.0.0.1:5000"
    exit 0
}

$startup = ([wmiclass]"Win32_ProcessStartup").CreateInstance()
$startup.ShowWindow = 7

$command = 'cmd.exe /d /c ""' + $python + '" dashboard_app.py > "' + $logFile + '" 2>&1"'
$result = Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList $command, $root, $startup

if ($result.ReturnValue -ne 0) {
    Write-Error "Failed to start LOKI dashboard. WMI returned $($result.ReturnValue)."
    exit $result.ReturnValue
}

Write-Host "Started LOKI dashboard process $($result.ProcessId)"
Write-Host "Log: $logFile"
