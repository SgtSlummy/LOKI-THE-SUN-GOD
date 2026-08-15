[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$processes = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.CommandLine -match [regex]::Escape("local_loki_runtime.py") -and $_.CommandLine -match [regex]::Escape($root)
}
foreach ($process in $processes) {
    Stop-Process -Id $process.ProcessId -Force
    Write-Output "Stopped LOKI local runtime PID $($process.ProcessId)."
}
if (-not $processes) {
    Write-Output "No matching LOKI local runtime process found."
}
