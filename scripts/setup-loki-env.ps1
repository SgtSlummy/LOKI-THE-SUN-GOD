param(
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $RepoRoot ".env"
$ExamplePath = Join-Path $RepoRoot ".env.example"
$SiblingEnvPath = Join-Path (Split-Path $RepoRoot -Parent) "Discord AI Relay\.env"

$SecretKeys = @(
    "DISCORD_TOKEN",
    "OPENAI_API_KEY",
    "RAILWAY_TOKEN",
    "RAILWAY_API_TOKEN"
)

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

function Get-ExistingValue {
    param(
        [string]$Key,
        [hashtable]$Current,
        [hashtable]$Sibling,
        [hashtable]$Example,
        [string]$Default = ""
    )

    if ($Current.ContainsKey($Key) -and $Current[$Key]) {
        return $Current[$Key]
    }

    $mappedSiblingKey = $Key
    if ($Key -eq "DISCORD_CLIENT_ID" -and -not $Sibling.ContainsKey("DISCORD_CLIENT_ID")) {
        $mappedSiblingKey = "DISCORD_APPLICATION_ID"
    }
    if ($Key -eq "BOT_ADMIN_USER_IDS" -and -not $Sibling.ContainsKey("BOT_ADMIN_USER_IDS")) {
        $mappedSiblingKey = "DISCORD_OWNER_USER_IDS"
    }

    if ($Sibling.ContainsKey($mappedSiblingKey) -and $Sibling[$mappedSiblingKey]) {
        return $Sibling[$mappedSiblingKey]
    }
    if ($Example.ContainsKey($Key) -and $Example[$Key] -and -not $Example[$Key].StartsWith("replace-with-")) {
        return $Example[$Key]
    }
    return $Default
}

function Read-ConfigValue {
    param(
        [string]$Key,
        [string]$Label,
        [AllowNull()][string]$Existing,
        [switch]$Secret,
        [switch]$Required,
        [switch]$NonInteractive
    )

    if ($NonInteractive) {
        if ($Required -and -not $Existing) {
            throw "Missing required value for $Key"
        }
        return $Existing
    }

    if ($Secret) {
        if ($Existing) {
            Write-Host "$Label is already set. Press Enter to keep it, or type a replacement."
        }
        else {
            Write-Host "$Label is required. Type it now. Input is hidden."
        }
        $secure = Read-Host -AsSecureString "$Key"
        $plain = ConvertFrom-SecretInput $secure
        if ($plain) {
            return $plain
        }
        if ($Existing) {
            return $Existing
        }
        if ($Required) {
            throw "Missing required value for $Key"
        }
        return ""
    }

    if ($Existing) {
        $prompt = "$Label [$Existing]"
    }
    else {
        $prompt = "$Label"
    }
    $value = Read-Host $prompt
    if ($value) {
        return $value
    }
    if ($Existing) {
        return $Existing
    }
    if ($Required) {
        throw "Missing required value for $Key"
    }
    return ""
}

$current = Import-DotEnv $EnvPath
$sibling = Import-DotEnv $SiblingEnvPath
$example = Import-DotEnv $ExamplePath

Write-Host "Loki 2.0 environment setup"
Write-Host "Writing local file: $EnvPath"
if (Test-Path -LiteralPath $SiblingEnvPath) {
    Write-Host "Existing Discord AI Relay values found and will be reused when you press Enter."
}
Write-Host "Secret values are never printed."
Write-Host ""

$schema = @(
    @{ Key = "DISCORD_TOKEN"; Label = "Discord bot token"; Required = $true; Secret = $true; Default = "" },
    @{ Key = "DISCORD_CLIENT_ID"; Label = "Discord application/client ID"; Required = $true; Secret = $false; Default = "" },
    @{ Key = "DISCORD_GUILD_ID"; Label = "Development Discord guild/server ID"; Required = $true; Secret = $false; Default = "" },
    @{ Key = "BOT_ADMIN_USER_IDS"; Label = "Admin Discord user IDs, comma-separated"; Required = $true; Secret = $false; Default = "" },
    @{ Key = "DATABASE_URL"; Label = "Database URL"; Required = $false; Secret = $false; Default = "sqlite:///loki-relay.db" },
    @{ Key = "OPENAI_API_KEY"; Label = "OpenAI API key for future LLM plugins"; Required = $false; Secret = $true; Default = "" },
    @{ Key = "OPENAI_MODEL"; Label = "OpenAI model"; Required = $false; Secret = $false; Default = "gpt-5-mini" },
    @{ Key = "BOT_ENV"; Label = "Bot environment"; Required = $false; Secret = $false; Default = "development" },
    @{ Key = "LOG_LEVEL"; Label = "Log level"; Required = $false; Secret = $false; Default = "info" },
    @{ Key = "MAX_ACTIVE_PLUGINS"; Label = "Max active plugins"; Required = $false; Secret = $false; Default = "8" },
    @{ Key = "HEALTH_PORT"; Label = "Health port"; Required = $false; Secret = $false; Default = "8080" },
    @{ Key = "RELAY_CONFIG_JSON"; Label = "Optional relay bootstrap JSON"; Required = $false; Secret = $false; Default = "" },
    @{ Key = "MEDIA_MODE"; Label = "Media mode: clean, button, or native_unfurl"; Required = $false; Secret = $false; Default = "clean" },
    @{ Key = "MEDIA_LINK_BUTTONS"; Label = "Show Open media buttons"; Required = $false; Secret = $false; Default = "false" },
    @{ Key = "WEBHOOK_RELAY_MODE"; Label = "Use webhook relay mode"; Required = $false; Secret = $false; Default = "false" },
    @{ Key = "ALLOW_BOT_RELAY"; Label = "Allow relaying bot-authored messages"; Required = $false; Secret = $false; Default = "false" },
    @{ Key = "AUTOCURATOR_ENABLED"; Label = "Enable autonomous curator stub"; Required = $false; Secret = $false; Default = "false" },
    @{ Key = "AUTOCURATOR_AUTOPOST"; Label = "Allow autonomous curator autopost"; Required = $false; Secret = $false; Default = "false" },
    @{ Key = "SERVER_SEARCH_ENABLED"; Label = "Enable server search stub"; Required = $false; Secret = $false; Default = "false" },
    @{ Key = "LLM_CHAT_ENABLED"; Label = "Enable LLM chat stub"; Required = $false; Secret = $false; Default = "false" },
    @{ Key = "MUSIC_ENABLED"; Label = "Enable music stub"; Required = $false; Secret = $false; Default = "false" },
    @{ Key = "RAILWAY_TOKEN"; Label = "Optional Railway token for CLI helpers"; Required = $false; Secret = $true; Default = "" },
    @{ Key = "RAILWAY_API_TOKEN"; Label = "Optional Railway API token for CLI helpers"; Required = $false; Secret = $true; Default = "" },
    @{ Key = "RAILWAY_PROJECT_ID"; Label = "Optional Railway project ID"; Required = $false; Secret = $false; Default = "" },
    @{ Key = "RAILWAY_PROJECT_NAME"; Label = "Optional Railway project name"; Required = $false; Secret = $false; Default = "loki-discord-relay" },
    @{ Key = "RAILWAY_SERVICE_NAME"; Label = "Optional Railway service name"; Required = $false; Secret = $false; Default = "loki-discord-relay" },
    @{ Key = "RAILWAY_SERVICE_ID"; Label = "Optional Railway service ID"; Required = $false; Secret = $false; Default = "" },
    @{ Key = "RAILWAY_ENVIRONMENT"; Label = "Optional Railway environment"; Required = $false; Secret = $false; Default = "production" }
)

$result = [ordered]@{}
foreach ($item in $schema) {
    $key = $item.Key
    $existing = Get-ExistingValue -Key $key -Current $current -Sibling $sibling -Example $example -Default $item.Default
    $result[$key] = Read-ConfigValue `
        -Key $key `
        -Label $item.Label `
        -Existing $existing `
        -Secret:([bool]$item.Secret) `
        -Required:([bool]$item.Required) `
        -NonInteractive:$NonInteractive
}

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# Loki 2.0 local environment")
$lines.Add("# Generated by Setup-Loki-Env.bat. Do not commit this file.")
foreach ($key in $result.Keys) {
    $lines.Add("$key=$(Format-DotEnvValue $result[$key])")
}

foreach ($key in $current.Keys) {
    if (-not $result.Contains($key)) {
        $lines.Add("$key=$(Format-DotEnvValue $current[$key])")
    }
}

Set-Content -LiteralPath $EnvPath -Value $lines -Encoding UTF8
Write-Host ""
Write-Host ".env updated. Stored keys:"
foreach ($key in $result.Keys) {
    if ($SecretKeys -contains $key -and $result[$key]) {
        Write-Host "  $key=<set>"
    }
    elseif ($SecretKeys -contains $key) {
        Write-Host "  $key=<empty>"
    }
    else {
        Write-Host "  $key=$($result[$key])"
    }
}

Write-Host ""
Write-Host "Next checks:"
Write-Host "  python -m pytest"
Write-Host "  python -m bot.main"
