[CmdletBinding()]
param(
    [string]$VenvPath,
    [string]$VerificationRoot,
    [switch]$IncludeDev,
    [switch]$VerifyOnly,
    [switch]$RunReleaseCheck
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label
    )
    & $FilePath @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Label failed with exit code $exitCode."
    }
}

function Invoke-NativeText {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $output = (& $FilePath @Arguments 2>&1 | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Label failed with exit code $exitCode."
    }
    return $output
}

$root = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$launcherCommand = Get-Command py -ErrorAction Stop
$launcher = $launcherCommand.Source
$launcherVersion = Invoke-NativeText -FilePath $launcher -Arguments @("-3.12", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Python 3.12 launcher validation"
if (-not $launcherVersion.StartsWith("3.12.")) {
    throw "py -3.12 did not resolve Python 3.12.x. Found $launcherVersion."
}

$releaseManifestPath = Join-Path $root "release-manifest.json"
if (Test-Path -LiteralPath $releaseManifestPath -PathType Leaf) {
    $releaseManifest = Get-Content -LiteralPath $releaseManifestPath -Raw | ConvertFrom-Json
    $candidateId = [string]$releaseManifest.candidate_id
    if ([string]::IsNullOrWhiteSpace($candidateId)) {
        throw "Release manifest does not contain a candidate_id."
    }
} else {
    $commit = Invoke-NativeText -FilePath "git.exe" -Arguments @("-C", $root, "rev-parse", "--short=12", "HEAD") -Label "Git candidate lookup"
    $candidateId = "loki-$commit"
}
if ([string]::IsNullOrWhiteSpace($VenvPath)) {
    $localVenvRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Loki\venvs"
    $VenvPath = Join-Path $localVenvRoot $candidateId
}
$venv = if ([System.IO.Path]::IsPathRooted($VenvPath)) {
    [System.IO.Path]::GetFullPath($VenvPath)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $root $VenvPath))
}
$venvPython = Join-Path $venv "Scripts\python.exe"

if (Test-Path -LiteralPath $venv) {
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        throw "Existing venv target is not a usable Windows virtual environment: $venv. It was preserved."
    }
    $existingVersion = Invoke-NativeText -FilePath $venvPython -Arguments @("-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Existing virtual environment validation"
    if (-not $existingVersion.StartsWith("3.12.")) {
        throw "Existing virtual environment uses Python $existingVersion, not 3.12.x: $venv. It was preserved; choose a fresh -VenvPath."
    }
} elseif ($VerifyOnly) {
    throw "Virtual environment is missing: $venv"
} else {
    $venvParent = Split-Path -Parent $venv
    New-Item -ItemType Directory -Path $venvParent -Force | Out-Null
    Invoke-Native -FilePath $launcher -Arguments @("-3.12", "-m", "venv", $venv) -Label "Python 3.12 virtual environment creation"
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Virtual environment creation failed: $venvPython"
}
$version = Invoke-NativeText -FilePath $venvPython -Arguments @("-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Virtual environment Python validation"
if (-not $version.StartsWith("3.12.")) {
    throw "LOKI requires Python 3.12.x; found $version in $venvPython. The existing environment was preserved."
}

if (-not $VerifyOnly) {
    Push-Location $root
    try {
        Invoke-Native -FilePath $venvPython -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "-r", ".\requirements.txt", "-r", ".\requirements-dev.txt") -Label "Dependency installation"
    } finally {
        Pop-Location
    }
}

if ([string]::IsNullOrWhiteSpace($VerificationRoot)) {
    $VerificationRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "Loki\verification\$candidateId"
}
$VerificationRoot = [System.IO.Path]::GetFullPath($VerificationRoot)
if ($VerificationRoot -ieq $root -or
    $VerificationRoot.StartsWith($root.TrimEnd("\") + "\", [StringComparison]::OrdinalIgnoreCase)) {
    throw "VerificationRoot must be outside the source/release root."
}
$verificationDbPath = Join-Path $VerificationRoot "data\bot.db"
$verificationPycache = Join-Path $VerificationRoot "pycache"
$verificationRuffCache = Join-Path $VerificationRoot "ruff-cache"
$testBase = Join-Path $VerificationRoot "pytest-$PID"
foreach ($directory in @(
    (Split-Path -Parent $verificationDbPath),
    $verificationPycache,
    $verificationRuffCache,
    (Split-Path -Parent $testBase)
)) {
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
}

$previousDbPath = $env:LOKI_DB_PATH
$previousPycache = $env:PYTHONPYCACHEPREFIX
$previousRuffCache = $env:RUFF_CACHE_DIR
$previousLocation = Get-Location
try {
    $env:LOKI_DB_PATH = $verificationDbPath
    $env:PYTHONPYCACHEPREFIX = $verificationPycache
    $env:RUFF_CACHE_DIR = $verificationRuffCache
    Set-Location $root
    Invoke-Native -FilePath $venvPython -Arguments @("-c", "import win32service, win32cred") -Label "pywin32 import validation"
    Invoke-Native -FilePath $venvPython -Arguments @("-m", "compileall", "-q", "-x", "[\\/](?:.venv|venv|build|dist|__pycache__)[\\/]", ".") -Label "Python compile"
    Invoke-Native -FilePath $venvPython -Arguments @("-m", "ruff", "check", ".") -Label "Ruff"
    Invoke-Native -FilePath $venvPython -Arguments @(".\scripts\secret_scan.py") -Label "Secret scan"
    Invoke-Native -FilePath $venvPython -Arguments @(".\local_loki_runtime.py", "--preflight") -Label "Local runtime preflight"
    Invoke-Native -FilePath $venvPython -Arguments @(".\scripts\release_check.py") -Label "Release check"
    Invoke-Native -FilePath $venvPython -Arguments @(
        "-m", "pytest", "tests", "-q",
        "-p", "no:cacheprovider",
        "--basetemp", $testBase
    ) -Label "Local test suite"
} finally {
    $env:LOKI_DB_PATH = $previousDbPath
    $env:PYTHONPYCACHEPREFIX = $previousPycache
    $env:RUFF_CACHE_DIR = $previousRuffCache
    Set-Location $previousLocation
}

Write-Output "LOKI candidate $candidateId verified at $venv using Python $version. No Discord process was started."
