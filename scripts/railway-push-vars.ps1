param(
    [switch]$Check,
    [switch]$TriggerDeploy
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

function Require-Value {
    param([hashtable]$Values, [string]$Key)
    if (-not $Values.ContainsKey($Key) -or [string]::IsNullOrWhiteSpace([string]$Values[$Key])) {
        throw "$Key is required in .env."
    }
    return [string]$Values[$Key]
}

if ($Check) {
    Write-Host "railway-push-vars.ps1 syntax and path check passed."
    exit 0
}

if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw ".env not found. Run Setup-Loki-Env.bat first."
}

$values = Read-DotEnv $EnvPath
$projectId = Require-Value -Values $values -Key "RAILWAY_PROJECT_ID"
$environment = if ($values["RAILWAY_ENVIRONMENT"]) { $values["RAILWAY_ENVIRONMENT"] } else { "production" }
$service = if ($values["RAILWAY_SERVICE_NAME"]) { $values["RAILWAY_SERVICE_NAME"] } else { "loki-discord-relay" }

$vars = [ordered]@{
    DISCORD_TOKEN = Require-Value -Values $values -Key "DISCORD_TOKEN"
    DISCORD_CLIENT_ID = Require-Value -Values $values -Key "DISCORD_CLIENT_ID"
    DISCORD_GUILD_ID = Require-Value -Values $values -Key "DISCORD_GUILD_ID"
    BOT_ADMIN_USER_IDS = Require-Value -Values $values -Key "BOT_ADMIN_USER_IDS"
    DATABASE_URL = '${{Postgres.DATABASE_URL}}'
    OPENAI_API_KEY = if ($values["OPENAI_API_KEY"]) { $values["OPENAI_API_KEY"] } else { "" }
    OPENAI_MODEL = if ($values["OPENAI_MODEL"]) { $values["OPENAI_MODEL"] } else { "gpt-5-mini" }
    BOT_ENV = "production"
    LOG_LEVEL = if ($values["LOG_LEVEL"]) { $values["LOG_LEVEL"] } else { "info" }
    MAX_ACTIVE_PLUGINS = if ($values["MAX_ACTIVE_PLUGINS"]) { $values["MAX_ACTIVE_PLUGINS"] } else { "8" }
    MEDIA_MODE = if ($values["MEDIA_MODE"]) { $values["MEDIA_MODE"] } else { "clean" }
    MEDIA_LINK_BUTTONS = if ($values["MEDIA_LINK_BUTTONS"]) { $values["MEDIA_LINK_BUTTONS"] } else { "false" }
    WEBHOOK_RELAY_MODE = if ($values["WEBHOOK_RELAY_MODE"]) { $values["WEBHOOK_RELAY_MODE"] } else { "false" }
    HEALTH_PORT = '${{PORT}}'
    AUTOCURATOR_ENABLED = if ($values["AUTOCURATOR_ENABLED"]) { $values["AUTOCURATOR_ENABLED"] } else { "false" }
    AUTOCURATOR_AUTOPOST = if ($values["AUTOCURATOR_AUTOPOST"]) { $values["AUTOCURATOR_AUTOPOST"] } else { "false" }
    SERVER_SEARCH_ENABLED = if ($values["SERVER_SEARCH_ENABLED"]) { $values["SERVER_SEARCH_ENABLED"] } else { "false" }
    LLM_CHAT_ENABLED = if ($values["LLM_CHAT_ENABLED"]) { $values["LLM_CHAT_ENABLED"] } else { "false" }
    MUSIC_ENABLED = if ($values["MUSIC_ENABLED"]) { $values["MUSIC_ENABLED"] } else { "false" }
    ALLOW_BOT_RELAY = if ($values["ALLOW_BOT_RELAY"]) { $values["ALLOW_BOT_RELAY"] } else { "false" }
}

if ($values["RELAY_CONFIG_JSON"]) {
    $vars["RELAY_CONFIG_JSON"] = $values["RELAY_CONFIG_JSON"]
}

$args = @(
    "variable",
    "set",
    "--service",
    $service,
    "--project",
    $projectId,
    "--environment",
    $environment
)

foreach ($entry in $vars.GetEnumerator()) {
    $args += "$($entry.Key)=$($entry.Value)"
}

if (-not $TriggerDeploy) {
    $args += "--skip-deploys"
}

Write-Host "Pushing Loki Railway variables to service $service in project $projectId."
Write-Host "Secret values will not be printed."
& (Join-Path $PSScriptRoot "railway-run.ps1") @args
if ($LASTEXITCODE -ne 0) {
    throw "Railway variable push failed."
}

foreach ($key in $vars.Keys) {
    if ($key -match "TOKEN|KEY|SECRET") {
        Write-Host "Set $key=<set>"
    }
    else {
        Write-Host "Set $key"
    }
}

