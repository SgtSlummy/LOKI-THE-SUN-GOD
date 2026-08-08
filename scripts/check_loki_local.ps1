[CmdletBinding()]
param([int]$HealthPort = 9101)

$ErrorActionPreference = "Stop"
$uri = "http://127.0.0.1:$HealthPort/healthz"
try {
    $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 3
    $response.Content | ConvertFrom-Json | ConvertTo-Json -Depth 8
    if ($response.StatusCode -ne 200) { exit 1 }
} catch {
    Write-Error "LOKI local health check failed: $($_.Exception.Message)"
    exit 1
}
