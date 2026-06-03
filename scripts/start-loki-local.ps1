$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $RepoRoot ".env"

if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw ".env not found. Run Setup-Loki-Env.bat first."
}

function Import-DotEnvIntoProcess {
    param([string]$Path)
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
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

Import-DotEnvIntoProcess $EnvPath

# Railway private Postgres URLs are often unreachable from local Windows shells.
# Keep Railway DATABASE_URL in Railway, but use SQLite for this local launcher.
$env:DATABASE_URL = "sqlite:///loki-relay.db"
$env:BOT_ENV = "development"

Write-Host "Starting Loki locally with SQLite fallback."
Write-Host "The bot will connect to Discord and keep running until this window is closed."
python -m bot.main

