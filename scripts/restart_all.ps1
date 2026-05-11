$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}
Set-Location $root

& .\scripts\stop_dashboard_test_processes.ps1
& $python .\scripts\release_check.py --strict-env

function Stop-MatchingProcess($label, $patterns) {
    Get-CimInstance Win32_Process | Where-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return $false }
        foreach ($pattern in $patterns) {
            if ($pattern -and $cmd.ToLower().Contains($pattern.ToLower())) {
                return $true
            }
        }
        return $false
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "stopped $label PID $($_.ProcessId)"
    }
}

Stop-MatchingProcess "bot" @("bot.py", "--run-bot", "-m bot")
Stop-MatchingProcess "dashboard" @("dashboard_app.py", "--run-dashboard")
Stop-MatchingProcess "desktop" @("desktop_app.py")

Start-Sleep -Seconds 2

Start-Process $python -ArgumentList "-m", "bot" -WorkingDirectory $root -WindowStyle Hidden
Start-Sleep -Seconds 1
Start-Process $python -ArgumentList "dashboard_app.py" -WorkingDirectory $root -WindowStyle Hidden
Start-Sleep -Seconds 1
Start-Process $python -ArgumentList "desktop_app.py" -WorkingDirectory $root
