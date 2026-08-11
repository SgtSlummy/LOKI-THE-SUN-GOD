[CmdletBinding()]
param(
    [string]$VenvPath = ".venv",
    [switch]$IncludeDev,
    [switch]$VerifyOnly,
    [switch]$RunReleaseCheck
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$venv = if ([System.IO.Path]::IsPathRooted($VenvPath)) { $VenvPath } else { Join-Path $root $VenvPath }
$venvPython = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    if ($VerifyOnly) {
        throw "Virtual environment is missing: $venv"
    }
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $python312 = (& $launcher.Source -0p 2>$null | Where-Object { $_ -match "3\.12" } | ForEach-Object {
            if ($_ -match "(?<path>[A-Z]:\\.*python\.exe)\s*$") { $Matches.path }
        } | Select-Object -First 1)
        if ($python312 -and (Test-Path -LiteralPath $python312)) {
            & $python312 -m venv $venv
        } else {
            & $launcher.Source -3.12 -m venv $venv
        }
    } else {
        $python = (Get-Command python -ErrorAction Stop).Source
        & $python -m venv $venv
    }
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Virtual environment creation failed: $venvPython"
}

$version = (& $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
if (-not $version.StartsWith("3.12.")) {
    throw "LOKI requires Python 3.12.x from runtime.txt; found $version in $venvPython. Use -VenvPath with a fresh environment."
}

Set-Location $root
if (-not $VerifyOnly) {
    & $venvPython -m pip install --disable-pip-version-check -r .\requirements.txt
    if ($IncludeDev) {
        & $venvPython -m pip install --disable-pip-version-check -r .\requirements-dev.txt
    }
}

& $venvPython -m compileall -q .\local_loki_runtime.py .\tests\test_local_runtime.py
& $venvPython .\scripts\secret_scan.py
& $venvPython .\local_loki_runtime.py --preflight
if ($RunReleaseCheck) {
    & $venvPython .\scripts\release_check.py
}

Write-Output "LOKI local install prepared at $venv using Python $version. No Discord process was started."
