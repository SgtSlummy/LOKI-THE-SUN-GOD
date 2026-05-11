$ErrorActionPreference = "Stop"

Get-CimInstance Win32_Process | Where-Object {
    $cmd = $_.CommandLine
    if (-not $cmd) { return $false }
    $lower = $cmd.ToLowerInvariant()
    return (
        $lower -match "desktop_app\.py.*--run-dashboard" -or
        $lower -match "loki dashboard\.exe.*--run-dashboard"
    )
} | ForEach-Object {
    if ($IsWindows -or $env:OS -eq "Windows_NT") {
        Start-Process -FilePath "$env:SystemRoot\System32\taskkill.exe" `
            -ArgumentList "/PID", "$($_.ProcessId)", "/T", "/F" `
            -Wait -NoNewWindow
    } else {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Write-Host "stopped dashboard test PID $($_.ProcessId)"
}
