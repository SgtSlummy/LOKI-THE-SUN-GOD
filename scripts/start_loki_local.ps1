[CmdletBinding()]
param(
    [ValidateSet("heartbeat", "full")]
    [string]$Mode = "heartbeat",
    [int]$HealthPort = 9101
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.CommandLine -match [regex]::Escape("local_loki_runtime.py") -and $_.CommandLine -match [regex]::Escape($root)
}
if ($existing) {
    Write-Output "LOKI local runtime already has a matching process: $($existing.ProcessId -join ', ')"
    exit 0
}

$logDir = Join-Path $root "runtime-logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$stdout = Join-Path $logDir "loki-local.stdout.log"
$stderr = Join-Path $logDir "loki-local.stderr.log"
$args = @((Join-Path $root "local_loki_runtime.py"), "--mode", $Mode, "--port", $HealthPort)
$process = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Start-Sleep -Milliseconds 800
$alive = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
if (-not $alive) {
    Write-Error "LOKI local runtime exited during startup. See $stdout and $stderr."
}
Write-Output "Started LOKI local runtime PID $($process.Id) in $Mode mode. Health: http://127.0.0.1:$HealthPort/healthz"
