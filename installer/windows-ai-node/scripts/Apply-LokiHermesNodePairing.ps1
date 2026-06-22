<#
.SYNOPSIS
  Apply-LokiHermesNodePairing.ps1 applies a Loki Hermes Node pairing env file to a local Loki bot checkout.

.DESCRIPTION
  Use this on the PC that runs Loki when a separate Windows AI node has generated
  PAIR_WITH_LOKI.env. The script updates .env and Loki.env without printing or
  modifying Discord/OpenAI secrets.
#>
[CmdletBinding()]
param(
  [string]$PairingFile = "$PSScriptRoot\..\PAIR_WITH_LOKI.env",
  [string]$LokiRoot = (Get-Location).Path,
  [switch]$RestartGuardian
)

$ErrorActionPreference = 'Stop'

function Read-EnvFile([string]$Path) {
  if (-not (Test-Path $Path)) { throw "Pairing file not found: $Path" }
  $values = @{}
  foreach ($line in Get-Content -Path $Path) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith('#') -or -not $trimmed.Contains('=')) { continue }
    $key, $value = $trimmed.Split('=', 2)
    $values[$key.Trim()] = $value.Trim()
  }
  return $values
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

$pairing = Read-EnvFile -Path $PairingFile
$allowedKeys = @(
  'FAUST_AGI_BASE_URL',
  'FAUST_AGI_RUN_PATH',
  'FAUST_AGI_PROVIDER',
  'FAUST_AGI_ROUTE_MODE',
  'FAUST_AGI_EXECUTE',
  'FAUST_AGI_TARGET_COMPONENT',
  'FAUST_AGI_ADMIN_EXECUTE_ENABLED',
  'FAUST_AGI_ADMIN_TARGET_COMPONENT',
  'FAUST_AGI_ADMIN_WORKSPACE',
  'LLM_CHAT_ENABLED',
  'FAUST_AGI_ENABLED',
  'BOT_ADMIN_USER_IDS'
)
$updates = @{}
foreach ($key in $allowedKeys) {
  if ($pairing.ContainsKey($key)) { $updates[$key] = $pairing[$key] }
}
if (-not $updates.ContainsKey('FAUST_AGI_BASE_URL')) { throw 'PAIR_WITH_LOKI.env is missing FAUST_AGI_BASE_URL' }
if (-not $updates.ContainsKey('BOT_ADMIN_USER_IDS')) { Write-Warning 'PAIR_WITH_LOKI.env has no BOT_ADMIN_USER_IDS; existing local admin IDs will be preserved if present.' }

$envPath = Join-Path $LokiRoot '.env'
$lokiEnvPath = Join-Path $LokiRoot 'Loki.env'
Upsert-Env -Path $envPath -Values $updates
if (Test-Path $lokiEnvPath) { Upsert-Env -Path $lokiEnvPath -Values $updates }

Write-Host "Applied Loki/Hermes node pairing to: $envPath"
if (Test-Path $lokiEnvPath) { Write-Host "Applied pairing to: $lokiEnvPath" }
Write-Host "FAUST_AGI_BASE_URL=$($updates['FAUST_AGI_BASE_URL'])"
Write-Host 'Secrets were not printed or changed by this script.'

if ($RestartGuardian) {
  $guardian = Join-Path $LokiRoot 'Start-Loki-Guardian.bat'
  if (Test-Path $guardian) {
    Start-Process -FilePath $guardian -WorkingDirectory $LokiRoot
    Write-Host 'Requested Loki guardian restart via Start-Loki-Guardian.bat.'
  } else {
    Write-Warning "RestartGuardian requested, but Start-Loki-Guardian.bat was not found under $LokiRoot"
  }
}
