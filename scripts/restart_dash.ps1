$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}
Set-Location $root

& .\scripts\stop_dashboard_test_processes.ps1
& $python .\scripts\release_check.py --strict-env

Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and (
        $_.CommandLine.ToLower().Contains("dashboard_app.py") -or
        $_.CommandLine.ToLower().Contains("--run-dashboard")
    )
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    Write-Host "stopped dashboard PID $($_.ProcessId)"
}

Start-Sleep -Seconds 2

Start-Process $python -ArgumentList "dashboard_app.py" -WorkingDirectory $root -WindowStyle Hidden
