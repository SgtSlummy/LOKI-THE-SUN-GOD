<#
.SYNOPSIS
  One-click Windows installer for a Loki + Hermes + Ollama + Obsidian AI node.

.DESCRIPTION
  Installs or verifies Git, Python, Tailscale, Obsidian, Ollama, Hermes Agent,
  a Faust-compatible Loki bridge, a dedicated Hermes profile/memory home, and
  Windows startup persistence. Uses OpenAI Codex gpt-5.5 for primary reasoning
  and Ollama as local backup for cron/offline tasks. The node binds local
  services to 127.0.0.1 by default; use Tailscale Serve for tailnet access.
#>
[CmdletBinding()]
param(
  [string]$InstallRoot = "$env:LOCALAPPDATA\LokiHermesNode",
  [string]$HermesProfile = "loki-node",
  [int]$BridgePort = 8765,
  [int]$HermesApiPort = 9125,
  [switch]$NonInteractive
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$LogPath = Join-Path $InstallRoot 'install.log'
New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Start-Transcript -Path $LogPath -Append | Out-Null

function Write-Step([string]$Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Warn([string]$Message) { Write-Host "WARN: $Message" -ForegroundColor Yellow }
function Test-Command([string]$Name) { [bool](Get-Command $Name -ErrorAction SilentlyContinue) }
function Add-UserPath([string]$PathToAdd) {
  if (-not (Test-Path $PathToAdd)) { return }
  $current = [Environment]::GetEnvironmentVariable('Path','User')
  if (($current -split ';') -notcontains $PathToAdd) {
    [Environment]::SetEnvironmentVariable('Path', ($current.TrimEnd(';') + ';' + $PathToAdd), 'User')
    $env:Path += ';' + $PathToAdd
  }
}
function Install-WingetPackage([string]$Id, [string]$Name) {
  if (-not (Test-Command winget)) { Write-Warn "winget not found; skipping $Name auto-install."; return }
  Write-Step "Installing/verifying $Name"
  winget list --id $Id --exact --accept-source-agreements | Out-Null
  if ($LASTEXITCODE -ne 0) {
    winget install --id $Id --exact --silent --accept-source-agreements --accept-package-agreements
  }
}
function Read-SecretOrDefault([string]$Prompt, [string]$Default = '') {
  if ($NonInteractive) { return $Default }
  $value = Read-Host $Prompt
  if ([string]::IsNullOrWhiteSpace($value)) { return $Default }
  return $value.Trim()
}
function Upsert-Env([string]$Path, [hashtable]$Values) {
  $lines = @()
  if (Test-Path $Path) { $lines = Get-Content -Path $Path }
  $seen = @{}
  $out = New-Object System.Collections.Generic.List[string]
  foreach ($line in $lines) {
    if ($line -match '^([^#=]+)=') {
      $key = $Matches[1]
      if ($Values.ContainsKey($key)) {
        $out.Add("$key=$($Values[$key])")
        $seen[$key] = $true
        continue
      }
    }
    $out.Add($line)
  }
  foreach ($key in $Values.Keys) {
    if (-not $seen.ContainsKey($key)) { $out.Add("$key=$($Values[$key])") }
  }
  Set-Content -Path $Path -Value $out -Encoding UTF8
}
function Invoke-Optional([scriptblock]$Block, [string]$Description) {
  try { & $Block } catch { Write-Warn "$Description failed: $($_.Exception.Message)" }
}

try {
  Write-Step "Creating install layout"
  $PackageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
  $ScriptsDir = Join-Path $InstallRoot 'scripts'
  $ConfigDir = Join-Path $InstallRoot 'config'
  $VaultPath = Join-Path $env:USERPROFILE 'Obsidian\Loki-Hermes-Vault'
  $HermesHome = Join-Path $env:USERPROFILE ".hermes\profiles\$HermesProfile"
  New-Item -ItemType Directory -Force -Path $ScriptsDir,$ConfigDir,$VaultPath,$HermesHome | Out-Null

  Copy-Item -Force -Path (Join-Path $PackageRoot 'scripts\loki_hermes_bridge.py') -Destination $ScriptsDir
  Copy-Item -Force -Path (Join-Path $PackageRoot 'scripts\Start-LokiHermesNode.cmd') -Destination $InstallRoot
  Copy-Item -Force -Path (Join-Path $PackageRoot 'scripts\Apply-LokiHermesNodePairing.ps1') -Destination $ScriptsDir
  Copy-Item -Force -Path (Join-Path $PackageRoot 'templates\obsidian-loki-home.md') -Destination (Join-Path $VaultPath 'Loki Hermes Node.md')
  Copy-Item -Force -Path (Join-Path $PackageRoot 'prompts\install-aide-1bit.md') -Destination (Join-Path $ConfigDir 'install-aide-1bit.md')

  $ProjectRoot = Split-Path -Parent (Split-Path -Parent $PackageRoot)
  $LokiBotDir = Join-Path $InstallRoot 'LokiBot'
  if (Test-Path (Join-Path $ProjectRoot 'bot\main.py')) {
    Write-Step "Copying Loki Discord bot application"
    New-Item -ItemType Directory -Force -Path $LokiBotDir | Out-Null
    robocopy $ProjectRoot $LokiBotDir /MIR /XD .git .venv venv __pycache__ .pytest_cache logs /XF .env Loki.env loki-relay.db *.pyc | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed with exit code $LASTEXITCODE" }
  } else {
    Write-Warn "Could not find bot\main.py next to the installer. Copy the Loki repo to $LokiBotDir before starting the bot."
  }

  Write-Step "Installing system dependencies intelligently"
  Install-WingetPackage -Id 'Git.Git' -Name 'Git'
  Install-WingetPackage -Id 'Python.Python.3.11' -Name 'Python 3.11'
  Install-WingetPackage -Id 'Tailscale.Tailscale' -Name 'Tailscale'
  Install-WingetPackage -Id 'Obsidian.Obsidian' -Name 'Obsidian'
  Install-WingetPackage -Id 'Ollama.Ollama' -Name 'Ollama'
  Add-UserPath "$env:LOCALAPPDATA\Programs\Python\Python311"
  Add-UserPath "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts"
  Add-UserPath "$env:LOCALAPPDATA\Programs\Ollama"

  Write-Step "Installing/updating Hermes Agent"
  if (-not (Test-Command hermes)) {
    Invoke-Optional { powershell -NoProfile -ExecutionPolicy Bypass -Command "iwr https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.ps1 -UseBasicParsing | iex" } 'Hermes PowerShell installer'
    if (-not (Test-Command hermes) -and (Test-Command bash)) {
      bash -lc "curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash"
    }
  }

  Write-Step "Collecting local secrets and IDs"
  $DiscordToken = Read-SecretOrDefault 'Discord bot token (required for Loki on this PC; blank leaves placeholder)' 'REPLACE_WITH_DISCORD_BOT_TOKEN'
  $DiscordClientId = Read-SecretOrDefault 'Discord application/client ID' 'REPLACE_WITH_DISCORD_CLIENT_ID'
  $DiscordGuildId = Read-SecretOrDefault 'Discord guild ID for fast command sync' 'REPLACE_WITH_DISCORD_GUILD_ID'
  $BotAdmins = Read-SecretOrDefault 'BOT_ADMIN_USER_IDS comma list (required for /agent maintain)' 'REPLACE_WITH_DISCORD_ADMIN_USER_ID'
  $OpenAIKey = Read-SecretOrDefault 'OpenAI/Codex API key or OAuth marker for Hermes primary gpt-5.5' 'REPLACE_WITH_OPENAI_API_KEY'
  $TailscaleHost = Read-SecretOrDefault 'Tailscale HTTPS hostname for this node, e.g. pc.tailnet.ts.net (blank = local only)' ''

  Write-Step "Configuring Ollama backup models and 1-bit install aide"
  Invoke-Optional { Start-Process -FilePath 'ollama' -ArgumentList 'serve' -WindowStyle Hidden } 'starting Ollama service'
  Start-Sleep -Seconds 3
  Invoke-Optional { ollama pull llama3.2:3b } 'pulling Ollama backup model llama3.2:3b'
  Invoke-Optional { ollama pull qwen2.5-coder:1.5b } 'pulling Ollama cron/coding backup model qwen2.5-coder:1.5b'
  # 1-bit LLM aide: prefer a BitNet GGUF if already available; otherwise keep the prompt ready for the local backup model.
  $BitnetModelPath = Join-Path $InstallRoot 'models\bitnet-b1.58.gguf'
  New-Item -ItemType Directory -Force -Path (Split-Path $BitnetModelPath) | Out-Null
  if (Test-Path $BitnetModelPath) {
    $Modelfile = Join-Path $InstallRoot 'models\Modelfile.bitnet-install-aide'
    Set-Content -Path $Modelfile -Encoding UTF8 -Value "FROM $BitnetModelPath`nSYSTEM `"You are a 1-bit BitNet install aide for Loki Hermes Node. Optimize prompts, diagnose installer failures, and propose safe Windows fixes.`""
    Invoke-Optional { ollama create bitnet-install-aide -f $Modelfile } 'creating bitnet-install-aide model'
  } else {
    Write-Warn "Optional 1-bit BitNet GGUF not found at $BitnetModelPath; installer will use qwen2.5-coder:1.5b with the 1-bit aide prompt until you drop a BitNet GGUF there."
  }

  Write-Step "Writing dedicated Hermes profile, memory, cron, and env"
  $HermesConfigTemplate = Get-Content -Raw -Path (Join-Path $PackageRoot 'templates\hermes-config.yaml.template')
  $HermesConfig = $HermesConfigTemplate.Replace('{{HERMES_API_PORT}}', [string]$HermesApiPort).Replace('{{OBSIDIAN_VAULT}}', ($VaultPath -replace '\\','/'))
  Set-Content -Path (Join-Path $HermesHome 'config.yaml') -Value $HermesConfig -Encoding UTF8
  $HermesEnvTemplate = Get-Content -Raw -Path (Join-Path $PackageRoot 'templates\hermes-env.template')
  $HermesEnv = $HermesEnvTemplate.Replace('REPLACE_WITH_OPENAI_API_KEY', $OpenAIKey)
  Set-Content -Path (Join-Path $HermesHome '.env') -Value $HermesEnv -Encoding UTF8
  New-Item -ItemType Directory -Force -Path (Join-Path $HermesHome 'memories'),(Join-Path $HermesHome 'cron'),(Join-Path $HermesHome 'skills') | Out-Null
  Set-Content -Path (Join-Path $HermesHome 'memories\README.md') -Encoding UTF8 -Value "# Loki Hermes Node Memory`nDedicated memory for this autonomous Windows node. Do not mix with personal/default Hermes memory.`n"

  Write-Step "Writing Loki/Faust bridge configuration"
  # Required Loki admin self-maintenance switch: FAUST_AGI_ADMIN_EXECUTE_ENABLED=true
  $NodeEnv = Join-Path $InstallRoot 'loki-node.env'
  $FaustBaseLocal = "http://127.0.0.1:$BridgePort"
  $FaustBaseTail = if ($TailscaleHost) { "https://$TailscaleHost" } else { $FaustBaseLocal }
  Upsert-Env -Path $NodeEnv -Values @{
    DISCORD_TOKEN=$DiscordToken
    DISCORD_CLIENT_ID=$DiscordClientId
    DISCORD_GUILD_ID=$DiscordGuildId
    BOT_ADMIN_USER_IDS=$BotAdmins
    DATABASE_URL='sqlite:///loki-relay.db'
    OPENAI_API_KEY=$OpenAIKey
    OPENAI_MODEL='gpt-5.5'
    LLM_CHAT_ENABLED='true'
    FAUST_AGI_ENABLED='true'
    FAUST_AGI_BASE_URL=$FaustBaseLocal
    FAUST_AGI_RUN_PATH='/api/faust/run'
    FAUST_AGI_ROUTE_MODE='local_first'
    FAUST_AGI_PROVIDER='codex'
    FAUST_AGI_EXECUTE='false'
    FAUST_AGI_TARGET_COMPONENT='discord'
    FAUST_AGI_ADMIN_EXECUTE_ENABLED='true'
    FAUST_AGI_ADMIN_TARGET_COMPONENT='loki_self'
    FAUST_AGI_ADMIN_WORKSPACE='.'
    HERMES_HOME=$HermesHome
    HERMES_PROFILE=$HermesProfile
    HERMES_PRIMARY_PROVIDER='openai-codex'
    HERMES_PRIMARY_MODEL='gpt-5.5'
    HERMES_BACKUP_PROVIDER='ollama'
    HERMES_BACKUP_MODEL='llama3.2:3b'
    HERMES_CRON_MODEL='qwen2.5-coder:1.5b'
    LOKI_HERMES_BRIDGE_PORT=[string]$BridgePort
    LOKI_HERMES_OBSIDIAN_VAULT=$VaultPath
    LOKI_HERMES_TAILSCALE_URL=$FaustBaseTail
  }

  Write-Step "Writing pairing package for this PC and Loki"
  $PairingPath = Join-Path $InstallRoot 'PAIR_WITH_LOKI.env'
  $PairCmd = Join-Path $InstallRoot 'PAIR_WITH_THIS_PC.cmd'
  $PairingLines = @(
    '# Copy this file to the PC that runs Loki, then run scripts\Apply-LokiHermesNodePairing.ps1 from the Loki repo or this package.',
    "FAUST_AGI_BASE_URL=$FaustBaseTail",
    'FAUST_AGI_RUN_PATH=/api/faust/run',
    'FAUST_AGI_PROVIDER=codex',
    'FAUST_AGI_ROUTE_MODE=local_first',
    'FAUST_AGI_EXECUTE=false',
    'FAUST_AGI_TARGET_COMPONENT=discord',
    'FAUST_AGI_ADMIN_EXECUTE_ENABLED=true',
    'FAUST_AGI_ADMIN_TARGET_COMPONENT=loki_self',
    'FAUST_AGI_ADMIN_WORKSPACE=.',
    'LLM_CHAT_ENABLED=true',
    'FAUST_AGI_ENABLED=true',
    "BOT_ADMIN_USER_IDS=$BotAdmins"
  )
  Set-Content -Path $PairingPath -Value $PairingLines -Encoding UTF8
  Set-Content -Path $PairCmd -Encoding ASCII -Value @"
@echo off
setlocal
cd /d "%~dp0"
echo This applies PAIR_WITH_LOKI.env to a Loki checkout on this PC.
echo If this file is still on the remote AI node, copy PAIR_WITH_LOKI.env and scripts\Apply-LokiHermesNodePairing.ps1 to the Loki PC first.
set /p LOKI_ROOT=Path to local Loki repo [%%USERPROFILE%%\Documents\Loki 2.0]: 
if "%%LOKI_ROOT%%"=="" set "LOKI_ROOT=%%USERPROFILE%%\Documents\Loki 2.0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Apply-LokiHermesNodePairing.ps1" -PairingFile "%~dp0PAIR_WITH_LOKI.env" -LokiRoot "%%LOKI_ROOT%%"
pause
"@

  Write-Step "Installing Python bridge dependencies"
  python -m pip install --upgrade pip | Out-Null
  python -m pip install requests python-dotenv | Out-Null

  Write-Step "Creating Windows startup shortcut"
  $StartupDir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
  New-Item -ItemType Directory -Force -Path $StartupDir | Out-Null
  if (Test-Path $LokiBotDir) {
    Copy-Item -Force -Path $NodeEnv -Destination (Join-Path $LokiBotDir '.env')
  }
  $Launcher = Join-Path $InstallRoot 'Start-LokiHermesNode.cmd'
  $LauncherContent = Get-Content -Raw -Path (Join-Path $PackageRoot 'scripts\Start-LokiHermesNode.cmd')
  $LauncherContent = $LauncherContent.Replace('{{INSTALL_ROOT}}', $InstallRoot).Replace('{{BRIDGE_PORT}}', [string]$BridgePort).Replace('{{HERMES_API_PORT}}', [string]$HermesApiPort)
  Set-Content -Path $Launcher -Value $LauncherContent -Encoding ASCII
  Copy-Item -Force -Path $Launcher -Destination (Join-Path $StartupDir 'Start-LokiHermesNode.cmd')

  Write-Step "Configuring Tailscale Serve for Hermexj/iOS tailnet access when possible"
  $TailscaleExe = "$env:ProgramFiles\Tailscale\tailscale.exe"
  if (Test-Path $TailscaleExe) {
    Invoke-Optional { & $TailscaleExe status | Out-Host } 'checking Tailscale login'
    Invoke-Optional { & $TailscaleExe serve --bg --yes "http://127.0.0.1:$BridgePort" } 'Tailscale Serve bridge exposure'
  } else {
    Write-Warn 'Tailscale executable not found after install. Log in to Tailscale, then run: tailscale serve --bg --yes http://127.0.0.1:<bridgePort>'
  }

  Write-Step "Starting Loki Hermes Node now"
  Start-Process -FilePath $Launcher -WindowStyle Minimized
  Start-Sleep -Seconds 5
  try {
    $Health = Invoke-RestMethod -Uri "http://127.0.0.1:$BridgePort/healthz" -TimeoutSec 5
    Write-Host "Bridge health: $($Health.ok), provider: $($Health.primary_provider), backup: $($Health.backup_model)"
  } catch {
    Write-Warn "Bridge health was not ready yet. It will continue starting from $Launcher."
  }

  Write-Step "Install complete"
  Write-Host "Loki FAUST_AGI_BASE_URL: $FaustBaseLocal"
  Write-Host "Hermexj/iOS tailnet URL: $FaustBaseTail"
  Write-Host "Dedicated Hermes profile: $HermesProfile at $HermesHome"
  Write-Host "Obsidian vault: $VaultPath"
  Write-Host "Local config/env: $NodeEnv"
  Write-Host "Startup launcher: $(Join-Path $StartupDir 'Start-LokiHermesNode.cmd')"
}
finally {
  Stop-Transcript | Out-Null
}
