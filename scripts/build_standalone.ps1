$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
$pyinstaller = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\Scripts\pyinstaller.exe"

if (-not (Test-Path $python)) {
    $python = "python"
}
if (-not (Test-Path $pyinstaller)) {
    $pyinstaller = "pyinstaller"
}

Set-Location $root

& .\scripts\stop_dashboard_test_processes.ps1
& $python .\scripts\release_check.py --strict-env

$name = "LOKI THE SUN GOD Dashboard"
& $pyinstaller --noconfirm --clean .\LokiDashboard.spec
& $python .\scripts\verify_loki_dashboard_package.py --exe ".\dist\LOKI-THE-SUN-GOD-Dashboard.exe"

Write-Host "Built standalone desktop release:"
Write-Host "  $root\\dist\\$name.exe"

& .\scripts\stop_dashboard_test_processes.ps1
