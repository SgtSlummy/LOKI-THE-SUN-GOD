param(
    [int]$Port = 2333,
    [switch]$InstallOnly
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$toolsDir = Join-Path $root "_tools"
$runtimeDir = Join-Path $root "_tmp\runtime"
$javaDir = Join-Path $toolsDir "java17"
$lavalinkDir = Join-Path $toolsDir "lavalink"
$lavalinkWorkDir = Join-Path $root "lavalink"
$jarPath = Join-Path $lavalinkDir "Lavalink.jar"

function Read-DotEnvValue {
    param([Parameter(Mandatory = $true)][string]$Name)
    $envPath = Join-Path $root ".env"
    if (-not (Test-Path $envPath)) {
        return ""
    }
    foreach ($line in [System.IO.File]::ReadLines($envPath)) {
        if ($line -match "^\s*$([regex]::Escape($Name))\s*=(.*)$") {
            return $matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return ""
}

function Ensure-Java17 {
    $existing = Get-ChildItem $javaDir -Recurse -Filter java.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($existing) {
        return $existing.FullName
    }
    New-Item -ItemType Directory -Force -Path $javaDir | Out-Null
    $api = "https://api.adoptium.net/v3/assets/latest/17/hotspot?architecture=x64&image_type=jre&os=windows&vendor=eclipse"
    $asset = (Invoke-RestMethod -Uri $api -Headers @{ "User-Agent" = "LOKI-Lavalink-Setup" })[0]
    $zipPath = Join-Path $javaDir "temurin17-jre.zip"
    Invoke-WebRequest -Uri $asset.binary.package.link -OutFile $zipPath -Headers @{ "User-Agent" = "LOKI-Lavalink-Setup" }
    Expand-Archive -LiteralPath $zipPath -DestinationPath $javaDir -Force
    $java = Get-ChildItem $javaDir -Recurse -Filter java.exe | Select-Object -First 1
    if (-not $java) {
        throw "java.exe was not found after extracting the portable JRE."
    }
    return $java.FullName
}

function Ensure-LavalinkJar {
    if (Test-Path $jarPath) {
        return $jarPath
    }
    New-Item -ItemType Directory -Force -Path $lavalinkDir | Out-Null
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/lavalink-devs/Lavalink/releases/latest" -Headers @{
        "User-Agent" = "LOKI-Lavalink-Setup"
    }
    $asset = $release.assets | Where-Object { $_.name -eq "Lavalink.jar" } | Select-Object -First 1
    if (-not $asset) {
        throw "The latest Lavalink release did not include Lavalink.jar."
    }
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $jarPath -Headers @{ "User-Agent" = "LOKI-Lavalink-Setup" }
    return $jarPath
}

function Test-LavalinkReady {
    param([Parameter(Mandatory = $true)][string]$Password)
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/v4/info" -Headers @{ Authorization = $Password } -TimeoutSec 5 | Out-Null
        return $true
    } catch {
        return $false
    }
}

$java = Ensure-Java17
$jar = Ensure-LavalinkJar
$lavalinkAuth = Read-DotEnvValue "LAVALINK_PASSWORD"
if (-not $lavalinkAuth) {
    $lavalinkAuth = "youshallnotpass"
}

if ($InstallOnly) {
    Write-Host "Java: $java"
    Write-Host "Lavalink: $jar"
    exit 0
}

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    if (Test-LavalinkReady -Password $lavalinkAuth) {
        Write-Host "Lavalink is already running on http://127.0.0.1:$Port"
        exit 0
    }
    throw "Port $Port is already in use, but Lavalink did not pass /v4/info."
}

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$outLog = Join-Path $runtimeDir "lavalink.out.log"
$errLog = Join-Path $runtimeDir "lavalink.err.log"
$escapedWorkDir = $lavalinkWorkDir.Replace("'", "''")
$escapedJava = $java.Replace("'", "''")
$escapedJar = $jar.Replace("'", "''")
$escapedPassword = $lavalinkAuth.Replace("'", "''")
$command = "`$env:LAVALINK_SERVER_PASSWORD='$escapedPassword'; `$env:PORT='$Port'; Set-Location '$escapedWorkDir'; & '$escapedJava' '-jar' '$escapedJar'"

Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command) `
    -WorkingDirectory $lavalinkWorkDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog | Out-Null

for ($attempt = 1; $attempt -le 30; $attempt++) {
    if (Test-LavalinkReady -Password $lavalinkAuth) {
        Write-Host "Lavalink is running on http://127.0.0.1:$Port"
        Write-Host "Log: $outLog"
        exit 0
    }
    Start-Sleep -Seconds 1
}

throw "Lavalink did not become ready. Check $outLog and $errLog."
