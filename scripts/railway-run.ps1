param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RailwayArgs
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $RepoRoot ".env"

if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw ".env not found. Run Setup-Loki-Env.bat first."
}

$rawValues = @{}
foreach ($line in Get-Content -LiteralPath $EnvPath) {
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
        $rawValues[$key] = $value
        if ($key -notin @("RAILWAY_TOKEN", "RAILWAY_API_TOKEN")) {
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

function Test-RailwayApiToken {
    param([string]$Token)

    if ([string]::IsNullOrWhiteSpace($Token)) {
        return $false
    }

    $oldToken = $env:RAILWAY_TOKEN
    $oldApiToken = $env:RAILWAY_API_TOKEN
    $oldErrorActionPreference = $ErrorActionPreference
    try {
        Remove-Item Env:RAILWAY_TOKEN -ErrorAction SilentlyContinue
        $env:RAILWAY_API_TOKEN = $Token
        $ErrorActionPreference = "Continue"
        $null = & npx -y '@railway/cli' whoami 2>&1
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
        if ($null -ne $oldToken) {
            $env:RAILWAY_TOKEN = $oldToken
        }
        else {
            Remove-Item Env:RAILWAY_TOKEN -ErrorAction SilentlyContinue
        }
        if ($null -ne $oldApiToken) {
            $env:RAILWAY_API_TOKEN = $oldApiToken
        }
        else {
            Remove-Item Env:RAILWAY_API_TOKEN -ErrorAction SilentlyContinue
        }
    }
}

function Test-RailwayBrowserLogin {
    $oldToken = $env:RAILWAY_TOKEN
    $oldApiToken = $env:RAILWAY_API_TOKEN
    $oldErrorActionPreference = $ErrorActionPreference
    try {
        Remove-Item Env:RAILWAY_TOKEN -ErrorAction SilentlyContinue
        Remove-Item Env:RAILWAY_API_TOKEN -ErrorAction SilentlyContinue
        $ErrorActionPreference = "Continue"
        $null = & npx -y '@railway/cli' whoami 2>&1
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
        if ($null -ne $oldToken) {
            $env:RAILWAY_TOKEN = $oldToken
        }
        if ($null -ne $oldApiToken) {
            $env:RAILWAY_API_TOKEN = $oldApiToken
        }
    }
}

$commandName = if ($RailwayArgs.Count -gt 0) { $RailwayArgs[0] } else { "" }
$preferApiToken = $commandName -in @("whoami", "login", "logout", "link", "project", "add")
$selectedTokenName = $null
$selectedToken = $null
if ($preferApiToken -and (Test-RailwayApiToken ([string]$rawValues["RAILWAY_API_TOKEN"]))) {
    $selectedTokenName = "RAILWAY_API_TOKEN"
    $selectedToken = [string]$rawValues["RAILWAY_API_TOKEN"]
}
elseif (-not [string]::IsNullOrWhiteSpace([string]$rawValues["RAILWAY_TOKEN"])) {
    $selectedTokenName = "RAILWAY_TOKEN"
    $selectedToken = [string]$rawValues["RAILWAY_TOKEN"]
}
elseif (Test-RailwayApiToken ([string]$rawValues["RAILWAY_API_TOKEN"])) {
    $selectedTokenName = "RAILWAY_API_TOKEN"
    $selectedToken = [string]$rawValues["RAILWAY_API_TOKEN"]
}
elseif (-not (Test-RailwayBrowserLogin)) {
    throw "Railway is not authenticated. Run the Railway browser login, or set a valid RAILWAY_TOKEN or RAILWAY_API_TOKEN in .env."
}

if ($selectedToken) {
    if ($selectedTokenName -eq "RAILWAY_API_TOKEN") {
        Remove-Item Env:RAILWAY_TOKEN -ErrorAction SilentlyContinue
        $env:RAILWAY_API_TOKEN = $selectedToken
    }
    else {
        $env:RAILWAY_TOKEN = $selectedToken
        Remove-Item Env:RAILWAY_API_TOKEN -ErrorAction SilentlyContinue
    }
}
else {
    Remove-Item Env:RAILWAY_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:RAILWAY_API_TOKEN -ErrorAction SilentlyContinue
}

& npx -y '@railway/cli' @RailwayArgs
exit $LASTEXITCODE
