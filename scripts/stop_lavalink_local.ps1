param([int]$Port = 2333)

$ErrorActionPreference = "Stop"

$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listeners) {
    Write-Host "Lavalink is not listening on port $Port."
    exit 0
}

$pids = $listeners | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($pid in $pids) {
    Write-Host "Stopping Lavalink process $pid..."
    & taskkill.exe /PID $pid /T /F | Out-Host
}
