[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ReleaseRoot,
    [string]$VenvPath,
    [string]$ConfigPath = "C:\ProgramData\Loki\config\lokithesungod.env",
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [string]$SidecarPath,
    [switch]$PreserveExistingIdentity,
    [switch]$AllowNonStandardReleaseRoot
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$serviceAccount = "LOKI\Administrator"
$serviceNames = @("LokiTHESunGodBot", "LokiTHESunGodDashboard")

function Assert-WindowsAdministrator {
    if ($env:OS -ne "Windows_NT") {
        throw "LOKI service installation is supported only on Windows."
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "LOKI service installation requires an elevated PowerShell session."
    }
}

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

function Get-EffectiveConfig {
    param([Parameter(Mandatory = $true)][string]$Path)
    $effective = @{}
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }
        if ($line.StartsWith("export ")) {
            $line = $line.Substring(7).TrimStart()
        }
        $parts = $line.Split(@("="), 2, [System.StringSplitOptions]::None)
        if ($parts.Count -ne 2) {
            continue
        }
        $name = $parts[0].Trim()
        if ($name -match "^[A-Za-z_][A-Za-z0-9_]*$") {
            $effective[$name] = $parts[1].Trim().Trim('"').Trim("'")
        }
    }
    return $effective
}

function Assert-StableConfig {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Stable LOKI config is missing: $Path"
    }
    $effective = Get-EffectiveConfig -Path $Path
    $required = @{
        "LOKI_LOCAL_ALLOW_FULL" = "true"
        "RELAY_ENABLED" = "false"
        "LOKI_ENABLE_SLASH_SYNC" = "false"
    }
    foreach ($name in $required.Keys) {
        if (-not $effective.ContainsKey($name)) {
            throw "Stable LOKI config is missing required nonsecret flag $name."
        }
        if ([string]$effective[$name] -cne [string]$required[$name]) {
            throw "Stable LOKI config has an unsafe value for $name."
        }
    }
    Write-Output "Stable config nonsecret commissioning flags passed."
}

function Get-ServiceSnapshot {
    param([Parameter(Mandatory = $true)][string]$Name)
    $service = Get-CimInstance Win32_Service -Filter "Name='$Name'" -ErrorAction SilentlyContinue
    $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
    if ($null -eq $service) {
        return [ordered]@{ Name = $Name; Exists = $false }
    }
    $registry = Get-Item -LiteralPath $registryPath -ErrorAction SilentlyContinue
    $pythonClassKey = Get-Item -LiteralPath (Join-Path $registryPath "PythonClass") -ErrorAction SilentlyContinue
    $pythonClass = if ($null -ne $pythonClassKey) { [string]$pythonClassKey.GetValue("") } else { "" }
    $safeEnvironment = @()
    $rawEnvironment = if ($null -ne $registry) { $registry.GetValue("Environment", $null) } else { $null }
    if ($null -ne $rawEnvironment) {
        foreach ($entry in @($rawEnvironment)) {
            if ([string]$entry -match "^(LOKI_APP_ROOT|LOKI_ENV_PATH|LOKI_DB_PATH|PYTHONPYCACHEPREFIX)=") {
                $safeEnvironment += [string]$entry
            }
        }
    }
    return [ordered]@{
        Name = $Name
        Exists = $true
        State = [string]$service.State
        StartMode = [string]$service.StartMode
        StartName = [string]$service.StartName
        PathName = [string]$service.PathName
        PythonClass = $pythonClass
        DelayedAutoStart = if ($null -ne $registry) { [int]$registry.GetValue("DelayedAutoStart", 0) } else { 0 }
        NonsecretEnvironment = $safeEnvironment
    }
}

function Save-RollbackEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$CandidateId,
        [Parameter(Mandatory = $true)][string]$Release,
        [Parameter(Mandatory = $true)][string]$Venv
    )
    $rollbackRoot = Join-Path $env:ProgramData "Loki\rollback"
    New-Item -ItemType Directory -Force -Path $rollbackRoot | Out-Null
    $timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ")
    $path = Join-Path $rollbackRoot "service-config-$timestamp.json"
    $services = @()
    foreach ($name in $serviceNames) {
        $services += Get-ServiceSnapshot -Name $name
    }
    $evidence = [ordered]@{
        schema = "loki-service-rollback/v1"
        captured_at_utc = [DateTime]::UtcNow.ToString("o")
        incoming_candidate_id = $CandidateId
        incoming_release_root = $Release
        incoming_venv_path = $Venv
        services = $services
    }
    $evidence | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $path -Encoding UTF8
    return $path
}

function Assert-ServiceStopped {
    param([Parameter(Mandatory = $true)][string]$Name)
    $service = Get-CimInstance Win32_Service -Filter "Name='$Name'" -ErrorAction SilentlyContinue
    if ($null -ne $service -and [string]$service.State -ne "Stopped") {
        throw "Service $Name must be stopped before update. No service was changed."
    }
}

function Set-ServiceIdentitySecurely {
    param(
        [Parameter(Mandatory = $true)][System.Management.Automation.PSCredential]$Credential,
        [Parameter(Mandatory = $true)][string[]]$Names
    )
    $passwordPointer = [IntPtr]::Zero
    $passwordText = $null
    try {
        $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Credential.Password)
        $passwordText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
        foreach ($name in $Names) {
            $service = Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction Stop
            $change = Invoke-CimMethod -InputObject $service -MethodName Change -Arguments @{
                StartName = $serviceAccount
                StartPassword = $passwordText
            }
            if ([int]$change.ReturnValue -ne 0) {
                throw "Service account update failed for $name with Win32_Service return code $($change.ReturnValue)."
            }
        }
    } finally {
        $passwordText = $null
        if ($passwordPointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
            $passwordPointer = [IntPtr]::Zero
        }
    }
}

function Set-RecoveryPolicy {
    param([Parameter(Mandatory = $true)][string]$Name)
    Invoke-Native -FilePath "sc.exe" -Arguments @(
        "failure", $Name,
        "reset=", "86400",
        "actions=", 'restart/60000/restart/120000/""/0'
    ) -Label "SCM recovery policy for $Name"
    Invoke-Native -FilePath "sc.exe" -Arguments @("failureflag", $Name, "1") -Label "SCM non-crash failure flag for $Name"
    $recovery = Invoke-NativeText -FilePath "sc.exe" -Arguments @("qfailure", $Name) -Label "SCM recovery query for $Name"
    foreach ($required in @("86400", "RESTART", "60000", "120000")) {
        if ($recovery -notmatch [regex]::Escape($required)) {
            throw "SCM recovery query for $Name did not confirm $required."
        }
    }
    $failureFlag = Invoke-NativeText -FilePath "sc.exe" -Arguments @("qfailureflag", $Name) -Label "SCM failure flag query for $Name"
    if ($failureFlag -notmatch "(?i)TRUE|1") {
        throw "SCM failureflag query for $Name did not confirm non-crash recovery."
    }
}

Assert-WindowsAdministrator
$ReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseRoot)
$ArchivePath = [System.IO.Path]::GetFullPath($ArchivePath)
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$commissionedConfigPath = [System.IO.Path]::GetFullPath("C:\ProgramData\Loki\config\lokithesungod.env")
if ($ConfigPath -ine $commissionedConfigPath) {
    throw "ConfigPath must be the commissioned stable path $commissionedConfigPath."
}
if ([string]::IsNullOrWhiteSpace($SidecarPath)) {
    $SidecarPath = "$ArchivePath.sha256.json"
}
$SidecarPath = [System.IO.Path]::GetFullPath($SidecarPath)
foreach ($requiredFile in @($ArchivePath, $SidecarPath, $ConfigPath)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required deployment evidence/config file is missing: $requiredFile"
    }
}
if (-not (Test-Path -LiteralPath $ReleaseRoot -PathType Container)) {
    throw "Extracted release root is missing: $ReleaseRoot"
}

$sidecar = Get-Content -LiteralPath $SidecarPath -Raw | ConvertFrom-Json
$archiveFile = Get-Item -LiteralPath $ArchivePath
$archiveHash = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ([string]$sidecar.schema -cne "loki-release-archive-digest/v1") {
    throw "Archive SHA-256 sidecar schema is unsupported."
}
if ([string]$sidecar.archive_name -cne $archiveFile.Name) {
    throw "Archive SHA-256 sidecar does not bind this archive name."
}
if ([long]$sidecar.archive_size -ne [long]$archiveFile.Length) {
    throw "Archive SHA-256 sidecar size mismatch."
}
if ([string]$sidecar.archive_sha256 -cne $archiveHash) {
    throw "Transferred archive SHA-256 mismatch."
}

$launcher = (Get-Command py -ErrorAction Stop).Source
$launcherVersion = Invoke-NativeText -FilePath $launcher -Arguments @("-3.12", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Python 3.12 launcher validation"
if (-not $launcherVersion.StartsWith("3.12.")) {
    throw "py -3.12 did not resolve Python 3.12.x. Found $launcherVersion."
}
$manifestHelper = Join-Path $ReleaseRoot "scripts\release_manifest.py"
if (-not (Test-Path -LiteralPath $manifestHelper -PathType Leaf)) {
    throw "Extracted release is missing the manifest verifier."
}
$archiveManifestJson = Invoke-NativeText -FilePath $launcher -Arguments @(
    "-3.12", $manifestHelper,
    "verify-archive", "--archive", $ArchivePath, "--sidecar", $SidecarPath
) -Label "Transferred release archive verification"
$directoryManifestJson = Invoke-NativeText -FilePath $launcher -Arguments @(
    "-3.12", $manifestHelper,
    "verify-directory", "--root", $ReleaseRoot
) -Label "Extracted release manifest verification"
$archiveManifest = $archiveManifestJson | ConvertFrom-Json
$directoryManifest = $directoryManifestJson | ConvertFrom-Json
foreach ($field in @("candidate_id", "commit_id", "tree_id")) {
    if ([string]$archiveManifest.$field -cne [string]$directoryManifest.$field) {
        throw "Archive and extracted release evidence mismatch: $field"
    }
    if ([string]$archiveManifest.$field -cne [string]$sidecar.$field) {
        throw "Archive and SHA-256 sidecar evidence mismatch: $field"
    }
}
$candidateId = [string]$archiveManifest.candidate_id

if (-not $AllowNonStandardReleaseRoot) {
    $releaseBase = [System.IO.Path]::GetFullPath((Join-Path $env:ProgramData "Loki\releases")).TrimEnd("\")
    $actualParent = [System.IO.Path]::GetDirectoryName($ReleaseRoot).TrimEnd("\")
    $actualLeaf = [System.IO.Path]::GetFileName($ReleaseRoot.TrimEnd("\"))
    if ($actualParent -cne $releaseBase -or $actualLeaf -cne $candidateId) {
        throw "ReleaseRoot must be the versioned path $releaseBase\$candidateId."
    }
}
if ([string]::IsNullOrWhiteSpace($VenvPath)) {
    $VenvPath = Join-Path $env:ProgramData "Loki\venvs\$candidateId"
}
$VenvPath = [System.IO.Path]::GetFullPath($VenvPath)
$venvBase = [System.IO.Path]::GetFullPath((Join-Path $env:ProgramData "Loki\venvs")).TrimEnd("\")
$venvParent = [System.IO.Path]::GetDirectoryName($VenvPath).TrimEnd("\")
$venvLeaf = [System.IO.Path]::GetFileName($VenvPath.TrimEnd("\"))
if ($venvParent -ine $venvBase -or $venvLeaf -cne $candidateId) {
    throw "VenvPath must be the release-specific path $venvBase\$candidateId."
}
$venvPython = Join-Path $VenvPath "Scripts\python.exe"
$venvServiceHost = Join-Path $VenvPath "pythonservice.exe"
Assert-StableConfig -Path $ConfigPath
foreach ($name in $serviceNames) {
    Assert-ServiceStopped -Name $name
}
if ($PreserveExistingIdentity) {
    foreach ($name in $serviceNames) {
        $preservedService = Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction SilentlyContinue
        if ($null -eq $preservedService -or [string]$preservedService.StartName -cne $serviceAccount) {
            throw "-PreserveExistingIdentity requires existing $name to use exact account $serviceAccount."
        }
    }
}
$rollbackPath = Save-RollbackEvidence -CandidateId $candidateId -Release $ReleaseRoot -Venv $VenvPath

$previousAppRoot = $env:LOKI_APP_ROOT
$previousEnvPath = $env:LOKI_ENV_PATH
try {
    $env:LOKI_APP_ROOT = $ReleaseRoot
    $env:LOKI_ENV_PATH = $ConfigPath
    $powershell = Join-Path $PSHOME "powershell.exe"
    Invoke-Native -FilePath $powershell -Arguments @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $ReleaseRoot "scripts\install_loki_local.ps1"),
        "-VenvPath", $VenvPath,
        "-VerificationRoot", (Join-Path $env:ProgramData "Loki\verification\$candidateId")
    ) -Label "Release-specific Python 3.12 environment preparation"
} finally {
    $env:LOKI_APP_ROOT = $previousAppRoot
    $env:LOKI_ENV_PATH = $previousEnvPath
}
$postVerificationJson = Invoke-NativeText -FilePath $launcher -Arguments @(
    "-3.12", $manifestHelper,
    "verify-directory", "--root", $ReleaseRoot
) -Label "Post-test immutable release verification"
$postVerification = $postVerificationJson | ConvertFrom-Json
foreach ($field in @("candidate_id", "commit_id", "tree_id")) {
    if ([string]$postVerification.$field -cne [string]$archiveManifest.$field) {
        throw "Post-test immutable release evidence mismatch: $field"
    }
}
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Release-specific Python environment is missing after preparation: $venvPython"
}
if (-not (Test-Path -LiteralPath $venvServiceHost -PathType Leaf)) {
    throw "pywin32 service host is missing from the release-specific venv: $venvServiceHost"
}
$venvVersion = Invoke-NativeText -FilePath $venvPython -Arguments @("-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Service Python version validation"
if (-not $venvVersion.StartsWith("3.12.")) {
    throw "Service Python must be 3.12.x; found $venvVersion."
}
Invoke-Native -FilePath $venvPython -Arguments @("-c", "import win32service, win32cred") -Label "Service pywin32 import validation"

foreach ($name in $serviceNames) {
    $existing = Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction SilentlyContinue
    $wrapper = if ($name -ceq "LokiTHESunGodBot") {
        Join-Path $ReleaseRoot "scripts\loki_bot_service.py"
    } else {
        Join-Path $ReleaseRoot "scripts\loki_dashboard_service.py"
    }
    $action = if ($null -eq $existing) { "install" } else { "update" }
    Invoke-Native -FilePath $venvPython -Arguments @($wrapper, "--startup", "delayed", $action) -Label "$action service $name"
    $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$name"
    $serviceCache = Join-Path $env:ProgramData "Loki\cache\$name"
    $serviceData = Join-Path $env:ProgramData "Loki\data\bot.db"
    New-Item -ItemType Directory -Path (Split-Path -Parent $serviceData) -Force | Out-Null
    New-Item -ItemType Directory -Path $serviceCache -Force | Out-Null
    $serviceEnvironment = @(
        "LOKI_APP_ROOT=$ReleaseRoot",
        "LOKI_ENV_PATH=$ConfigPath",
        "LOKI_DB_PATH=$serviceData",
        "PYTHONPYCACHEPREFIX=$serviceCache"
    )
    New-ItemProperty -LiteralPath $registryPath -Name "Environment" -PropertyType MultiString -Value $serviceEnvironment -Force | Out-Null
}

$credential = $null
try {
    if ($PreserveExistingIdentity) {
        foreach ($name in $serviceNames) {
            $service = Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction Stop
            if ([string]$service.StartName -cne $serviceAccount) {
                throw "-PreserveExistingIdentity requires $name to already use exact account $serviceAccount."
            }
        }
    } else {
        $credential = Get-Credential -UserName $serviceAccount -Message "Enter the service logon credential for exact account $serviceAccount"
        if ($null -eq $credential -or [string]$credential.UserName -cne $serviceAccount) {
            throw "Service credential username must be exactly $serviceAccount."
        }
        Set-ServiceIdentitySecurely -Credential $credential -Names $serviceNames
    }
} finally {
    $credential = $null
}

foreach ($name in $serviceNames) {
    Set-RecoveryPolicy -Name $name
    $service = Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction Stop
    $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$name"
    $delayed = (Get-ItemProperty -LiteralPath $registryPath -Name DelayedAutoStart -ErrorAction Stop).DelayedAutoStart
    $pythonClassKey = Get-Item -LiteralPath (Join-Path $registryPath "PythonClass") -ErrorAction Stop
    $pythonClass = [string]$pythonClassKey.GetValue("")
    $expectedWrapper = if ($name -ceq "LokiTHESunGodBot") { "loki_bot_service" } else { "loki_dashboard_service" }
    $expectedEnvironment = @(
        "LOKI_APP_ROOT=$ReleaseRoot",
        "LOKI_ENV_PATH=$ConfigPath",
        "LOKI_DB_PATH=$(Join-Path $env:ProgramData 'Loki\data\bot.db')",
        "PYTHONPYCACHEPREFIX=$(Join-Path $env:ProgramData "Loki\cache\$name")"
    )
    $actualEnvironment = @((Get-ItemProperty -LiteralPath $registryPath -Name Environment -ErrorAction Stop).Environment)
    if ([string]$service.StartMode -cne "Auto" -or [int]$delayed -ne 1) {
        throw "Service $name is not configured for delayed automatic startup."
    }
    if ([string]$service.StartName -cne $serviceAccount) {
        throw "Service $name does not use exact account $serviceAccount."
    }
    if ([string]$service.PathName -ine ('"' + $venvServiceHost + '"')) {
        throw "Service $name image path does not bind the exact release-specific pythonservice.exe."
    }
    if ($pythonClass.IndexOf($ReleaseRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0 -or
        $pythonClass.IndexOf($expectedWrapper, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "Service $name PythonClass does not bind the exact active release wrapper."
    }
    foreach ($entry in $expectedEnvironment) {
        if ($actualEnvironment -inotcontains $entry) {
            throw "Service $name is missing required nonsecret environment path configuration."
        }
    }
    if ([string]$service.State -cne "Stopped") {
        throw "Service $name started unexpectedly; installer must leave services stopped."
    }
}
$finalVerificationJson = Invoke-NativeText -FilePath $launcher -Arguments @(
    "-3.12", $manifestHelper,
    "verify-directory", "--root", $ReleaseRoot
) -Label "Post-registration immutable release verification"
$finalVerification = $finalVerificationJson | ConvertFrom-Json
foreach ($field in @("candidate_id", "commit_id", "tree_id")) {
    if ([string]$finalVerification.$field -cne [string]$archiveManifest.$field) {
        throw "Post-registration immutable release evidence mismatch: $field"
    }
}

Write-Output "Installed candidate $candidateId with Python $venvVersion. Services remain stopped."
Write-Output "Rollback metadata: $rollbackPath"
Write-Output "Credential Manager values and service-account password were not logged or stored by this script."
