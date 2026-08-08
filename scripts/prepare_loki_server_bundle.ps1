[CmdletBinding()]
param(
    [string]$OutputPath,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
Set-Location $root
$commit = (& git rev-parse --short HEAD).Trim()
if (-not $OutputPath) {
    $OutputPath = Join-Path $root "handoff\loki-local-install-$commit.zip"
} elseif (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path $root $OutputPath
}

if ((Test-Path -LiteralPath $OutputPath) -and -not $Force) {
    throw "Output already exists: $OutputPath. Use -Force only when replacing this exact handoff artifact."
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null
& git archive --format=zip --prefix="loki-local-install-$commit/" --output="$OutputPath" HEAD
if (-not (Test-Path -LiteralPath $OutputPath)) {
    throw "Git archive was not created: $OutputPath"
}

Add-Type -AssemblyName System.IO.Compression
$archive = [System.IO.Compression.ZipFile]::OpenRead($OutputPath)
try {
    $unsafe = $archive.Entries | Where-Object {
        $_.FullName -match '(^|/)(\.env($|\.)|data/|runtime-logs/|\.venv/|\.git/)'
    }
    if ($unsafe) {
        throw "Handoff archive contains forbidden paths: $($unsafe.FullName -join ', ')"
    }
    $count = $archive.Entries.Count
} finally {
    $archive.Dispose()
}

Write-Output "Prepared $OutputPath from commit $commit ($count entries). No secrets, environment, database, logs, or Git metadata included."
