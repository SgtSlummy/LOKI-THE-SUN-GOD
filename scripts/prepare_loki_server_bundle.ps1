[CmdletBinding()]
param(
    [string]$OutputPath,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0

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

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$launcher = (Get-Command py -ErrorAction Stop).Source
$version = Invoke-NativeText -FilePath $launcher -Arguments @("-3.12", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Python 3.12 launcher validation"
if (-not $version.StartsWith("3.12.")) {
    throw "py -3.12 did not resolve Python 3.12.x. Found $version."
}
$commit = Invoke-NativeText -FilePath "git.exe" -Arguments @("-C", $root, "rev-parse", "--short=12", "HEAD") -Label "Git candidate lookup"
$candidateId = "loki-$commit"
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $root "handoff\$candidateId.zip"
} elseif (-not [System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path $root $OutputPath
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$arguments = @(
    (Join-Path $PSScriptRoot "release_manifest.py"),
    "build",
    "--source", $root,
    "--archive", $OutputPath
)
if ($Force) {
    $arguments += "--force"
}
$result = Invoke-NativeText -FilePath $launcher -Arguments (@("-3.12") + $arguments) -Label "Immutable release archive build"

$sidecarPath = "$OutputPath.sha256.json"
$textDigestPath = "$OutputPath.sha256"
foreach ($path in @($OutputPath, $sidecarPath, $textDigestPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Release builder did not create required artifact: $path"
    }
}
Invoke-NativeText -FilePath $launcher -Arguments @(
    "-3.12",
    (Join-Path $PSScriptRoot "release_manifest.py"),
    "verify-archive",
    "--archive", $OutputPath,
    "--sidecar", $sidecarPath
) -Label "Release archive verification" | Out-Null

Write-Output "Prepared immutable candidate $candidateId from committed HEAD."
Write-Output "Archive: $OutputPath"
Write-Output "SHA-256 evidence: $sidecarPath"
Write-Output "Portable digest: $textDigestPath"
