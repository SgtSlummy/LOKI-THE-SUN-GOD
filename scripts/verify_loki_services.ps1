[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ReleaseRoot,
    [string]$VenvPath,
    [string]$ConfigPath = "C:\ProgramData\Loki\config\lokithesungod.env",
    [string]$ServiceAccount = "LOKI\Administrator",
    [string]$BotHealthUrl = "http://127.0.0.1:9101/healthz",
    [string]$DashboardHealthUrl = "http://127.0.0.1:5000/healthz",
    [switch]$ExerciseRecovery,
    [string]$RecoveryConfirmation
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 3.0
$serviceNames = @("LokiTHESunGodBot", "LokiTHESunGodDashboard")

function Assert-WindowsAdministrator {
    if ($env:OS -ne "Windows_NT") {
        throw "LOKI service verification is supported only on Windows."
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "LOKI service verification requires an elevated PowerShell session."
    }
    if ([string]$identity.Name -cne $ServiceAccount) {
        throw "Run verification as exact service identity $ServiceAccount so Credential Manager log scanning is authoritative."
    }
}

function Assert-StableConfig {
    param([Parameter(Mandatory = $true)][string]$Path)
    $effective = @{}
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }
        $parts = $line.Split(@("="), 2, [System.StringSplitOptions]::None)
        if ($parts.Count -ne 2) {
            continue
        }
        $name = $parts[0].Trim()
        $effective[$name] = $parts[1].Trim().Trim('"').Trim("'")
    }
    $required = @{
        "LOKI_LOCAL_ALLOW_FULL" = "true"
        "RELAY_ENABLED" = "false"
        "LOKI_ENABLE_SLASH_SYNC" = "false"
    }
    foreach ($name in $required.Keys) {
        if (-not $effective.ContainsKey($name) -or [string]$effective[$name] -cne [string]$required[$name]) {
            throw "Stable config commissioning flag failed: $name."
        }
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

function Assert-RecoveryPolicy {
    param([Parameter(Mandatory = $true)][string]$Name)
    $recovery = Invoke-NativeText -FilePath "sc.exe" -Arguments @("qfailure", $Name) -Label "SCM recovery query for $Name"
    foreach ($required in @("86400", "RESTART", "60000", "120000")) {
        if ($recovery -notmatch [regex]::Escape($required)) {
            throw "SCM recovery evidence for $Name is missing $required."
        }
    }
    $failureFlag = Invoke-NativeText -FilePath "sc.exe" -Arguments @("qfailureflag", $Name) -Label "SCM failureflag query for $Name"
    if ($failureFlag -notmatch "(?i)TRUE|1") {
        throw "SCM failureflag evidence for $Name does not enable non-crash recovery."
    }
}

function Get-MatchingChildren {
    param(
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$ExpectedCommand,
        [Parameter(Mandatory = $true)][uint32]$ParentPid,
        [Parameter(Mandatory = $true)][string]$PythonPath
    )
    $matches = @()
    foreach ($process in Get-CimInstance Win32_Process) {
        $command = [string]$process.CommandLine
        $scriptName = [System.IO.Path]::GetFileName($ScriptPath)
        if (-not $command -or $command.IndexOf($scriptName, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            continue
        }
        $normalized = ($command -replace '"', '').Trim()
        if ($normalized -ine $ExpectedCommand) {
            throw "A process for $([System.IO.Path]::GetFileName($ScriptPath)) has an unexpected command line; values were withheld."
        }
        if ([uint32]$process.ParentProcessId -ne $ParentPid) {
            throw "A process for $([System.IO.Path]::GetFileName($ScriptPath)) is not owned by its SCM service wrapper."
        }
        if ([string]$process.ExecutablePath -ine $PythonPath) {
            throw "A process for $([System.IO.Path]::GetFileName($ScriptPath)) uses the wrong Python executable."
        }
        $matches += $process
    }
    return @($matches)
}

function Assert-ServiceAndChild {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$ExpectedCommand,
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [Parameter(Mandatory = $true)][string]$Venv,
        [Parameter(Mandatory = $true)][string]$Release
    )
    $service = Get-CimInstance Win32_Service -Filter "Name='$Name'" -ErrorAction Stop
    if ([string]$service.State -cne "Running") {
        throw "Service $Name is not Running."
    }
    if ([string]$service.StartMode -cne "Auto") {
        throw "Service $Name is not configured for automatic startup."
    }
    if ([string]$service.StartName -cne $ServiceAccount) {
        throw "Service $Name does not use exact account $ServiceAccount."
    }
    $expectedServiceHost = '"' + (Join-Path $Venv "pythonservice.exe") + '"'
    if ([string]$service.PathName -ine $expectedServiceHost) {
        throw "Service $Name wrapper does not execute from the exact active release-specific venv."
    }
    $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
    $delayed = (Get-ItemProperty -LiteralPath $registryPath -Name DelayedAutoStart -ErrorAction Stop).DelayedAutoStart
    if ([int]$delayed -ne 1) {
        throw "Service $Name is not configured for delayed automatic startup."
    }
    $pythonClassKey = Get-Item -LiteralPath (Join-Path $registryPath "PythonClass") -ErrorAction Stop
    $pythonClass = [string]$pythonClassKey.GetValue("")
    if ($pythonClass.IndexOf($Release, [StringComparison]::OrdinalIgnoreCase) -lt 0) {
        throw "Service $Name PythonClass is not bound to the active release."
    }
    $requiredEnvironment = @(
        "LOKI_APP_ROOT=$Release",
        "LOKI_ENV_PATH=$ConfigPath",
        "LOKI_DB_PATH=$(Join-Path $env:ProgramData 'Loki\data\bot.db')",
        "PYTHONPYCACHEPREFIX=$(Join-Path $env:ProgramData "Loki\cache\$Name")"
    )
    $actualEnvironment = @((Get-ItemProperty -LiteralPath $registryPath -Name Environment -ErrorAction Stop).Environment)
    foreach ($entry in $requiredEnvironment) {
        if ($actualEnvironment -inotcontains $entry) {
            throw "Service $Name is missing a required external runtime path."
        }
    }
    Assert-RecoveryPolicy -Name $Name
    $children = @(Get-MatchingChildren -ScriptPath $ScriptPath -ExpectedCommand $ExpectedCommand -ParentPid ([uint32]$service.ProcessId) -PythonPath $PythonPath)
    if ($children.Count -ne 1) {
        throw "Service $Name must own exactly one expected child; found $($children.Count)."
    }
    return $children[0]
}

function Invoke-HealthCheck {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Kind
    )
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15
    if ([int]$response.StatusCode -ne 200) {
        throw "$Kind health returned HTTP $($response.StatusCode), not 200."
    }
    $payload = $response.Content | ConvertFrom-Json
    if ($payload.ok -ne $true) {
        throw "$Kind health did not report ok=true."
    }
    if ($Kind -ceq "Bot") {
        if ($payload.discord.connected -ne $true -or $payload.discord.ready -ne $true -or [string]$payload.state -cne "ready") {
            throw "Bot health is HTTP 200 but Discord is not ready."
        }
    }
    return $payload
}

function Wait-ForRecoveredChild {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$ScriptPath,
        [Parameter(Mandatory = $true)][string]$ExpectedCommand,
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [Parameter(Mandatory = $true)][string]$Venv,
        [Parameter(Mandatory = $true)][uint32]$OldPid
    )
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Seconds 2
        try {
            $child = Assert-ServiceAndChild -Name $Name -ScriptPath $ScriptPath -ExpectedCommand $ExpectedCommand -PythonPath $PythonPath -Venv $Venv -Release $ReleaseRoot
            if ([uint32]$child.ProcessId -ne $OldPid) {
                return $child
            }
        } catch {
            continue
        }
    }
    throw "SCM did not recover $Name with a replacement child within 180 seconds."
}

Assert-WindowsAdministrator
$commissionedServiceAccount = "LOKI\Administrator"
if ($ServiceAccount -cne $commissionedServiceAccount) {
    throw "ServiceAccount must be exact commissioned identity $commissionedServiceAccount."
}
$ReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseRoot)
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$commissionedConfigPath = [System.IO.Path]::GetFullPath("C:\ProgramData\Loki\config\lokithesungod.env")
if ($ConfigPath -ine $commissionedConfigPath) {
    throw "ConfigPath must be the commissioned stable path $commissionedConfigPath."
}
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Stable config is missing: $ConfigPath"
}
Assert-StableConfig -Path $ConfigPath
$manifestPath = Join-Path $ReleaseRoot "release-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Active release is missing release-manifest.json."
}
$releaseManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$candidateId = [string]$releaseManifest.candidate_id
if ([string]::IsNullOrWhiteSpace($candidateId)) {
    throw "Active release manifest is missing candidate_id."
}
$releaseLeaf = [System.IO.Path]::GetFileName($ReleaseRoot.TrimEnd("\"))
$releaseBase = [System.IO.Path]::GetFullPath((Join-Path $env:ProgramData "Loki\releases")).TrimEnd("\")
$releaseParent = [System.IO.Path]::GetDirectoryName($ReleaseRoot).TrimEnd("\")
if ($releaseLeaf -cne $candidateId -or $releaseParent -ine $releaseBase) {
    throw "Active release directory does not match its candidate_id."
}
if ([string]::IsNullOrWhiteSpace($VenvPath)) {
    $VenvPath = Join-Path $env:ProgramData "Loki\venvs\$candidateId"
}
$VenvPath = [System.IO.Path]::GetFullPath($VenvPath)
$venvBase = [System.IO.Path]::GetFullPath((Join-Path $env:ProgramData "Loki\venvs")).TrimEnd("\")
$venvParent = [System.IO.Path]::GetDirectoryName($VenvPath).TrimEnd("\")
$venvLeaf = [System.IO.Path]::GetFileName($VenvPath.TrimEnd("\"))
if ($venvParent -ine $venvBase -or $venvLeaf -cne $candidateId) {
    throw "Active venv directory does not match its candidate_id."
}
$venvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "Active service Python is missing: $venvPython"
}
$pythonVersion = Invoke-NativeText -FilePath $venvPython -Arguments @("-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Service Python version check"
if (-not $pythonVersion.StartsWith("3.12.")) {
    throw "Active service Python is $pythonVersion, not 3.12.x."
}
Invoke-Native -FilePath $venvPython -Arguments @("-c", "import win32service, win32cred") -Label "Service pywin32 import check"
$manifestHelper = Join-Path $ReleaseRoot "scripts\release_manifest.py"
Invoke-Native -FilePath $venvPython -Arguments @(
    "-B", $manifestHelper, "verify-directory", "--root", $ReleaseRoot
) -Label "Live immutable release verification"

$botScript = Join-Path $ReleaseRoot "local_loki_runtime.py"
$dashboardScript = Join-Path $ReleaseRoot "dashboard_app.py"
$botCommand = "$venvPython $botScript --mode full --host 127.0.0.1 --port 9101"
$dashboardCommand = "$venvPython $dashboardScript"
$botChild = Assert-ServiceAndChild -Name "LokiTHESunGodBot" -ScriptPath $botScript -ExpectedCommand $botCommand -PythonPath $venvPython -Venv $VenvPath -Release $ReleaseRoot
$dashboardChild = Assert-ServiceAndChild -Name "LokiTHESunGodDashboard" -ScriptPath $dashboardScript -ExpectedCommand $dashboardCommand -PythonPath $venvPython -Venv $VenvPath -Release $ReleaseRoot
Invoke-HealthCheck -Url $BotHealthUrl -Kind "Bot" | Out-Null
Invoke-HealthCheck -Url $DashboardHealthUrl -Kind "Dashboard" | Out-Null

$logRoot = Join-Path $env:ProgramData "Loki\logs"
$botLog = Join-Path $logRoot "bot-service.log"
$dashboardLog = Join-Path $logRoot "dashboard-service.log"
Invoke-Native -FilePath $venvPython -Arguments @(
    "-B", (Join-Path $ReleaseRoot "scripts\scan_service_logs.py"),
    "--env-path", $ConfigPath,
    $botLog, $dashboardLog
) -Label "Redacted service log scan"

$rollbackRoot = Join-Path $env:ProgramData "Loki\rollback"
$rollbackEvidence = Get-ChildItem -LiteralPath $rollbackRoot -Filter "service-config-*.json" -File -ErrorAction Stop |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if ($null -eq $rollbackEvidence) {
    throw "No rollback service configuration evidence was found."
}

if ($ExerciseRecovery) {
    if ([string]$RecoveryConfirmation -cne "EXERCISE LOKI SERVICE RECOVERY") {
        throw "-ExerciseRecovery requires -RecoveryConfirmation 'EXERCISE LOKI SERVICE RECOVERY'."
    }
    Stop-Process -Id ([int]$botChild.ProcessId) -Force -ErrorAction Stop
    $botChild = Wait-ForRecoveredChild -Name "LokiTHESunGodBot" -ScriptPath $botScript -ExpectedCommand $botCommand -PythonPath $venvPython -Venv $VenvPath -OldPid ([uint32]$botChild.ProcessId)
    Invoke-HealthCheck -Url $BotHealthUrl -Kind "Bot" | Out-Null

    Stop-Process -Id ([int]$dashboardChild.ProcessId) -Force -ErrorAction Stop
    $dashboardChild = Wait-ForRecoveredChild -Name "LokiTHESunGodDashboard" -ScriptPath $dashboardScript -ExpectedCommand $dashboardCommand -PythonPath $venvPython -Venv $VenvPath -OldPid ([uint32]$dashboardChild.ProcessId)
    Invoke-HealthCheck -Url $DashboardHealthUrl -Kind "Dashboard" | Out-Null
    Invoke-Native -FilePath $venvPython -Arguments @(
        "-B", (Join-Path $ReleaseRoot "scripts\scan_service_logs.py"),
        "--env-path", $ConfigPath,
        $botLog, $dashboardLog
    ) -Label "Post-recovery redacted service log scan"
}

Write-Output "PASS: both LOKI services are Running with one exact Python 3.12 child each."
Write-Output "PASS: delayed automatic startup, service identity, recovery actions, failureflag, health, and redacted logs verified."
Write-Output "Active candidate: $candidateId"
Write-Output "Rollback evidence retained: $($rollbackEvidence.FullName)"
