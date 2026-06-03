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

function Is-RealValue {
    param([hashtable]$Values, [string]$Key)
    return $Values.ContainsKey($Key) -and
        -not [string]::IsNullOrWhiteSpace([string]$Values[$Key]) -and
        -not ([string]$Values[$Key]).StartsWith("replace-with-")
}

function Add-InfoUrl {
    param(
        [System.Collections.Generic.List[object]]$Rows,
        [string]$ValueName,
        [string]$Url,
        [string]$WhereToLook,
        [bool]$Open = $false
    )
    $Rows.Add([pscustomobject]@{
        Value = $ValueName
        Url = $Url
        Where = $WhereToLook
        Open = $Open
    })
}

$values = Import-DotEnv $EnvPath
$rows = New-Object System.Collections.Generic.List[object]

$discordAppsUrl = "https://discord.com/developers/applications"
if (Is-RealValue $values "DISCORD_CLIENT_ID") {
    $clientId = [string]$values["DISCORD_CLIENT_ID"]
    Add-InfoUrl $rows "DISCORD_TOKEN" "https://discord.com/developers/applications/$clientId/bot" "Bot page: Token section; also enable Message Content Intent here." $true
    Add-InfoUrl $rows "DISCORD_CLIENT_ID" "https://discord.com/developers/applications/$clientId/information" "General Information page: Application ID." $true
    Add-InfoUrl $rows "Bot invite/OAuth2" "https://discord.com/developers/applications/$clientId/oauth2" "OAuth2 page: URL Generator for bot + applications.commands scopes." $false
}
else {
    Add-InfoUrl $rows "DISCORD_TOKEN" $discordAppsUrl "Open your app, then Bot page: Token section; also enable Message Content Intent." $true
    Add-InfoUrl $rows "DISCORD_CLIENT_ID" $discordAppsUrl "Open your app, then General Information page: Application ID." $true
    Add-InfoUrl $rows "Bot invite/OAuth2" $discordAppsUrl "Open your app, then OAuth2 page: URL Generator." $false
}

Add-InfoUrl $rows "DISCORD_GUILD_ID / BOT_ADMIN_USER_IDS / channel IDs" "https://support.discord.com/hc/en-us/articles/206346498" "Discord support article: enable Developer Mode, then Copy ID for server/user/channel." $true

Add-InfoUrl $rows "OPENAI_API_KEY" "https://platform.openai.com/api-keys" "OpenAI Platform: create or manage API keys." $true
Add-InfoUrl $rows "ANTHROPIC_API_KEY for Mythos chat" "https://console.anthropic.com/settings/keys" "Anthropic Console: API Keys." $false
Add-InfoUrl $rows "DEEPSEEK_API_KEY for Mythos chat" "https://platform.deepseek.com/api_keys" "DeepSeek Platform: API Keys." $false

Add-InfoUrl $rows "RAILWAY_TOKEN / RAILWAY_API_TOKEN" "https://railway.com/account/tokens" "Railway Account Settings: Tokens. Use one valid token, not both at once in the same shell." $true

if (Is-RealValue $values "RAILWAY_PROJECT_ID") {
    $projectId = [string]$values["RAILWAY_PROJECT_ID"]
    Add-InfoUrl $rows "RAILWAY_PROJECT_ID / project settings" "https://railway.com/project/$projectId" "Railway project dashboard. Project settings contain the project ID." $true
    if (Is-RealValue $values "RAILWAY_SERVICE_ID") {
        $serviceId = [string]$values["RAILWAY_SERVICE_ID"]
        Add-InfoUrl $rows "RAILWAY_SERVICE_ID / service variables" "https://railway.com/project/$projectId/service/$serviceId" "Railway service page. Open Variables or Settings for this service." $true
    }
    else {
        Add-InfoUrl $rows "RAILWAY_SERVICE_ID / service variables" "https://railway.com/project/$projectId" "Select the Loki service in the project canvas, then open Variables or Settings. Copy the service ID from the URL." $false
    }
}
else {
    Add-InfoUrl $rows "RAILWAY_PROJECT_ID / project settings" "https://railway.com/dashboard" "Railway dashboard: open the project; the project ID is in the URL and Settings." $true
    Add-InfoUrl $rows "RAILWAY_SERVICE_ID / service variables" "https://railway.com/dashboard" "Open the project, select the Loki service, then open Variables or Settings. Copy the service ID from the URL." $false
}

Write-Host "Loki setup info URLs"
Write-Host "No secret values are printed. Exact project/app URLs are built from IDs already in .env when present."
Write-Host ""

foreach ($row in $rows) {
    Write-Host "[$($row.Value)]"
    Write-Host "  URL: $($row.Url)"
    Write-Host "  Where: $($row.Where)"
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
    Write-Host "Opened the main setup pages in your browser."
}
