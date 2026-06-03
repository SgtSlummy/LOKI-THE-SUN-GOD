param(
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $RepoRoot ".env"

function Import-DotEnv {
    param([string]$Path)
    $values = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $values
    }
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
            $values[$key] = $value
        }
    }
    return $values
}

function Has-UsableValue {
    param([hashtable]$Values, [string]$Key)
    return $Values.ContainsKey($Key) -and
        -not [string]::IsNullOrWhiteSpace([string]$Values[$Key]) -and
        -not ([string]$Values[$Key]).StartsWith("replace-with-")
}

function Add-NeededUrl {
    param(
        [System.Collections.Generic.List[object]]$Rows,
        [string]$Need,
        [string]$Url,
        [string]$Why,
        [bool]$Open = $true
    )
    $Rows.Add([pscustomobject]@{
        Need = $Need
        Url = $Url
        Why = $Why
        Open = $Open
    })
}

function Test-RailwayToken {
    param([hashtable]$Values)

    $token = ""
    if (Has-UsableValue $Values "RAILWAY_TOKEN") {
        $token = [string]$Values["RAILWAY_TOKEN"]
    }
    elseif (Has-UsableValue $Values "RAILWAY_API_TOKEN") {
        $token = [string]$Values["RAILWAY_API_TOKEN"]
    }
    else {
        return $false
    }

    $oldToken = $env:RAILWAY_TOKEN
    $oldErrorActionPreference = $ErrorActionPreference
    try {
        $env:RAILWAY_TOKEN = $token
        $ErrorActionPreference = "Continue"
        $output = & npx -y '@railway/cli' whoami 2>&1
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
        $env:RAILWAY_TOKEN = $oldToken
    }
}

$values = Import-DotEnv $EnvPath
$rows = New-Object System.Collections.Generic.List[object]

if (-not (Has-UsableValue $values "DISCORD_CLIENT_ID")) {
    Add-NeededUrl $rows "DISCORD_CLIENT_ID" "https://discord.com/developers/applications" "Required for slash command sync. Open your app, then General Information -> Application ID."
}

if (-not (Has-UsableValue $values "DISCORD_TOKEN")) {
    if (Has-UsableValue $values "DISCORD_CLIENT_ID") {
        $clientId = [string]$values["DISCORD_CLIENT_ID"]
        Add-NeededUrl $rows "DISCORD_TOKEN" "https://discord.com/developers/applications/$clientId/bot" "Required to start the bot. Bot page -> Token. Enable Message Content Intent here too."
    }
    else {
        Add-NeededUrl $rows "DISCORD_TOKEN" "https://discord.com/developers/applications" "Required to start the bot. Open your app, then Bot page -> Token."
    }
}

if (-not (Has-UsableValue $values "DISCORD_GUILD_ID") -or -not (Has-UsableValue $values "BOT_ADMIN_USER_IDS")) {
    Add-NeededUrl $rows "DISCORD_GUILD_ID / BOT_ADMIN_USER_IDS" "https://support.discord.com/hc/en-us/articles/206346498" "Required for dev command sync and admin commands. Enable Developer Mode, then Copy ID."
}

$railwayOk = Test-RailwayToken $values
if (-not $railwayOk) {
    Add-NeededUrl $rows "RAILWAY_TOKEN or RAILWAY_API_TOKEN" "https://railway.com/account/tokens" "Required because Railway rejected the current token or no token is set."
}

if (-not (Has-UsableValue $values "RAILWAY_PROJECT_ID")) {
    Add-NeededUrl $rows "RAILWAY_PROJECT_ID" "https://railway.com/dashboard" "Required by the Railway push/deploy helper. Open the project; the project ID is in the URL/settings."
}

if (-not (Has-UsableValue $values "RAILWAY_SERVICE_NAME")) {
    if (Has-UsableValue $values "RAILWAY_PROJECT_ID") {
        $projectId = [string]$values["RAILWAY_PROJECT_ID"]
        Add-NeededUrl $rows "RAILWAY_SERVICE_NAME" "https://railway.com/project/$projectId" "Required by the Railway push/deploy helper. Select the Loki service and use its service name."
    }
    else {
        Add-NeededUrl $rows "RAILWAY_SERVICE_NAME" "https://railway.com/dashboard" "Required by the Railway push/deploy helper. Open the project and select the Loki service."
    }
}

Write-Host "Loki needed-only setup URLs"
Write-Host "No secret values are printed. Optional LLM/Mythos/OpenAI pages are intentionally skipped."
Write-Host ""

if ($rows.Count -eq 0) {
    Write-Host "No missing required setup pages detected for the MVP/Railway path."
    Write-Host "Next useful batch: Push-Loki-Railway-Variables.bat"
    exit 0
}

foreach ($row in $rows) {
    Write-Host "[$($row.Need)]"
    Write-Host "  URL: $($row.Url)"
    Write-Host "  Why: $($row.Why)"
    Write-Host ""
}

if ($OpenBrowser) {
    $opened = @{}
    foreach ($row in $rows) {
        if ($row.Open -and -not $opened.ContainsKey($row.Url)) {
            Start-Process $row.Url
            $opened[$row.Url] = $true
        }
    }
    Write-Host "Opened only the needed setup pages."
}
