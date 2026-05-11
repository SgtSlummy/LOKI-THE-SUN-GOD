$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$desktop = Join-Path $env:USERPROFILE "OneDrive\Desktop"
$target = Join-Path $desktop "LOKI-THE-SUN-GOD-Dashboard.exe"
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
& $pyinstaller --noconfirm --clean .\LokiDashboard.spec

if (-not (Test-Path ".\dist\LOKI-THE-SUN-GOD-Dashboard.exe")) {
    throw "PyInstaller finished but dist\LOKI-THE-SUN-GOD-Dashboard.exe was not created."
}

& $python .\scripts\verify_loki_dashboard_package.py --exe ".\dist\LOKI-THE-SUN-GOD-Dashboard.exe"

if (-not (Test-Path $desktop)) {
    New-Item -ItemType Directory -Force -Path $desktop | Out-Null
}

Copy-Item ".\dist\LOKI-THE-SUN-GOD-Dashboard.exe" $target -Force

$sourceInfo = Get-Item ".\dist\LOKI-THE-SUN-GOD-Dashboard.exe"
$targetInfo = Get-Item $target
if ($sourceInfo.Length -ne $targetInfo.Length) {
    throw "Desktop copy size mismatch: source=$($sourceInfo.Length) target=$($targetInfo.Length)"
}

Write-Host "Built LOKI THE SUN GOD dashboard executable:"
Write-Host "  $target"

& .\scripts\stop_dashboard_test_processes.ps1
