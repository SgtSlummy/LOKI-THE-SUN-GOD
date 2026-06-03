$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $RepoRoot ".env"

if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw ".env not found. Run Setup-Loki-Env.bat first."
}

function Import-DotEnv {
    param([string]$Path)
    $values = [ordered]@{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') {
            continue
        }
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            $values[$matches[1]] = $matches[2].Trim()
        }
    }
    return $values
}

function ConvertFrom-SecretInput {
    param([securestring]$SecureValue)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Format-DotEnvValue {
    param([AllowNull()][string]$Value)
    if ($null -eq $Value) {
        return ""
    }
    if ($Value -match '[\s#=`"''{}]') {
        $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
        return '"' + $escaped + '"'
    }
    return $Value
}

$values = Import-DotEnv $EnvPath

Write-Host "Railway setup for Loki 2.0"
Write-Host "Paste a valid Railway token. It will not be printed."
$secureToken = Read-Host -AsSecureString "RAILWAY_TOKEN"
$token = ConvertFrom-SecretInput $secureToken
if ($token) {
    $values["RAILWAY_TOKEN"] = $token
    $values["RAILWAY_API_TOKEN"] = $token
}

$projectId = Read-Host "RAILWAY_PROJECT_ID [$($values['RAILWAY_PROJECT_ID'])]"
if ($projectId) {
    $values["RAILWAY_PROJECT_ID"] = $projectId
}

$projectName = Read-Host "RAILWAY_PROJECT_NAME [$($values['RAILWAY_PROJECT_NAME'])]"
if ($projectName) {
    $values["RAILWAY_PROJECT_NAME"] = $projectName
}
elseif (-not $values["RAILWAY_PROJECT_NAME"]) {
    $values["RAILWAY_PROJECT_NAME"] = "loki-discord-relay"
}

$serviceName = Read-Host "RAILWAY_SERVICE_NAME [$($values['RAILWAY_SERVICE_NAME'])]"
if ($serviceName) {
    $values["RAILWAY_SERVICE_NAME"] = $serviceName
}
elseif (-not $values["RAILWAY_SERVICE_NAME"]) {
    $values["RAILWAY_SERVICE_NAME"] = "loki-discord-relay"
}

$serviceId = Read-Host "RAILWAY_SERVICE_ID [$($values['RAILWAY_SERVICE_ID'])]"
if ($serviceId) {
    $values["RAILWAY_SERVICE_ID"] = $serviceId
}

$environment = Read-Host "RAILWAY_ENVIRONMENT [$($values['RAILWAY_ENVIRONMENT'])]"
if ($environment) {
    $values["RAILWAY_ENVIRONMENT"] = $environment
}
elseif (-not $values["RAILWAY_ENVIRONMENT"]) {
    $values["RAILWAY_ENVIRONMENT"] = "production"
}

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# Loki 2.0 local environment")
$lines.Add("# Updated by Setup-Loki-Railway-Env.bat. Do not commit this file.")
foreach ($key in $values.Keys) {
    $lines.Add("$key=$(Format-DotEnvValue $values[$key])")
}

Set-Content -LiteralPath $EnvPath -Value $lines -Encoding UTF8
Write-Host "Railway values updated. Re-run Push-Loki-Railway-Variables.bat when ready."
