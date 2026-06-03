$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvPath = Join-Path $RepoRoot ".env"

if (-not (Test-Path -LiteralPath $EnvPath)) {
    throw ".env not found. Run Setup-Loki-Env.bat first."
}

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
        [Environment]::SetEnvironmentVariable($key, $value, "Process")
    }
}

if (-not $env:ANTHROPIC_API_KEY -and -not $env:OPENAI_API_KEY -and -not $env:DEEPSEEK_API_KEY) {
    throw "No Mythos provider key is available. Add ANTHROPIC_API_KEY, OPENAI_API_KEY, or DEEPSEEK_API_KEY to .env."
}

Write-Host "Starting Mythos chat with the loki-relay project skill."
Write-Host "Provider keys are loaded into this process only and will not be printed."
npx -y mythos-router chat -s loki-relay
