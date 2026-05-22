$ErrorActionPreference = "Stop"

$routerDir = Join-Path $env:USERPROFILE "OneDrive\Desktop\Codex\9router"
$logFile = Join-Path $routerDir "9router-dev.log"

if (-not (Test-Path (Join-Path $routerDir "package.json"))) {
    Write-Error "9router source was not found at: $routerDir"
    exit 1
}

if (-not (Test-Path (Join-Path $routerDir ".env"))) {
    $setupScript = Join-Path (Split-Path -Parent $PSScriptRoot) "setup_9router.bat"
    & $setupScript
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$portInUse = Get-NetTCPConnection -LocalPort 20128 -State Listen -ErrorAction SilentlyContinue
if ($portInUse) {
    Write-Host "9router is already running on http://localhost:20128"
    exit 0
}

$startup = ([wmiclass]"Win32_ProcessStartup").CreateInstance()
$startup.ShowWindow = 7

$command = 'cmd.exe /d /c npm run dev > "' + $logFile + '" 2>&1'
$result = Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList $command, $routerDir, $startup

if ($result.ReturnValue -ne 0) {
    Write-Error "Failed to start 9router. WMI returned $($result.ReturnValue)."
    exit $result.ReturnValue
}

Write-Host "Started 9router process $($result.ProcessId)"
Write-Host "Log: $logFile"
