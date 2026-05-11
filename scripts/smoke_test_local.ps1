$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python .\scripts\release_check.py

function Test-Url($url) {
    try {
        $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
        [PSCustomObject]@{ Url = $url; StatusCode = $response.StatusCode; Ok = $true }
    } catch {
        [PSCustomObject]@{ Url = $url; StatusCode = 0; Ok = $false; Error = $_.Exception.Message }
    }
}

$results = @(
    Test-Url "http://127.0.0.1:7331/api/status"
    Test-Url "http://127.0.0.1:5000/healthz"
)

$results | Format-Table -AutoSize
