param([switch]$SkipDocker)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$model = "dolphin3:8b"
$ollamaHost = "http://127.0.0.1:11434"
$openAiBaseUrl = "$ollamaHost/v1"
$envPath = Join-Path $root ".env"
$envExamplePath = Join-Path $root ".env.example"

Set-Location $root

function Require-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name was not found. Install it or open a terminal where it is on PATH."
    }
}

function Wait-For-Ollama {
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        try {
            & curl.exe -fsS "$ollamaHost/api/tags" *> $null
            return
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    throw "Ollama did not become available at $ollamaHost."
}

function Invoke-Docker {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker.exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker.exe $($Arguments -join ' ') failed with exit code $LASTEXITCODE."
    }
}

function Set-EnvLine {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$Value
    )

    if (-not (Test-Path $Path)) {
        if (Test-Path $envExamplePath) {
            Copy-Item $envExamplePath $Path
        } else {
            New-Item -ItemType File -Path $Path | Out-Null
        }
    }

    $lines = [System.Collections.Generic.List[string]]::new()
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $lines.Add($line)
    }

    $pattern = "^\s*$([regex]::Escape($Key))="
    $found = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = "$Key=$Value"
            $found = $true
        }
    }

    if (-not $found) {
        if ($lines.Count -gt 0 -and $lines[$lines.Count - 1].Trim()) {
            $lines.Add("")
        }
        $lines.Add("$Key=$Value")
    }

    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllLines($Path, $lines, $utf8NoBom)
}

if (-not $SkipDocker) {
    Write-Host "Checking Docker..."
    Require-Command "docker.exe"
    Invoke-Docker version

    $existing = & docker.exe ps -a --filter "name=^/ollama$" --format "{{.Names}}"
    if (-not ($existing -contains "ollama")) {
        Write-Host "Creating Ollama Docker container..."
        Invoke-Docker run -d --name ollama -p "127.0.0.1:11434:11434" -v "ollama:/root/.ollama" "ollama/ollama"
    } else {
        Write-Host "Starting existing Ollama Docker container..."
        Invoke-Docker start ollama
    }

    Write-Host "Waiting for Ollama API..."
    Wait-For-Ollama

    Write-Host "Pulling $model. This can take a while the first time..."
    Invoke-Docker exec ollama ollama pull $model
}

Write-Host "Updating project .env for local Dolphin routing..."
Set-EnvLine -Path $envPath -Key "OLLAMA_HOST" -Value $ollamaHost
Set-EnvLine -Path $envPath -Key "OPENAI_BASE_URL" -Value $openAiBaseUrl
Set-EnvLine -Path $envPath -Key "OPENAI_API_KEY" -Value "ollama"
Set-EnvLine -Path $envPath -Key "LOKI_LLM_MODEL" -Value $model
Set-EnvLine -Path $envPath -Key "LOKI_NPC_HERMES_FALLBACK" -Value "true"

Write-Host ""
Write-Host "Dolphin local setup is ready."
Write-Host "Ollama API: $openAiBaseUrl"
Write-Host "Model: $model"
