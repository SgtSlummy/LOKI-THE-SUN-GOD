$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python .\scripts\release_check.py

$name = "LokiDashboard-Standalone"
pyinstaller --noconfirm --clean .\LokiDashboard-Standalone.spec

if (Test-Path .\.env.example) {
    Copy-Item .\.env.example .\dist\.env.example -Force
}

Write-Host "Built standalone dashboard:"
Write-Host "  $root\\dist\\$name.exe"
Write-Host "Place a .env next to the executable if you want the standalone build to load local configuration."
