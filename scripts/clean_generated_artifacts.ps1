param(
    [switch]$IncludeNodeModules,
    [switch]$IncludeMythos,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$removed = New-Object System.Collections.Generic.List[string]

function Remove-GeneratedPath {
    param([string]$Path)

    $resolved = Join-Path $root $Path
    if (-not (Test-Path -LiteralPath $resolved)) {
        return
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force -WhatIf:$WhatIf
    if (-not $WhatIf) {
        $removed.Add($Path)
    }
}

function Test-SkippedPath {
    param([string]$FullName)

    $skipPrefixes = @(
        (Join-Path $root ".git"),
        (Join-Path $root ".venv"),
        (Join-Path $root "services\activity-bridge\node_modules")
    )
    foreach ($prefix in $skipPrefixes) {
        if ($FullName.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    }
    return $false
}

function Get-RelativePath {
    param([string]$FullName)

    if ($FullName.StartsWith($root, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $FullName.Substring($root.Length).TrimStart("\", "/")
    }
    return $FullName
}

$paths = @(
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
    "_tmp",
    "data\dashboard.log",
    "data\relay.log",
    "desktop_runtime.log",
    "tests\fixtures\mcp\generated",
    "winui\LokiOperator\Properties\PublishProfiles"
)

foreach ($path in $paths) {
    Remove-GeneratedPath $path
}

if ($IncludeNodeModules) {
    Remove-GeneratedPath "services\activity-bridge\node_modules"
}

if ($IncludeMythos) {
    Remove-GeneratedPath ".mythos"
}

Get-ChildItem -LiteralPath $root -Directory -Recurse -Force -Filter "__pycache__" |
    Where-Object { -not (Test-SkippedPath $_.FullName) } |
    ForEach-Object {
        $relative = Get-RelativePath $_.FullName
        Remove-Item -LiteralPath $_.FullName -Recurse -Force -WhatIf:$WhatIf
        if (-not $WhatIf) {
            $removed.Add($relative)
        }
    }

Get-ChildItem -LiteralPath $root -File -Recurse -Force |
    Where-Object {
        $_.Extension -in @(".pyc", ".pyo") -and -not (Test-SkippedPath $_.FullName)
    } |
    ForEach-Object {
        $relative = Get-RelativePath $_.FullName
        Remove-Item -LiteralPath $_.FullName -Force -WhatIf:$WhatIf
        if (-not $WhatIf) {
            $removed.Add($relative)
        }
    }

if ($removed.Count -eq 0) {
    Write-Host "No generated artifacts found."
} else {
    Write-Host "Generated artifacts removed:"
    $removed | Sort-Object -Unique | ForEach-Object { Write-Host "  $_" }
}
