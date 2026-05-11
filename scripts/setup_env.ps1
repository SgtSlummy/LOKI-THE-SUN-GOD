param(
    [string]$OutputPath = "",
    [string]$DiscordToken = "",
    [string]$Prefix = "",
    [string]$OwnerId = "",
    [string]$TestGuildId = "",
    [string]$DiscordClientId = "",
    [string]$DiscordClientSecret = "",
    [string]$RedirectUri = "",
    [string]$DashboardSecretKey = "",
    [string]$DashboardHost = "",
    [string]$DashboardPort = "",
    [string]$DashboardDebug = "",
    [string]$TwitchClientId = "",
    [string]$TwitchClientSecret = "",
    [switch]$OpenDiscordPortal,
    [switch]$NoPortalPrompt
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$defaultOutputPath = Join-Path $repoRoot ".env"
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = $defaultOutputPath
}

function Read-DotEnv {
    param([string]$Path)

    $values = @{}
    if (-not (Test-Path $Path)) {
        return $values
    }

    foreach ($line in Get-Content -Path $Path -ErrorAction SilentlyContinue) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $trimmed = $line.Trim()
        if ($trimmed.StartsWith("#")) {
            continue
        }
        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2) {
            continue
        }
        $key = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $values[$key] = $value
    }
    return $values
}

function Prompt-Text {
    param(
        [string]$Label,
        [string]$CurrentValue,
        [string]$DefaultValue = ""
    )

    $effectiveDefault = if (-not [string]::IsNullOrWhiteSpace($CurrentValue)) { $CurrentValue } else { $DefaultValue }
    $suffix = if ([string]::IsNullOrWhiteSpace($effectiveDefault)) { "" } else { " [$effectiveDefault]" }
    $response = Read-Host "$Label$suffix"
    if ([string]::IsNullOrWhiteSpace($response)) {
        return $effectiveDefault
    }
    return $response.Trim()
}

function SecureString-ToPlainText {
    param([Security.SecureString]$Value)

    if ($null -eq $Value) {
        return ""
    }

    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
}

function Prompt-Secret {
    param(
        [string]$Label,
        [string]$CurrentValue
    )

    $hint = if ([string]::IsNullOrWhiteSpace($CurrentValue)) {
        "$Label (hidden input)"
    }
    else {
        "$Label (hidden input, leave blank to keep current value)"
    }

    $secure = Read-Host -AsSecureString $hint
    $plain = SecureString-ToPlainText $secure
    if ([string]::IsNullOrWhiteSpace($plain)) {
        return $CurrentValue
    }
    return $plain
}

function Escape-DotEnvValue {
    param([string]$Value)

    if ($null -eq $Value) {
        return ""
    }
    $escaped = $Value.Replace("\", "\\").Replace('"', '\"')
    return '"' + $escaped + '"'
}

function Open-DiscordPortalPages {
    param(
        [string]$ClientId,
        [string]$RedirectUri
    )

    $urls = @()
    if (-not [string]::IsNullOrWhiteSpace($ClientId) -and $ClientId -match '^\d+$') {
        $urls += "https://discord.com/developers/applications/$ClientId/information"
        $urls += "https://discord.com/developers/applications/$ClientId/bot"
        $urls += "https://discord.com/developers/applications/$ClientId/oauth2"
        $urls += "https://discord.com/developers/applications/$ClientId/installation"
    }
    else {
        $urls += "https://discord.com/developers/applications"
    }

    foreach ($url in $urls | Select-Object -Unique) {
        Start-Process $url | Out-Null
    }

    Write-Host ""
    Write-Host "Opened Discord Developer Portal pages." -ForegroundColor Green
    if (-not [string]::IsNullOrWhiteSpace($RedirectUri)) {
        Write-Host "Verify this redirect URI in Discord OAuth2 settings: $RedirectUri" -ForegroundColor Yellow
    }
    Write-Host "On the Bot page, make sure MESSAGE_CONTENT and GUILD_MEMBERS are enabled if LOKI THE SUN GOD needs them." -ForegroundColor Yellow
}

$existing = Read-DotEnv -Path $OutputPath

$resolvedDiscordToken = if (-not [string]::IsNullOrWhiteSpace($DiscordToken)) { $DiscordToken } else { Prompt-Secret "DISCORD_TOKEN" ($existing["DISCORD_TOKEN"]) }
$resolvedPrefix = if (-not [string]::IsNullOrWhiteSpace($Prefix)) { $Prefix } else { Prompt-Text "PREFIX" ($existing["PREFIX"]) "!" }
$resolvedOwnerId = if (-not [string]::IsNullOrWhiteSpace($OwnerId)) { $OwnerId } else { Prompt-Text "OWNER_ID" ($existing["OWNER_ID"]) "" }
$resolvedTestGuildId = if (-not [string]::IsNullOrWhiteSpace($TestGuildId)) { $TestGuildId } else { Prompt-Text "TEST_GUILD_ID" ($existing["TEST_GUILD_ID"]) "" }
$resolvedDiscordClientId = if (-not [string]::IsNullOrWhiteSpace($DiscordClientId)) { $DiscordClientId } else { Prompt-Text "DISCORD_CLIENT_ID" ($existing["DISCORD_CLIENT_ID"]) "" }
$resolvedDiscordClientSecret = if (-not [string]::IsNullOrWhiteSpace($DiscordClientSecret)) { $DiscordClientSecret } else { Prompt-Secret "DISCORD_CLIENT_SECRET" ($existing["DISCORD_CLIENT_SECRET"]) }
$resolvedRedirectUri = if (-not [string]::IsNullOrWhiteSpace($RedirectUri)) { $RedirectUri } else { Prompt-Text "REDIRECT_URI" ($existing["REDIRECT_URI"]) "http://127.0.0.1:5000/callback" }
$resolvedDashboardSecretKey = if (-not [string]::IsNullOrWhiteSpace($DashboardSecretKey)) { $DashboardSecretKey } else { Prompt-Secret "DASHBOARD_SECRET_KEY" ($existing["DASHBOARD_SECRET_KEY"]) }
$resolvedDashboardHost = if (-not [string]::IsNullOrWhiteSpace($DashboardHost)) { $DashboardHost } else { Prompt-Text "DASHBOARD_HOST" ($existing["DASHBOARD_HOST"]) "127.0.0.1" }
$resolvedDashboardPort = if (-not [string]::IsNullOrWhiteSpace($DashboardPort)) { $DashboardPort } else { Prompt-Text "DASHBOARD_PORT" ($existing["DASHBOARD_PORT"]) "5000" }
$resolvedDashboardDebug = if (-not [string]::IsNullOrWhiteSpace($DashboardDebug)) { $DashboardDebug } else { Prompt-Text "DASHBOARD_DEBUG" ($existing["DASHBOARD_DEBUG"]) "false" }
$resolvedTwitchClientId = if (-not [string]::IsNullOrWhiteSpace($TwitchClientId)) { $TwitchClientId } else { Prompt-Text "TWITCH_CLIENT_ID" ($existing["TWITCH_CLIENT_ID"]) "" }
$resolvedTwitchClientSecret = if (-not [string]::IsNullOrWhiteSpace($TwitchClientSecret)) { $TwitchClientSecret } else { Prompt-Secret "TWITCH_CLIENT_SECRET" ($existing["TWITCH_CLIENT_SECRET"]) }

$content = @(
    "DISCORD_TOKEN=$(Escape-DotEnvValue $resolvedDiscordToken)"
    "# Enable MESSAGE_CONTENT and GUILD_MEMBERS in the Discord Developer Portal for this bot."
    "PREFIX=$(Escape-DotEnvValue $resolvedPrefix)"
    "OWNER_ID=$(Escape-DotEnvValue $resolvedOwnerId)"
    "TEST_GUILD_ID=$(Escape-DotEnvValue $resolvedTestGuildId)"
    ""
    "DISCORD_CLIENT_ID=$(Escape-DotEnvValue $resolvedDiscordClientId)"
    "DISCORD_CLIENT_SECRET=$(Escape-DotEnvValue $resolvedDiscordClientSecret)"
    "REDIRECT_URI=$(Escape-DotEnvValue $resolvedRedirectUri)"
    "DASHBOARD_SECRET_KEY=$(Escape-DotEnvValue $resolvedDashboardSecretKey)"
    ""
    "DASHBOARD_HOST=$(Escape-DotEnvValue $resolvedDashboardHost)"
    "DASHBOARD_PORT=$(Escape-DotEnvValue $resolvedDashboardPort)"
    "DASHBOARD_DEBUG=$(Escape-DotEnvValue $resolvedDashboardDebug)"
    ""
    "TWITCH_CLIENT_ID=$(Escape-DotEnvValue $resolvedTwitchClientId)"
    "TWITCH_CLIENT_SECRET=$(Escape-DotEnvValue $resolvedTwitchClientSecret)"
    ""
)

$outputDirectory = Split-Path -Parent $OutputPath
if (-not [string]::IsNullOrWhiteSpace($outputDirectory) -and -not (Test-Path $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($OutputPath, $content, $utf8NoBom)

Write-Host ""
Write-Host "Wrote environment file to $OutputPath" -ForegroundColor Green
Write-Host "Required values present:" -ForegroundColor Cyan
Write-Host ("  DISCORD_TOKEN: " + (-not [string]::IsNullOrWhiteSpace($resolvedDiscordToken)))
Write-Host ("  DISCORD_CLIENT_ID: " + (-not [string]::IsNullOrWhiteSpace($resolvedDiscordClientId)))
Write-Host ("  DISCORD_CLIENT_SECRET: " + (-not [string]::IsNullOrWhiteSpace($resolvedDiscordClientSecret)))
Write-Host ("  REDIRECT_URI: " + (-not [string]::IsNullOrWhiteSpace($resolvedRedirectUri)))
Write-Host ("  DASHBOARD_SECRET_KEY: " + (-not [string]::IsNullOrWhiteSpace($resolvedDashboardSecretKey)))

$shouldOpenPortal = $false
if ($OpenDiscordPortal) {
    $shouldOpenPortal = $true
}
elseif (-not $NoPortalPrompt) {
    $openResponse = Read-Host "Open Discord Developer Portal pages now? [Y/n]"
    if ([string]::IsNullOrWhiteSpace($openResponse)) {
        $shouldOpenPortal = $true
    }
    else {
        $normalized = $openResponse.Trim().ToLowerInvariant()
        $shouldOpenPortal = $normalized -in @("y", "yes")
    }
}

if ($shouldOpenPortal) {
    Open-DiscordPortalPages -ClientId $resolvedDiscordClientId -RedirectUri $resolvedRedirectUri
}
