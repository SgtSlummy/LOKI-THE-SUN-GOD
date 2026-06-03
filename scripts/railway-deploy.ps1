param(
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $RepoRoot ".env"

function Read-DotEnv {
    param([string]$Path)
    $result = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') {
            continue
        }
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            $key = $matches[1]
            $value = $matches[2].Trim()
            if ($value.Length -ge 2) {
                if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                    $value = $value.Substring(1, $value.Length - 2)
                }
            }
            $result[$key] = $value
        }
    }
    return $result
}

if ($Check) {
    Write-Host "railway-deploy.ps1 syntax and path check passed."
    exit 0
}

if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw ".env not found. Run Setup-Loki-Env.bat first."
}

$values = Read-DotEnv $EnvPath
$projectId = $values["RAILWAY_PROJECT_ID"]
$environment = if ($values["RAILWAY_ENVIRONMENT"]) { $values["RAILWAY_ENVIRONMENT"] } else { "production" }
$service = if ($values["RAILWAY_SERVICE_NAME"]) { $values["RAILWAY_SERVICE_NAME"] } else { "loki-discord-relay" }

if (-not $projectId) {
    throw "RAILWAY_PROJECT_ID is required in .env."
}

Write-Host "Deploying Loki service $service to Railway project $projectId."
& (Join-Path $PSScriptRoot "railway-run.ps1") `
    up `
    --service $service `
    --project $projectId `
    --environment $environment `
    --detach `
    --message "Deploy Loki Discord relay backend"

if ($LASTEXITCODE -ne 0) {
    throw "Railway deploy failed."
}

Write-Host "Railway deploy request submitted."
