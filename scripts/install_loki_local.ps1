[CmdletBinding()]
param(
    [string]$VenvPath,
    [string]$VerificationRoot,
    [string]$TrustedPythonLauncher,
    [string]$TrustedPythonRuntime,
    [string]$TrustedGitExecutable,
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
$hasTrustedLauncher = -not [string]::IsNullOrWhiteSpace($TrustedPythonLauncher)
$hasTrustedRuntime = -not [string]::IsNullOrWhiteSpace($TrustedPythonRuntime)
$hasTrustedGit = -not [string]::IsNullOrWhiteSpace($TrustedGitExecutable)
if (($hasTrustedLauncher -or $hasTrustedRuntime -or $hasTrustedGit) -and
    -not ($hasTrustedLauncher -and $hasTrustedRuntime -and $hasTrustedGit)) {
    throw "TrustedPythonLauncher, TrustedPythonRuntime, and TrustedGitExecutable must be supplied together."
}
if (-not $hasTrustedLauncher) {
    $launcher = (Get-Command py -ErrorAction Stop).Source
    $bootstrapPython = $launcher
    $bootstrapPrefix = @("-3.12")
    $gitExecutable = "git.exe"
} else {
    $expectedPowerShellHome = [System.IO.Path]::GetFullPath(
        "C:\Windows\System32\WindowsPowerShell\v1.0"
    )
    $currentProcess = [System.Diagnostics.Process]::GetCurrentProcess()
    try {
        $currentExecutable = [System.IO.Path]::GetFullPath(
            [string]$currentProcess.MainModule.FileName
        )
    } finally {
        $currentProcess.Dispose()
    }
    $expectedPowerShell = [System.IO.Path]::Combine(
        $expectedPowerShellHome,
        "powershell.exe"
    )
    if ($currentExecutable -ine $expectedPowerShell -or
        [System.IO.Path]::GetFullPath($PSHOME).TrimEnd("\") -ine $expectedPowerShellHome -or
        [string]$PSVersionTable.PSEdition -cne "Desktop" -or
        $PSVersionTable.PSVersion.Major -ne 5 -or
        $PSVersionTable.PSVersion.Minor -ne 1) {
        throw "Production preparation requires canonical Windows PowerShell 5.1."
    }
    $localCommandLine = [System.Environment]::GetCommandLineArgs()
    if ($localCommandLine.Length -lt 6 -or
        -not $localCommandLine[1].Equals("-NoProfile", [StringComparison]::OrdinalIgnoreCase) -or
        -not $localCommandLine[2].Equals("-ExecutionPolicy", [StringComparison]::OrdinalIgnoreCase) -or
        -not $localCommandLine[3].Equals("Bypass", [StringComparison]::OrdinalIgnoreCase) -or
        -not $localCommandLine[4].Equals("-File", [StringComparison]::OrdinalIgnoreCase) -or
        [System.IO.Path]::GetFullPath([string]$localCommandLine[5]) -ine
            [System.IO.Path]::GetFullPath($PSCommandPath)) {
        throw "Production preparation requires exact powershell.exe -NoProfile -ExecutionPolicy Bypass -File invocation."
    }
    $env:PSModulePath = [System.IO.Path]::Combine($expectedPowerShellHome, "Modules")
    if ([string]::IsNullOrWhiteSpace($env:TEMP) -or
        [string]::IsNullOrWhiteSpace($env:TMP) -or
        $env:TEMP -ine $env:TMP) {
        throw "Production verification TEMP and TMP must be the same protected directory."
    }
    $productionTemp = [System.IO.Path]::GetFullPath($env:TEMP)
    $expectedTempBase = [System.IO.Path]::GetFullPath(
        "C:\ProgramData\Loki\bootstrap"
    ).TrimEnd("\") + "\"
    if (-not $productionTemp.StartsWith(
        $expectedTempBase,
        [StringComparison]::OrdinalIgnoreCase
    ) -or -not [System.IO.Directory]::Exists($productionTemp)) {
        throw "Production verification TEMP must be under $expectedTempBase."
    }
    if (([System.IO.File]::GetAttributes($productionTemp) -band
        [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Production verification TEMP must not be a reparse point."
    }
    $launcher = [System.IO.Path]::GetFullPath($TrustedPythonLauncher)
    $expectedLauncher = [System.IO.Path]::GetFullPath("C:\Windows\py.exe")
    if ($launcher -ine $expectedLauncher) {
        throw "TrustedPythonLauncher must be exact system-wide launcher $expectedLauncher."
    }
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "TrustedPythonLauncher is missing: $launcher"
    }
    $launcherItem = Get-Item -LiteralPath $launcher -Force
    if (($launcherItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "TrustedPythonLauncher must not be a reparse point: $launcher"
    }
    $bootstrapPython = [System.IO.Path]::GetFullPath($TrustedPythonRuntime)
    $expectedRuntime = [System.IO.Path]::GetFullPath("C:\Program Files\Python312\python.exe")
    if ($bootstrapPython -ine $expectedRuntime) {
        throw "TrustedPythonRuntime must be exact machine-wide runtime $expectedRuntime."
    }
    if (-not (Test-Path -LiteralPath $bootstrapPython -PathType Leaf)) {
        throw "TrustedPythonRuntime is missing: $bootstrapPython"
    }
    $runtimeItem = Get-Item -LiteralPath $bootstrapPython -Force
    if (($runtimeItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "TrustedPythonRuntime must not be a reparse point: $bootstrapPython"
    }
    $gitExecutable = [System.IO.Path]::GetFullPath($TrustedGitExecutable)
    $expectedGit = [System.IO.Path]::GetFullPath("C:\Program Files\Git\cmd\git.exe")
    if ($gitExecutable -ine $expectedGit) {
        throw "TrustedGitExecutable must be exact machine-wide Git $expectedGit."
    }
    if (-not (Test-Path -LiteralPath $gitExecutable -PathType Leaf)) {
        throw "TrustedGitExecutable is missing: $gitExecutable"
    }
    $gitItem = Get-Item -LiteralPath $gitExecutable -Force
    if (($gitItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "TrustedGitExecutable must not be a reparse point: $gitExecutable"
    }
    $trustedProcessPath = [string]::Join(";", [string[]]@(
        $expectedPowerShellHome,
        "C:\Windows\System32",
        "C:\Windows",
        [System.IO.Path]::GetDirectoryName($bootstrapPython),
        [System.IO.Path]::GetDirectoryName($gitExecutable)
    ))
    $env:PATH = $trustedProcessPath
    $env:PATHEXT = ".COM;.EXE;.BAT;.CMD"
    $env:COMSPEC = "C:\Windows\System32\cmd.exe"
    $bootstrapPrefix = @()
}
$bootstrapVersion = Invoke-NativeText -FilePath $bootstrapPython -Arguments @(
    $bootstrapPrefix + @("-I", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))")
) -Label "Python 3.12 bootstrap validation"
if (-not $bootstrapVersion.StartsWith("3.12.")) {
    throw "Python bootstrap is not Python 3.12.x. Found $bootstrapVersion."
}

$releaseManifestPath = Join-Path $root "release-manifest.json"
if (Test-Path -LiteralPath $releaseManifestPath -PathType Leaf) {
    $releaseManifest = Get-Content -LiteralPath $releaseManifestPath -Raw | ConvertFrom-Json
    $candidateId = [string]$releaseManifest.candidate_id
    if ([string]::IsNullOrWhiteSpace($candidateId)) {
        throw "Release manifest does not contain a candidate_id."
    }
} else {
    $commit = Invoke-NativeText -FilePath $gitExecutable -Arguments @("-C", $root, "rev-parse", "--short=12", "HEAD") -Label "Git candidate lookup"
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
    $existingVersion = Invoke-NativeText -FilePath $venvPython -Arguments @("-E", "-s", "-B", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Existing virtual environment validation"
    if (-not $existingVersion.StartsWith("3.12.")) {
        throw "Existing virtual environment uses Python $existingVersion, not 3.12.x: $venv. It was preserved; choose a fresh -VenvPath."
    }
} elseif ($VerifyOnly) {
    throw "Virtual environment is missing: $venv"
} else {
    $venvParent = Split-Path -Parent $venv
    New-Item -ItemType Directory -Path $venvParent -Force | Out-Null
    Invoke-Native -FilePath $bootstrapPython -Arguments @(
        $bootstrapPrefix + @("-I", "-m", "venv", $venv)
    ) -Label "Python 3.12 virtual environment creation"
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Virtual environment creation failed: $venvPython"
}
$version = Invoke-NativeText -FilePath $venvPython -Arguments @("-E", "-s", "-B", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Virtual environment Python validation"
if (-not $version.StartsWith("3.12.")) {
    throw "LOKI requires Python 3.12.x; found $version in $venvPython. The existing environment was preserved."
}

if (-not $VerifyOnly) {
    Push-Location $root
    try {
        Invoke-Native -FilePath $venvPython -Arguments @("-E", "-s", "-B", "-m", "pip", "--isolated", "install", "--no-cache-dir", "--disable-pip-version-check", "-r", ".\requirements.txt", "-r", ".\requirements-dev.txt") -Label "Dependency installation"
        # pywin32's wheel does not always run its post-install copy step when
        # installed into a fresh venv. Invoke the wheel's script entrypoint so
        # pythonservice.exe is materialized in the venv root.
        $pywin32Postinstall = Join-Path (Split-Path -Parent $venvPython) "pywin32_postinstall.py"
        if (Test-Path -LiteralPath $pywin32Postinstall -PathType Leaf) {
            Invoke-Native -FilePath $venvPython -Arguments @("-E", "-s", "-B", $pywin32Postinstall, "-install", "-silent") -Label "pywin32 service-host post-install"
        }
        $venvWin32Dir = Join-Path $venv "Lib\site-packages\win32"
        $venvPackageServiceHost = Join-Path $venvWin32Dir "pythonservice.exe"
        if (-not (Test-Path -LiteralPath $venvPackageServiceHost -PathType Leaf)) {
            $wheelStaging = Join-Path (Split-Path -Parent $venv) ".pywin32-wheel-$candidateId"
            New-Item -ItemType Directory -Path $wheelStaging -Force | Out-Null
            try {
                Invoke-Native -FilePath $venvPython -Arguments @(
                    "-E", "-s", "-B", "-m", "pip", "--isolated", "download",
                    "--no-deps", "--no-cache-dir", "--only-binary=:all:",
                    "--dest", $wheelStaging, "pywin32==312"
                ) -Label "Pinned pywin32 wheel retrieval"
                Invoke-Native -FilePath $venvPython -Arguments @(
                    "-E", "-s", "-B", "-c",
                    "import pathlib,sys,zipfile; d=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2]); wheels=list(d.glob('pywin32-312-*.whl')); assert len(wheels)==1, f'expected one pywin32 wheel, found {len(wheels)}'; z=zipfile.ZipFile(wheels[0]); data=z.read('win32/pythonservice.exe'); out.mkdir(parents=True,exist_ok=True); (out/'pythonservice.exe').write_bytes(data)",
                    $wheelStaging, $venvWin32Dir
                ) -Label "pywin32 service-host extraction"
            } finally {
                if (Test-Path -LiteralPath $wheelStaging) {
                    [System.IO.Directory]::Delete($wheelStaging, $true)
                }
            }
        }
        $machinePackageServiceHost = Join-Path (Split-Path -Parent $bootstrapPython) "Lib\site-packages\win32\pythonservice.exe"
        if (-not (Test-Path -LiteralPath $venvPackageServiceHost -PathType Leaf) -and
            (Test-Path -LiteralPath $machinePackageServiceHost -PathType Leaf)) {
            New-Item -ItemType Directory -Path $venvWin32Dir -Force | Out-Null
            Copy-Item -LiteralPath $machinePackageServiceHost -Destination $venvPackageServiceHost -Force
        }
        $venvRootServiceHost = Join-Path $venv "pythonservice.exe"
        if (-not (Test-Path -LiteralPath $venvRootServiceHost -PathType Leaf) -and
            (Test-Path -LiteralPath $venvPackageServiceHost -PathType Leaf)) {
            Copy-Item -LiteralPath $venvPackageServiceHost -Destination $venvRootServiceHost -Force
        }
        if (-not (Test-Path -LiteralPath $venvPackageServiceHost -PathType Leaf) -or
            -not (Test-Path -LiteralPath $venvRootServiceHost -PathType Leaf)) {
            throw "pywin32 pythonservice.exe was not materialized in the release-specific venv. Expected: $venvPackageServiceHost and $venvRootServiceHost"
        }
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
    Invoke-Native -FilePath $venvPython -Arguments @("-E", "-s", "-B", "-c", "import win32service, win32cred") -Label "pywin32 import validation"
    Invoke-Native -FilePath $venvPython -Arguments @("-E", "-s", "-B", "-m", "compileall", "-q", "-x", "[\\/](?:.venv|venv|build|dist|__pycache__)[\\/]", ".") -Label "Python compile"
    # compileall writes bytecode beside sources even with -B; remove only
    # generated caches before immutable release verification.
    foreach ($cache in @(Get-ChildItem -LiteralPath $root -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction Stop)) {
        [System.IO.Directory]::Delete($cache.FullName, $true)
    }
    Invoke-Native -FilePath $venvPython -Arguments @("-E", "-s", "-B", "-m", "ruff", "check", ".") -Label "Ruff"
    Invoke-Native -FilePath $venvPython -Arguments @("-E", "-s", "-B", ".\scripts\secret_scan.py") -Label "Secret scan"
    Invoke-Native -FilePath $venvPython -Arguments @("-E", "-s", "-B", ".\local_loki_runtime.py", "--preflight") -Label "Local runtime preflight"
    Invoke-Native -FilePath $venvPython -Arguments @("-E", "-s", "-B", ".\scripts\release_check.py") -Label "Release check"
    Invoke-Native -FilePath $venvPython -Arguments @(
        "-E", "-s", "-B", "-m", "pytest", "tests", "-q",
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
