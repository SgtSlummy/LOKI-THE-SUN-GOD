[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ReleaseRoot,
    [string]$VenvPath,
    [string]$ConfigPath = "C:\ProgramData\Loki\config\lokithesungod.env",
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [Parameter(Mandatory = $true)][string]$ExpectedArchiveSha256,
    [Parameter(Mandatory = $true)][string]$TrustedPythonLauncher,
    [Parameter(Mandatory = $true)][string]$TrustedPythonRuntime,
    [Parameter(Mandatory = $true)][string]$TrustedGitExecutable,
    [string]$SidecarPath,
    [switch]$PreserveExistingIdentity,
    [switch]$ReuseExistingVenv,
    [switch]$EvidenceOnly
)

function Assert-TrustedWindowsPowerShellHost {
    $expectedHome = [System.IO.Path]::GetFullPath(
        "C:\Windows\System32\WindowsPowerShell\v1.0"
    )
    $expectedExecutable = [System.IO.Path]::Combine($expectedHome, "powershell.exe")
    if ([string]$PSVersionTable.PSEdition -cne "Desktop" -or
        $PSVersionTable.PSVersion.Major -ne 5 -or
        $PSVersionTable.PSVersion.Minor -ne 1 -or
        [System.IO.Path]::GetFullPath($PSHOME).TrimEnd("\") -ine $expectedHome) {
        throw "LOKI service tooling requires canonical Windows PowerShell 5.1."
    }
    $process = [System.Diagnostics.Process]::GetCurrentProcess()
    try {
        $actualExecutable = [System.IO.Path]::GetFullPath(
            [string]$process.MainModule.FileName
        )
    } finally {
        $process.Dispose()
    }
    if ($actualExecutable -ine $expectedExecutable) {
        throw "LOKI service tooling requires canonical host $expectedExecutable."
    }
    $arguments = [System.Environment]::GetCommandLineArgs()
    if ($arguments.Length -lt 6 -or
        -not $arguments[1].Equals("-NoProfile", [StringComparison]::OrdinalIgnoreCase) -or
        -not $arguments[2].Equals("-ExecutionPolicy", [StringComparison]::OrdinalIgnoreCase) -or
        -not $arguments[3].Equals("Bypass", [StringComparison]::OrdinalIgnoreCase) -or
        -not $arguments[4].Equals("-File", [StringComparison]::OrdinalIgnoreCase)) {
        throw "LOKI service tooling requires exact powershell.exe -NoProfile ... -File invocation."
    }
    $invokedScript = [System.IO.Path]::GetFullPath([string]$arguments[5])
    if ([string]::IsNullOrWhiteSpace($PSCommandPath) -or
        $invokedScript -ine [System.IO.Path]::GetFullPath($PSCommandPath)) {
        throw "LOKI service tooling -File target does not match its executing script path."
    }
    return $expectedHome
}

$trustedPowerShellHome = Assert-TrustedWindowsPowerShellHost
$ErrorActionPreference = "Stop"
Microsoft.PowerShell.Core\Set-StrictMode -Version 3.0
$env:PSModulePath = [System.IO.Path]::Combine($trustedPowerShellHome, "Modules")
Microsoft.PowerShell.Core\Import-Module -Name (
    Join-Path $trustedPowerShellHome "Modules\CimCmdlets\CimCmdlets.psd1"
) -Force -ErrorAction Stop
Microsoft.PowerShell.Core\Import-Module -Name (
    Join-Path $trustedPowerShellHome "Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1"
) -Force -ErrorAction Stop
$serviceAccount = "LOKI\Administrator"
$serviceNames = @("LokiTHESunGodBot", "LokiTHESunGodDashboard")
$script:trustedScPath = $null
if ($ReuseExistingVenv -and -not $PreserveExistingIdentity) {
    throw "-ReuseExistingVenv requires -PreserveExistingIdentity."
}

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

function Get-TrustedSystemExecutable {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ExpectedPath,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $actual = [System.IO.Path]::GetFullPath($Path)
    $expected = [System.IO.Path]::GetFullPath($ExpectedPath)
    if ($actual -ine $expected) {
        if ($Label -ceq "TrustedPythonLauncher") {
            throw "TrustedPythonLauncher must be exact system-wide launcher $expected."
        }
        if ($Label -ceq "TrustedPythonRuntime") {
            throw "TrustedPythonRuntime must be exact machine-wide runtime $expected."
        }
        throw "$Label must be exact system executable $expected."
    }
    if (-not (Test-Path -LiteralPath $actual -PathType Leaf)) {
        throw "$Label is missing: $actual"
    }
    $item = Get-Item -LiteralPath $actual -Force
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "$Label must not be a reparse point: $actual"
    }
    return $actual
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

function Get-Sha256Hex {
    [CmdletBinding(DefaultParameterSetName = "Path")]
    param(
        [Parameter(Mandatory = $true, ParameterSetName = "Path")][string]$Path,
        [Parameter(Mandatory = $true, ParameterSetName = "Stream")][System.IO.Stream]$Stream
    )
    $ownedStream = $null
    $sha256 = $null
    try {
        if ($PSCmdlet.ParameterSetName -ceq "Path") {
            $ownedStream = [System.IO.File]::Open(
                $Path,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read,
                [System.IO.FileShare]::Read
            )
            $Stream = $ownedStream
        }
        if (-not $Stream.CanSeek) {
            throw "SHA-256 evidence stream must be seekable."
        }
        $Stream.Position = 0
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        $digest = $sha256.ComputeHash($Stream)
        $Stream.Position = 0
        return [System.BitConverter]::ToString($digest).Replace("-", "").ToLowerInvariant()
    } finally {
        if ($null -ne $sha256) {
            $sha256.Dispose()
        }
        if ($null -ne $ownedStream) {
            $ownedStream.Dispose()
        }
    }
}

function Read-JsonEvidenceStream {
    param([Parameter(Mandatory = $true)][System.IO.Stream]$Stream)
    if (-not $Stream.CanSeek -or $Stream.Length -le 0 -or $Stream.Length -gt 1048576) {
        throw "Archive SHA-256 sidecar must be a nonempty seekable file no larger than 1 MiB."
    }
    $Stream.Position = 0
    $bytes = New-Object byte[] ([int]$Stream.Length)
    $offset = 0
    while ($offset -lt $bytes.Length) {
        $read = $Stream.Read($bytes, $offset, $bytes.Length - $offset)
        if ($read -le 0) {
            throw "Archive SHA-256 sidecar ended unexpectedly."
        }
        $offset += $read
    }
    $Stream.Position = 0
    $json = [System.Text.Encoding]::UTF8.GetString($bytes)
    return $json | ConvertFrom-Json
}

function Copy-LockedEvidenceFile {
    param(
        [Parameter(Mandatory = $true)][System.IO.Stream]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if (-not $Source.CanSeek) {
        throw "Deployment evidence source must be seekable."
    }
    $destinationStream = $null
    try {
        $Source.Position = 0
        $destinationStream = [System.IO.File]::Open(
            $Destination,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        $Source.CopyTo($destinationStream)
        $destinationStream.Flush($true)
        $Source.Position = 0
    } finally {
        if ($null -ne $destinationStream) {
            $destinationStream.Dispose()
        }
    }
}

function Copy-TrustedManifestHelper {
    param(
        [Parameter(Mandatory = $true)][string]$Archive,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = $null
    $sourceStream = $null
    $destinationStream = $null
    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($Archive)
        $entries = @($zip.Entries | Where-Object { [string]$_.FullName -ceq "scripts/release_manifest.py" })
        if ($entries.Count -ne 1 -or [long]$entries[0].Length -le 0) {
            throw "Trusted archive must contain exactly one nonempty manifest helper."
        }
        $sourceStream = $entries[0].Open()
        $destinationStream = [System.IO.File]::Open(
            $Destination,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        $sourceStream.CopyTo($destinationStream)
    } finally {
        if ($null -ne $destinationStream) {
            $destinationStream.Dispose()
        }
        if ($null -ne $sourceStream) {
            $sourceStream.Dispose()
        }
        if ($null -ne $zip) {
            $zip.Dispose()
        }
    }
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

function Get-RegistryValueSnapshot {
    param(
        [Parameter(Mandatory = $true)][Microsoft.Win32.RegistryKey]$Key,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Name
    )
    $exists = $false
    foreach ($candidate in $Key.GetValueNames()) {
        if ([string]$candidate -ceq $Name) {
            $exists = $true
            break
        }
    }
    if (-not $exists) {
        return [ordered]@{ Exists = $false; Kind = $null; Value = $null }
    }
    return [ordered]@{
        Exists = $true
        Kind = $Key.GetValueKind($Name).ToString()
        Value = $Key.GetValue($Name, $null, [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
    }
}

function Get-ServiceSnapshot {
    param([Parameter(Mandatory = $true)][string]$Name)
    $service = CimCmdlets\Get-CimInstance Win32_Service -Filter "Name='$Name'" -ErrorAction SilentlyContinue
    if ($null -eq $service) {
        return [pscustomobject][ordered]@{ Name = $Name; Exists = $false }
    }
    $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
    $registry = Get-Item -LiteralPath $registryPath -ErrorAction Stop
    $registryNames = @(
        "ImagePath", "Start", "ObjectName", "Description", "DependOnService",
        "ErrorControl", "Type", "Environment", "FailureActions",
        "FailureActionsOnNonCrashFailures", "DelayedAutoStart", "LokiInstallId"
    )
    $registryValues = [ordered]@{}
    foreach ($valueName in $registryNames) {
        $registryValues[$valueName] = Get-RegistryValueSnapshot -Key $registry -Name $valueName
    }
    $pythonClassPath = Join-Path $registryPath "PythonClass"
    $pythonClassKey = Get-Item -LiteralPath $pythonClassPath -ErrorAction SilentlyContinue
    $pythonClass = if ($null -eq $pythonClassKey) {
        [ordered]@{ KeyExists = $false; Value = [ordered]@{ Exists = $false; Kind = $null; Value = $null } }
    } else {
        [ordered]@{ KeyExists = $true; Value = (Get-RegistryValueSnapshot -Key $pythonClassKey -Name "") }
    }
    return [pscustomobject][ordered]@{
        Name = $Name
        Exists = $true
        State = [string]$service.State
        StartMode = [string]$service.StartMode
        StartName = [string]$service.StartName
        PathName = [string]$service.PathName
        DisplayName = [string]$service.DisplayName
        Description = [string]$service.Description
        ServiceType = [string]$service.ServiceType
        ErrorControl = [string]$service.ErrorControl
        ServiceDependencies = @($service.ServiceDependencies)
        RegistryValues = $registryValues
        PythonClass = $pythonClass
    }
}

function Protect-RollbackEvidenceAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$Directory
    )
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Protected LOKI path cannot be a reparse point: $Path"
    }
    $securityModule = Join-Path $PSHOME "Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1"
    $loadedSecurityModule = Get-Module Microsoft.PowerShell.Security | Where-Object {
        [string]$_.Path -ieq $securityModule
    }
    if ($null -eq $loadedSecurityModule) {
        Import-Module -Name $securityModule -Force -ErrorAction Stop
    }
    $systemSid = New-Object Security.Principal.SecurityIdentifier("S-1-5-18")
    $administratorsSid = New-Object Security.Principal.SecurityIdentifier("S-1-5-32-544")
    $principals = @($systemSid, $administratorsSid)
    $security = Microsoft.PowerShell.Security\Get-Acl -LiteralPath $Path
    $security.SetAccessRuleProtection($true, $false)
    foreach ($existingRule in @($security.Access)) {
        [void]$security.RemoveAccessRuleSpecific($existingRule)
    }
    $security.SetOwner($administratorsSid)
    foreach ($principal in $principals) {
        $rule = if ($Directory) {
            New-Object Security.AccessControl.FileSystemAccessRule(
                $principal,
                [Security.AccessControl.FileSystemRights]::FullControl,
                ([Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit),
                [Security.AccessControl.PropagationFlags]::None,
                [Security.AccessControl.AccessControlType]::Allow
            )
        } else {
            New-Object Security.AccessControl.FileSystemAccessRule(
                $principal,
                [Security.AccessControl.FileSystemRights]::FullControl,
                [Security.AccessControl.AccessControlType]::Allow
            )
        }
        [void]$security.AddAccessRule($rule)
    }
    Microsoft.PowerShell.Security\Set-Acl -LiteralPath $Path -AclObject $security
    $verifiedItem = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($verifiedItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Protected LOKI path became a reparse point: $Path"
    }
    $verified = Microsoft.PowerShell.Security\Get-Acl -LiteralPath $Path
    $verifiedOwner = $verified.GetOwner([Security.Principal.SecurityIdentifier]).Value
    $verifiedRules = @($verified.GetAccessRules($true, $false, [Security.Principal.SecurityIdentifier]))
    if (-not $verified.AreAccessRulesProtected -or
        $verifiedOwner -cne $administratorsSid.Value -or
        $verifiedRules.Count -ne 2) {
        throw "Protected LOKI path owner or ACL is not exact: $Path"
    }
    $verifiedPrincipals = @{}
    foreach ($verifiedRule in $verifiedRules) {
        $verifiedSid = [string]$verifiedRule.IdentityReference.Value
        $fullControl = [Security.AccessControl.FileSystemRights]::FullControl
        if ($verifiedSid -notin @($systemSid.Value, $administratorsSid.Value) -or
            [string]$verifiedRule.AccessControlType -cne "Allow" -or
            ([int]$verifiedRule.FileSystemRights -band [int]$fullControl) -ne [int]$fullControl) {
            throw "Protected LOKI path contains an unapproved ACL rule: $Path"
        }
        if ($Directory) {
            $requiredInheritance = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
            if (($verifiedRule.InheritanceFlags -band $requiredInheritance) -ne $requiredInheritance -or
                [string]$verifiedRule.PropagationFlags -cne "None") {
                throw "Protected LOKI directory ACL does not secure descendants: $Path"
            }
        } elseif ([string]$verifiedRule.InheritanceFlags -cne "None") {
            throw "Protected LOKI file ACL contains inheritance flags: $Path"
        }
        $verifiedPrincipals[$verifiedSid] = $true
    }
    foreach ($requiredSid in @($systemSid.Value, $administratorsSid.Value)) {
        if (-not $verifiedPrincipals.ContainsKey($requiredSid)) {
            throw "Protected LOKI path ACL omits required principal $requiredSid."
        }
    }
}

function Protect-AdministratorTree {
    param([Parameter(Mandatory = $true)][string]$Root)
    $rootItem = Get-Item -LiteralPath $Root -Force -ErrorAction Stop
    if (-not $rootItem.PSIsContainer) {
        throw "Protected LOKI tree root is not a directory: $Root"
    }
    $pending = New-Object System.Collections.Generic.Stack[string]
    $pending.Push([System.IO.Path]::GetFullPath($Root))
    while ($pending.Count -ne 0) {
        $directory = $pending.Pop()
        Protect-RollbackEvidenceAcl -Path $directory -Directory
        foreach ($child in @(Get-ChildItem -LiteralPath $directory -Force -ErrorAction Stop)) {
            if (($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Protected LOKI tree contains a reparse point: $($child.FullName)"
            }
            if ($child.PSIsContainer) {
                $pending.Push([string]$child.FullName)
            } else {
                Protect-RollbackEvidenceAcl -Path ([string]$child.FullName)
            }
        }
    }
}

function Assert-ProtectedRollbackAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$Directory
    )
    $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Rollback authorization path cannot be a reparse point."
    }
    $securityModule = Join-Path $PSHOME "Modules\Microsoft.PowerShell.Security\Microsoft.PowerShell.Security.psd1"
    $loadedSecurityModule = Get-Module Microsoft.PowerShell.Security | Where-Object {
        [string]$_.Path -ieq $securityModule
    }
    if ($null -eq $loadedSecurityModule) {
        Import-Module -Name $securityModule -Force -ErrorAction Stop
    }
    $acl = Microsoft.PowerShell.Security\Get-Acl -LiteralPath $Path
    $administratorsSid = "S-1-5-32-544"
    if (-not $acl.AreAccessRulesProtected -or
        $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne $administratorsSid) {
        throw "Rollback authorization owner or inheritance is not exact."
    }
    $allowed = @{
        "S-1-5-18" = $true
        $administratorsSid = $true
    }
    $seen = @{}
    $rules = @($acl.GetAccessRules($true, $false, [Security.Principal.SecurityIdentifier]))
    if ($rules.Count -ne 2) {
        throw "Rollback authorization ACL does not contain exactly two rules."
    }
    foreach ($rule in $rules) {
        $sid = [string]$rule.IdentityReference.Value
        $fullControl = [Security.AccessControl.FileSystemRights]::FullControl
        if (-not $allowed.ContainsKey($sid) -or
            [string]$rule.AccessControlType -cne "Allow" -or
            ([int]$rule.FileSystemRights -band [int]$fullControl) -ne [int]$fullControl) {
            throw "Rollback authorization ACL contains an unapproved rule."
        }
        if ($Directory) {
            $requiredInheritance = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [Security.AccessControl.InheritanceFlags]::ObjectInherit
            if (($rule.InheritanceFlags -band $requiredInheritance) -ne $requiredInheritance -or
                [string]$rule.PropagationFlags -cne "None") {
                throw "Rollback authorization directory inheritance is not exact."
            }
        } elseif ([string]$rule.InheritanceFlags -cne "None") {
            throw "Rollback authorization file has unexpected inheritance flags."
        }
        $seen[$sid] = $true
    }
    foreach ($requiredSid in $allowed.Keys) {
        if (-not $seen.ContainsKey($requiredSid)) {
            throw "Rollback authorization ACL omits a required principal."
        }
    }
}

function Assert-StagedInstallerInvocation {
    $bootstrapRoot = [System.IO.Path]::GetFullPath("C:\ProgramData\Loki\bootstrap")
    $scriptPath = [System.IO.Path]::GetFullPath($PSCommandPath)
    $runRoot = [System.IO.Path]::GetDirectoryName($scriptPath)
    $runParent = [System.IO.Path]::GetDirectoryName($runRoot).TrimEnd("\")
    $runLeaf = [System.IO.Path]::GetFileName($runRoot)
    if ($runParent -ine $bootstrapRoot -or
        $runLeaf -cnotmatch "^run-[0-9a-f]{32}$" -or
        [System.IO.Path]::GetFileName($scriptPath) -cne "install_loki_services.ps1") {
        throw "Service installation is allowed only through the protected external bootstrap."
    }
    Assert-ProtectedRollbackAcl -Path $bootstrapRoot -Directory
    Assert-ProtectedRollbackAcl -Path $runRoot -Directory
    Assert-ProtectedRollbackAcl -Path $scriptPath
    return $runRoot
}

function Assert-ExactPropertyNames {
    param(
        [Parameter(Mandatory = $true)][object]$Object,
        [Parameter(Mandatory = $true)][string[]]$Expected,
        [Parameter(Mandatory = $true)][string]$Label
    )
    $actual = @($Object.PSObject.Properties.Name)
    if ($actual.Count -ne $Expected.Count) {
        throw "$Label has missing or extra fields."
    }
    foreach ($name in $Expected) {
        if ($actual -cnotcontains $name) {
            throw "$Label omits an exact required field."
        }
    }
}

function Get-SnapshotInstallId {
    param([Parameter(Mandatory = $true)][object]$Snapshot)
    if (-not [bool]$Snapshot.Exists) {
        throw "Authorized rollback requires both commissioned services to exist."
    }
    $value = $Snapshot.RegistryValues["LokiInstallId"]
    if (-not [bool]$value.Exists -or
        [string]$value.Kind -cne "String" -or
        [string]$value.Value -cnotmatch "^[0-9a-f]{32}$") {
        throw "Existing service rollback install ID is missing or malformed."
    }
    return [string]$value.Value
}

function Open-ReuseVenvAuthorization {
    param([Parameter(Mandatory = $true)][object[]]$Snapshots)
    if ($Snapshots.Count -ne 2) {
        throw "Authorized rollback requires exact snapshots for both services."
    }
    $firstInstallId = Get-SnapshotInstallId -Snapshot $Snapshots[0]
    $secondInstallId = Get-SnapshotInstallId -Snapshot $Snapshots[1]
    if ($firstInstallId -cne $secondInstallId) {
        throw "Existing services do not share one rollback install ID."
    }
    $rollbackRoot = Join-Path $env:ProgramData "Loki\rollback"
    $evidencePath = Join-Path $rollbackRoot "service-config-$firstInstallId.json"
    Assert-ProtectedRollbackAcl -Path $rollbackRoot -Directory
    Assert-ProtectedRollbackAcl -Path $evidencePath
    $stream = $null
    try {
        $stream = [System.IO.File]::Open(
            $evidencePath,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::None
        )
        $evidence = Read-JsonEvidenceStream -Stream $stream
        Assert-ExactPropertyNames -Object $evidence -Expected @(
            "schema", "status", "install_id", "captured_at_utc", "candidate_id",
            "incoming_candidate_id", "incoming_release_root", "incoming_venv_path",
            "service_logon_right_preexisting", "services", "completed_at_utc"
        ) -Label "Rollback authorization"
        if ([string]$evidence.schema -cne "loki-service-rollback/v2" -or
            [string]$evidence.status -cne "installed" -or
            [string]$evidence.install_id -cne $firstInstallId -or
            [string]$evidence.candidate_id -cne [string]$evidence.incoming_candidate_id -or
            [string]$evidence.incoming_candidate_id -cnotmatch "^loki-[A-Za-z0-9._-]+$" -or
            [string]::IsNullOrWhiteSpace([string]$evidence.captured_at_utc) -or
            [string]::IsNullOrWhiteSpace([string]$evidence.completed_at_utc) -or
            $evidence.service_logon_right_preexisting -isnot [bool]) {
            throw "Rollback authorization evidence is not exact installed state."
        }
        $currentRelease = [string]$Snapshots[0].RollbackReleaseRoot
        $currentVenv = [string]$Snapshots[0].RollbackVenvPath
        foreach ($snapshot in $Snapshots) {
            if (-not [string]::Equals([string]$snapshot.RollbackReleaseRoot, $currentRelease, [StringComparison]::OrdinalIgnoreCase) -or
                -not [string]::Equals([string]$snapshot.RollbackVenvPath, $currentVenv, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Existing services do not bind the same active candidate."
            }
        }
        if ([string]$evidence.incoming_candidate_id -cne [System.IO.Path]::GetFileName($currentRelease.TrimEnd("\")) -or
            -not [string]::Equals([string]$evidence.incoming_release_root, $currentRelease, [StringComparison]::OrdinalIgnoreCase) -or
            -not [string]::Equals([string]$evidence.incoming_venv_path, $currentVenv, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Rollback authorization does not bind the currently installed candidate."
        }
        return [pscustomobject]@{
            Stream = $stream
            Evidence = $evidence
            InstallId = $firstInstallId
            CurrentRelease = $currentRelease
            CurrentVenv = $currentVenv
        }
    } catch {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
        throw
    }
}

function Assert-ReuseEvidenceBindsTarget {
    param(
        [Parameter(Mandatory = $true)][object]$Authorization,
        [Parameter(Mandatory = $true)][string]$CandidateId,
        [Parameter(Mandatory = $true)][string]$Release,
        [Parameter(Mandatory = $true)][string]$Venv,
        [Parameter(Mandatory = $true)][string]$Config
    )
    if ([string]$Authorization.Evidence.incoming_candidate_id -ceq $CandidateId) {
        throw "Authorized rollback target must differ from the currently installed candidate."
    }
    $snapshots = @($Authorization.Evidence.services)
    if ($snapshots.Count -ne 2) {
        throw "Rollback authorization must contain exactly two prior service snapshots."
    }
    $seenNames = @{}
    foreach ($snapshot in $snapshots) {
        $name = [string]$snapshot.Name
        if ($name -notin $serviceNames -or $seenNames.ContainsKey($name) -or -not [bool]$snapshot.Exists) {
            throw "Rollback authorization service snapshots are missing, duplicate, or absent."
        }
        $seenNames[$name] = $true
        if ([string]$snapshot.RollbackCandidateId -cne $CandidateId -or
            -not [string]::Equals([string]$snapshot.RollbackReleaseRoot, $Release, [StringComparison]::OrdinalIgnoreCase) -or
            -not [string]::Equals([string]$snapshot.RollbackVenvPath, $Venv, [StringComparison]::OrdinalIgnoreCase) -or
            [string]$snapshot.StartName -cne $serviceAccount) {
            throw "Rollback authorization snapshot does not bind the requested prior candidate."
        }
        $expectedHost = Join-Path $Venv "pythonservice.exe"
        $quotedHost = '"' + $expectedHost + '"'
        if ([string]$snapshot.PathName -ine $quotedHost -or
            -not [bool]$snapshot.RegistryValues.ImagePath.Exists -or
            [string]$snapshot.RegistryValues.ImagePath.Value -ine $quotedHost -or
            -not [bool]$snapshot.RegistryValues.ObjectName.Exists -or
            [string]$snapshot.RegistryValues.ObjectName.Value -cne $serviceAccount) {
            throw "Rollback authorization image path or identity does not bind the requested prior candidate."
        }
        $environment = $snapshot.RegistryValues.Environment
        if (-not [bool]$environment.Exists -or [string]$environment.Kind -cne "MultiString") {
            throw "Rollback authorization environment is missing or malformed."
        }
        Assert-ExactServiceEnvironment -Name $name -Actual @($environment.Value) -Expected (Get-ExpectedServiceEnvironment -Name $name -Release $Release -Config $Config)
        $expectedPythonClass = Get-ExpectedPythonClass -Name $name -Release $Release
        if (-not [bool]$snapshot.PythonClass.KeyExists -or
            -not [bool]$snapshot.PythonClass.Value.Exists -or
            [string]$snapshot.PythonClass.Value.Kind -cne "String") {
            throw "Rollback authorization PythonClass is missing."
        }
        Assert-ExactPythonClass -Name $name -Actual ([string]$snapshot.PythonClass.Value.Value) -Expected $expectedPythonClass
    }
    foreach ($name in $serviceNames) {
        if (-not $seenNames.ContainsKey($name)) {
            throw "Rollback authorization omits a required service snapshot."
        }
    }
    $venvItem = Get-Item -LiteralPath $Venv -Force -ErrorAction Stop
    if (-not $venvItem.PSIsContainer -or
        ($venvItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Authorized rollback venv is missing, not a directory, or a reparse point."
    }
    foreach ($requiredFile in @(
        (Join-Path $Venv "pyvenv.cfg"),
        (Join-Path $Venv "pythonservice.exe"),
        (Join-Path $Venv "Scripts\python.exe")
    )) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "Authorized rollback venv is missing a required runtime artifact."
        }
    }
}

function Assert-ReuseAuthorizationStillCurrent {
    param(
        [Parameter(Mandatory = $true)][object]$Authorization,
        [Parameter(Mandatory = $true)][object[]]$Snapshots
    )
    if ($Snapshots.Count -ne 2 -or -not $Authorization.Stream.CanRead) {
        throw "Rollback authorization lock or service snapshots are no longer valid."
    }
    foreach ($snapshot in $Snapshots) {
        if ((Get-SnapshotInstallId -Snapshot $snapshot) -cne [string]$Authorization.InstallId -or
            -not [string]::Equals([string]$snapshot.RollbackReleaseRoot, [string]$Authorization.CurrentRelease, [StringComparison]::OrdinalIgnoreCase) -or
            -not [string]::Equals([string]$snapshot.RollbackVenvPath, [string]$Authorization.CurrentVenv, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Installed services changed after rollback authorization was captured."
        }
    }
}

function Save-RollbackEvidence {
    param(
        [Parameter(Mandatory = $true)][string]$InstallId,
        [Parameter(Mandatory = $true)][string]$CandidateId,
        [Parameter(Mandatory = $true)][string]$Release,
        [Parameter(Mandatory = $true)][string]$Venv,
        [Parameter(Mandatory = $true)][object[]]$Snapshots,
        [Parameter(Mandatory = $true)][bool]$ServiceLogonRightPreexisting
    )
    $rollbackRoot = Join-Path $env:ProgramData "Loki\rollback"
    if (-not (Test-Path -LiteralPath $rollbackRoot -PathType Container)) {
        New-Item -ItemType Directory -Path $rollbackRoot | Out-Null
    }
    Protect-RollbackEvidenceAcl -Path $rollbackRoot -Directory
    $path = Join-Path $rollbackRoot "service-config-$InstallId.json"
    if (Test-Path -LiteralPath $path) {
        throw "Rollback evidence path already exists; no service was changed."
    }
    $evidence = [ordered]@{
        schema = "loki-service-rollback/v2"
        status = "prepared"
        install_id = $InstallId
        captured_at_utc = [DateTime]::UtcNow.ToString("o")
        candidate_id = $CandidateId
        incoming_candidate_id = $CandidateId
        incoming_release_root = $Release
        incoming_venv_path = $Venv
        service_logon_right_preexisting = $ServiceLogonRightPreexisting
        services = $Snapshots
    }
    $evidence | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $path -Encoding UTF8
    Protect-RollbackEvidenceAcl -Path $path
    return $path
}

function Set-RollbackEvidenceStatus {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][ValidateSet("installed", "rolled_back", "rollback_incomplete")][string]$Status
    )
    $evidence = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $evidence.status = $Status
    $evidence | Add-Member -NotePropertyName completed_at_utc -NotePropertyValue ([DateTime]::UtcNow.ToString("o")) -Force
    $temporaryPath = "$Path.tmp"
    if (Test-Path -LiteralPath $temporaryPath) {
        throw "Rollback evidence temporary path already exists."
    }
    $evidence | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporaryPath -Encoding UTF8
    Protect-RollbackEvidenceAcl -Path $temporaryPath
    Move-Item -LiteralPath $temporaryPath -Destination $Path -Force
    Protect-RollbackEvidenceAcl -Path $Path
}

function Assert-ServiceStopped {
    param([Parameter(Mandatory = $true)][string]$Name)
    $service = CimCmdlets\Get-CimInstance Win32_Service -Filter "Name='$Name'" -ErrorAction SilentlyContinue
    if ($null -ne $service -and [string]$service.State -ne "Stopped") {
        throw "Service $Name must be stopped before update. No service was changed."
    }
}

function Initialize-NativeServiceApi {
    if ($null -ne ("Loki.ServiceNativeApi" -as [type])) {
        return
    }
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;

namespace Loki {
    public static class ServiceNativeApi {
        private const UInt32 SC_MANAGER_CONNECT = 0x0001;
        private const UInt32 SERVICE_CHANGE_CONFIG = 0x0002;
        private const UInt32 SERVICE_NO_CHANGE = 0xFFFFFFFF;
        public const Int32 LOGON32_LOGON_SERVICE = 5;
        private const Int32 LOGON32_PROVIDER_DEFAULT = 0;
        private const UInt32 POLICY_CREATE_ACCOUNT = 0x00000010;
        private const UInt32 POLICY_LOOKUP_NAMES = 0x00000800;
        private const UInt32 STATUS_OBJECT_NAME_NOT_FOUND = 0xC0000034;

        [StructLayout(LayoutKind.Sequential)]
        private struct LSA_OBJECT_ATTRIBUTES {
            public UInt32 Length;
            public IntPtr RootDirectory;
            public IntPtr ObjectName;
            public UInt32 Attributes;
            public IntPtr SecurityDescriptor;
            public IntPtr SecurityQualityOfService;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct LSA_UNICODE_STRING {
            public UInt16 Length;
            public UInt16 MaximumLength;
            public IntPtr Buffer;
        }

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool LogonUserW(
            string userName, string domain, IntPtr password, int logonType,
            int logonProvider, out IntPtr token);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr OpenSCManagerW(
            string machineName, string databaseName, UInt32 desiredAccess);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern IntPtr OpenServiceW(
            IntPtr serviceManager, string serviceName, UInt32 desiredAccess);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool ChangeServiceConfigW(
            IntPtr service, UInt32 serviceType, UInt32 startType, UInt32 errorControl,
            string binaryPathName, string loadOrderGroup, IntPtr tagId,
            string dependencies, string serviceStartName, IntPtr password,
            string displayName);

        [StructLayout(LayoutKind.Sequential)]
        private struct SERVICE_DESCRIPTION {
            public IntPtr Description;
        }

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool ChangeServiceConfig2W(
            IntPtr service, UInt32 infoLevel, ref SERVICE_DESCRIPTION info);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern bool CloseServiceHandle(IntPtr handle);

        [DllImport("kernel32.dll", SetLastError = true)]
        private static extern bool CloseHandle(IntPtr handle);

        [DllImport("advapi32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool LookupAccountNameW(
            string systemName, string accountName, IntPtr sid, ref UInt32 sidSize,
            StringBuilder referencedDomainName, ref UInt32 domainNameSize,
            out UInt32 sidNameUse);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern UInt32 LsaOpenPolicy(
            IntPtr systemName, ref LSA_OBJECT_ATTRIBUTES objectAttributes,
            UInt32 desiredAccess, out IntPtr policyHandle);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern UInt32 LsaAddAccountRights(
            IntPtr policyHandle, IntPtr accountSid,
            [In] LSA_UNICODE_STRING[] userRights, UInt32 countOfRights);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern UInt32 LsaRemoveAccountRights(
            IntPtr policyHandle, IntPtr accountSid, bool allRights,
            [In] LSA_UNICODE_STRING[] userRights, UInt32 countOfRights);

        [DllImport("advapi32.dll", SetLastError = true)]
        private static extern UInt32 LsaEnumerateAccountRights(
            IntPtr policyHandle, IntPtr accountSid, out IntPtr userRights,
            out UInt32 countOfRights);

        [DllImport("advapi32.dll")]
        private static extern UInt32 LsaNtStatusToWinError(UInt32 status);

        [DllImport("advapi32.dll")]
        private static extern UInt32 LsaFreeMemory(IntPtr buffer);

        [DllImport("advapi32.dll")]
        private static extern UInt32 LsaClose(IntPtr policyHandle);

        private static void ThrowLsa(UInt32 status, string operation) {
            if (status != 0) {
                throw new Win32Exception((int)LsaNtStatusToWinError(status), operation);
            }
        }

        private static IntPtr ResolveSid(string accountName) {
            UInt32 sidSize = 0;
            UInt32 domainSize = 0;
            UInt32 sidUse;
            LookupAccountNameW(null, accountName, IntPtr.Zero, ref sidSize,
                null, ref domainSize, out sidUse);
            if (sidSize == 0) {
                throw new Win32Exception(Marshal.GetLastWin32Error(),
                    "Account SID lookup sizing failed");
            }
            IntPtr sid = Marshal.AllocHGlobal((int)sidSize);
            try {
                StringBuilder domain = new StringBuilder((int)domainSize);
                if (!LookupAccountNameW(null, accountName, sid, ref sidSize,
                        domain, ref domainSize, out sidUse)) {
                    throw new Win32Exception(Marshal.GetLastWin32Error(),
                        "Account SID lookup failed");
                }
                return sid;
            } catch {
                Marshal.FreeHGlobal(sid);
                throw;
            }
        }

        private static IntPtr OpenPolicy() {
            LSA_OBJECT_ATTRIBUTES attributes = new LSA_OBJECT_ATTRIBUTES();
            attributes.Length = (UInt32)Marshal.SizeOf(typeof(LSA_OBJECT_ATTRIBUTES));
            IntPtr policy;
            UInt32 status = LsaOpenPolicy(IntPtr.Zero, ref attributes,
                POLICY_CREATE_ACCOUNT | POLICY_LOOKUP_NAMES, out policy);
            ThrowLsa(status, "LSA policy open failed");
            return policy;
        }

        private static LSA_UNICODE_STRING MakeRight(string right, out IntPtr buffer) {
            buffer = Marshal.StringToHGlobalUni(right);
            LSA_UNICODE_STRING value = new LSA_UNICODE_STRING();
            value.Buffer = buffer;
            value.Length = (UInt16)(right.Length * 2);
            value.MaximumLength = (UInt16)((right.Length + 1) * 2);
            return value;
        }

        public static bool HasAccountRight(string accountName, string right) {
            IntPtr sid = ResolveSid(accountName);
            IntPtr policy = IntPtr.Zero;
            IntPtr rights = IntPtr.Zero;
            try {
                policy = OpenPolicy();
                UInt32 count;
                UInt32 status = LsaEnumerateAccountRights(policy, sid, out rights, out count);
                if (status == STATUS_OBJECT_NAME_NOT_FOUND) {
                    return false;
                }
                ThrowLsa(status, "LSA account-right enumeration failed");
                int size = Marshal.SizeOf(typeof(LSA_UNICODE_STRING));
                for (UInt32 index = 0; index < count; index++) {
                    IntPtr item = new IntPtr(rights.ToInt64() + (long)index * size);
                    LSA_UNICODE_STRING value = (LSA_UNICODE_STRING)Marshal.PtrToStructure(
                        item, typeof(LSA_UNICODE_STRING));
                    string name = Marshal.PtrToStringUni(value.Buffer, value.Length / 2);
                    if (String.Equals(name, right, StringComparison.OrdinalIgnoreCase)) {
                        return true;
                    }
                }
                return false;
            } finally {
                if (rights != IntPtr.Zero) LsaFreeMemory(rights);
                if (policy != IntPtr.Zero) LsaClose(policy);
                Marshal.FreeHGlobal(sid);
            }
        }

        public static void AddAccountRight(string accountName, string right) {
            IntPtr sid = ResolveSid(accountName);
            IntPtr policy = IntPtr.Zero;
            IntPtr buffer = IntPtr.Zero;
            try {
                policy = OpenPolicy();
                LSA_UNICODE_STRING[] rights = new LSA_UNICODE_STRING[] {
                    MakeRight(right, out buffer)
                };
                ThrowLsa(LsaAddAccountRights(policy, sid, rights, 1),
                    "LSA account-right grant failed");
            } finally {
                if (buffer != IntPtr.Zero) Marshal.FreeHGlobal(buffer);
                if (policy != IntPtr.Zero) LsaClose(policy);
                Marshal.FreeHGlobal(sid);
            }
        }

        public static void RemoveAccountRight(string accountName, string right) {
            IntPtr sid = ResolveSid(accountName);
            IntPtr policy = IntPtr.Zero;
            IntPtr buffer = IntPtr.Zero;
            try {
                policy = OpenPolicy();
                LSA_UNICODE_STRING[] rights = new LSA_UNICODE_STRING[] {
                    MakeRight(right, out buffer)
                };
                UInt32 status = LsaRemoveAccountRights(policy, sid, false, rights, 1);
                if (status != STATUS_OBJECT_NAME_NOT_FOUND) {
                    ThrowLsa(status, "LSA account-right removal failed");
                }
            } finally {
                if (buffer != IntPtr.Zero) Marshal.FreeHGlobal(buffer);
                if (policy != IntPtr.Zero) LsaClose(policy);
                Marshal.FreeHGlobal(sid);
            }
        }

        public static void ValidateServiceLogon(
            string userName, string domain, IntPtr password) {
            IntPtr token;
            if (!LogonUserW(userName, domain, password, LOGON32_LOGON_SERVICE,
                    LOGON32_PROVIDER_DEFAULT, out token)) {
                throw new Win32Exception(Marshal.GetLastWin32Error(),
                    "Service credential validation failed");
            }
            CloseHandle(token);
        }

        public static void ChangeIdentity(
            string serviceName, string accountName, IntPtr password) {
            IntPtr manager = OpenSCManagerW(null, null, SC_MANAGER_CONNECT);
            if (manager == IntPtr.Zero) {
                throw new Win32Exception(Marshal.GetLastWin32Error(),
                    "OpenSCManager failed");
            }
            try {
                IntPtr service = OpenServiceW(manager, serviceName, SERVICE_CHANGE_CONFIG);
                if (service == IntPtr.Zero) {
                    throw new Win32Exception(Marshal.GetLastWin32Error(),
                        "OpenService failed");
                }
                try {
                    if (!ChangeServiceConfigW(service, SERVICE_NO_CHANGE,
                            SERVICE_NO_CHANGE, SERVICE_NO_CHANGE, null, null,
                            IntPtr.Zero, null, accountName, password, null)) {
                        throw new Win32Exception(Marshal.GetLastWin32Error(),
                            "Service identity update failed");
                    }
                } finally {
                    CloseServiceHandle(service);
                }
            } finally {
                CloseServiceHandle(manager);
            }
        }

        public static void RestoreCoreConfiguration(
            string serviceName, UInt32 serviceType, UInt32 startType,
            UInt32 errorControl, string binaryPathName, string dependencies,
            string displayName, string description) {
            IntPtr manager = OpenSCManagerW(null, null, SC_MANAGER_CONNECT);
            if (manager == IntPtr.Zero) {
                throw new Win32Exception(Marshal.GetLastWin32Error(),
                    "OpenSCManager failed");
            }
            try {
                IntPtr service = OpenServiceW(manager, serviceName, SERVICE_CHANGE_CONFIG);
                if (service == IntPtr.Zero) {
                    throw new Win32Exception(Marshal.GetLastWin32Error(),
                        "OpenService failed");
                }
                try {
                    if (!ChangeServiceConfigW(service, serviceType, startType,
                            errorControl, binaryPathName, null, IntPtr.Zero,
                            dependencies, null, IntPtr.Zero, displayName)) {
                        throw new Win32Exception(Marshal.GetLastWin32Error(),
                            "Service core configuration restore failed");
                    }
                    IntPtr descriptionBuffer = description == null
                        ? IntPtr.Zero : Marshal.StringToHGlobalUni(description);
                    try {
                        SERVICE_DESCRIPTION serviceDescription = new SERVICE_DESCRIPTION();
                        serviceDescription.Description = descriptionBuffer;
                        if (!ChangeServiceConfig2W(service, 1, ref serviceDescription)) {
                            throw new Win32Exception(Marshal.GetLastWin32Error(),
                                "Service description restore failed");
                        }
                    } finally {
                        if (descriptionBuffer != IntPtr.Zero) {
                            Marshal.FreeHGlobal(descriptionBuffer);
                        }
                    }
                } finally {
                    CloseServiceHandle(service);
                }
            } finally {
                CloseServiceHandle(manager);
            }
        }
    }
}
'@
}

function Test-ServiceLogonRight {
    Initialize-NativeServiceApi
    return [Loki.ServiceNativeApi]::HasAccountRight($serviceAccount, "SeServiceLogonRight")
}

function Grant-ServiceLogonRight {
    Initialize-NativeServiceApi
    $added = $false
    try {
        [Loki.ServiceNativeApi]::AddAccountRight($serviceAccount, "SeServiceLogonRight")
        $added = $true
        if (-not (Test-ServiceLogonRight)) {
            throw "SeServiceLogonRight grant verification failed for exact service account."
        }
    } catch {
        $grantFailure = $_
        if ($added) {
            [Loki.ServiceNativeApi]::RemoveAccountRight($serviceAccount, "SeServiceLogonRight")
        }
        throw $grantFailure
    }
}

function Revoke-ServiceLogonRight {
    Initialize-NativeServiceApi
    [Loki.ServiceNativeApi]::RemoveAccountRight($serviceAccount, "SeServiceLogonRight")
    if (Test-ServiceLogonRight) {
        throw "SeServiceLogonRight rollback removal failed for exact service account."
    }
}

function Test-ServiceCredential {
    param([Parameter(Mandatory = $true)][System.Management.Automation.PSCredential]$Credential)
    Initialize-NativeServiceApi
    $accountParts = $Credential.UserName.Split(@("\"), 2, [System.StringSplitOptions]::None)
    if ($accountParts.Count -ne 2) {
        throw "Service credential username must include the exact domain."
    }
    $passwordPointer = [IntPtr]::Zero
    try {
        $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Credential.Password)
        [Loki.ServiceNativeApi]::ValidateServiceLogon(
            [string]$accountParts[1], [string]$accountParts[0], $passwordPointer
        )
    } finally {
        if ($passwordPointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
        }
    }
}

function Get-ValidatedServiceCredential {
    $credential = Get-Credential -UserName $serviceAccount -Message "Enter the service logon credential for exact account $serviceAccount"
    if ($null -eq $credential -or [string]$credential.UserName -cne $serviceAccount) {
        throw "Service credential username must be exactly $serviceAccount."
    }
    Test-ServiceCredential -Credential $credential
    return $credential
}

function Set-ServiceIdentitySecurely {
    param(
        [Parameter(Mandatory = $true)][System.Management.Automation.PSCredential]$Credential,
        [Parameter(Mandatory = $true)][string[]]$Names
    )
    $passwordPointer = [IntPtr]::Zero
    try {
        $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Credential.Password)
        foreach ($name in $Names) {
            [Loki.ServiceNativeApi]::ChangeIdentity($name, $serviceAccount, $passwordPointer)
        }
    } finally {
        if ($passwordPointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
        }
    }
}

function Get-ExpectedPythonClass {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Release
    )
    if ($Name -ceq "LokiTHESunGodBot") {
        return (Join-Path $Release "scripts\loki_bot_service") + ".LokiBotService"
    }
    if ($Name -ceq "LokiTHESunGodDashboard") {
        return (Join-Path $Release "scripts\loki_dashboard_service") + ".LokiDashboardService"
    }
    throw "Unknown LOKI service name."
}

function Assert-ExactPythonClass {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Actual,
        [Parameter(Mandatory = $true)][string]$Expected
    )
    $actualSeparator = $Actual.LastIndexOf(".")
    $expectedSeparator = $Expected.LastIndexOf(".")
    if ($actualSeparator -le 0 -or $expectedSeparator -le 0) {
        throw "Service $Name PythonClass is malformed."
    }
    $actualModule = $Actual.Substring(0, $actualSeparator)
    $expectedModule = $Expected.Substring(0, $expectedSeparator)
    $actualClass = $Actual.Substring($actualSeparator + 1)
    $expectedClass = $Expected.Substring($expectedSeparator + 1)
    if (-not [string]::Equals($actualModule, $expectedModule, [StringComparison]::OrdinalIgnoreCase) -or
        $actualClass -cne $expectedClass) {
        throw "Service $Name PythonClass does not exactly bind its release wrapper and class."
    }
}

function Get-ExpectedServiceEnvironment {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Release,
        [Parameter(Mandatory = $true)][string]$Config
    )
    return @(
        "LOKI_APP_ROOT=$Release",
        "LOKI_ENV_PATH=$Config",
        "LOKI_DB_PATH=$(Join-Path $env:ProgramData 'Loki\data\bot.db')",
        "PYTHONPYCACHEPREFIX=$(Join-Path $env:ProgramData "Loki\cache\$Name")",
        "LOKI_LOCAL_ALLOW_FULL=true",
        "RELAY_ENABLED=false",
        "LOKI_ENABLE_SLASH_SYNC=false"
    )
}

function Assert-ExactServiceEnvironment {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string[]]$Actual,
        [Parameter(Mandatory = $true)][string[]]$Expected
    )
    if ($Actual.Count -ne $Expected.Count) {
        throw "Service $Name environment contains missing, duplicate, or extra entries."
    }
    $actualValues = @{}
    foreach ($entry in $Actual) {
        $parts = ([string]$entry).Split(@("="), 2, [System.StringSplitOptions]::None)
        if ($parts.Count -ne 2 -or [string]::IsNullOrWhiteSpace($parts[0]) -or $actualValues.ContainsKey($parts[0])) {
            throw "Service $Name environment is malformed or contains a duplicate name."
        }
        $actualValues[$parts[0]] = $parts[1]
    }
    foreach ($entry in $Expected) {
        $parts = ([string]$entry).Split(@("="), 2, [System.StringSplitOptions]::None)
        if (-not $actualValues.ContainsKey($parts[0]) -or
            -not [string]::Equals([string]$actualValues[$parts[0]], [string]$parts[1], [StringComparison]::OrdinalIgnoreCase)) {
            throw "Service $Name environment does not exactly match commissioned external paths."
        }
    }
}

function Assert-InstalledServiceExact {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Release,
        [Parameter(Mandatory = $true)][string]$Config,
        [Parameter(Mandatory = $true)][string]$ServiceHost,
        [Parameter(Mandatory = $true)][string]$InstallId,
        [Parameter(Mandatory = $true)][ValidateSet("Disabled", "Auto")][string]$ExpectedStartMode,
        [Parameter(Mandatory = $true)][ValidateSet(0, 1)][int]$ExpectedDelayed
    )
    $service = CimCmdlets\Get-CimInstance Win32_Service -Filter "Name='$Name'" -ErrorAction Stop
    $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
    $registry = Get-Item -LiteralPath $registryPath -ErrorAction Stop
    $delayed = [int]$registry.GetValue("DelayedAutoStart", 0)
    $pythonClassKey = Get-Item -LiteralPath (Join-Path $registryPath "PythonClass") -ErrorAction Stop
    $pythonClass = [string]$pythonClassKey.GetValue("")
    $expectedPythonClass = Get-ExpectedPythonClass -Name $Name -Release $Release
    $actualEnvironment = @($registry.GetValue("Environment", @()))
    $expectedEnvironment = Get-ExpectedServiceEnvironment -Name $Name -Release $Release -Config $Config
    $actualInstallId = [string]$registry.GetValue("LokiInstallId", "")
    if ([string]$service.State -cne "Stopped") {
        throw "Service $Name started unexpectedly."
    }
    if ([string]$service.StartMode -cne $ExpectedStartMode -or $delayed -ne $ExpectedDelayed) {
        throw "Service $Name startup mode does not match the transaction phase."
    }
    if ([string]$service.StartName -cne $serviceAccount) {
        throw "Service $Name does not use exact account $serviceAccount."
    }
    if ([string]$service.PathName -ine ('"' + $ServiceHost + '"')) {
        throw "Service $Name image path does not bind exact release-specific pythonservice.exe."
    }
    Assert-ExactPythonClass -Name $Name -Actual $pythonClass -Expected $expectedPythonClass
    if ($actualInstallId -cne $InstallId) {
        throw "Service $Name does not bind current rollback install evidence."
    }
    Assert-ExactServiceEnvironment -Name $Name -Actual $actualEnvironment -Expected $expectedEnvironment
}

function Set-RecoveryPolicy {
    param([Parameter(Mandatory = $true)][string]$Name)
    Invoke-Native -FilePath $script:trustedScPath -Arguments @(
        "failure", $Name,
        "reset=", "86400",
        "actions=", 'restart/60000/restart/120000/""/0'
    ) -Label "SCM recovery policy for $Name"
    Invoke-Native -FilePath $script:trustedScPath -Arguments @("failureflag", $Name, "1") -Label "SCM non-crash failure flag for $Name"
    $recovery = Invoke-NativeText -FilePath $script:trustedScPath -Arguments @("qfailure", $Name) -Label "SCM recovery query for $Name"
    Assert-RecoveryTextExact -Name $Name -Text $recovery
    $failureFlag = Invoke-NativeText -FilePath $script:trustedScPath -Arguments @("qfailureflag", $Name) -Label "SCM failure flag query for $Name"
    if ($failureFlag -notmatch "(?im)^\s*FAILURE_ACTIONS_ON_NONCRASH_FAILURES\s*:\s*TRUE\s*$") {
        throw "SCM failureflag query for $Name did not confirm non-crash recovery."
    }
}

function Assert-RecoveryTextExact {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Text
    )
    if ($Text -notmatch "(?im)^\s*RESET_PERIOD[^:]*:\s*86400\s*$") {
        throw "SCM recovery for $Name does not use exact 86400-second reset period."
    }
    foreach ($emptyField in @("REBOOT_MESSAGE", "COMMAND_LINE")) {
        if ($Text -notmatch "(?im)^\s*$emptyField\s*:\s*$") {
            throw "SCM recovery for $Name has a nonempty or missing $emptyField field."
        }
    }
    $pattern = "(?im)^\s*(?:FAILURE_ACTIONS\s*:\s*)?(RESTART|REBOOT|RUN COMMAND|NONE)\s*--\s*Delay\s*=\s*(\d+)\s+milliseconds\.\s*$"
    $matches = @([regex]::Matches($Text, $pattern))
    $expectedActions = @("RESTART", "RESTART", "NONE")
    $expectedDelays = @(60000, 120000, 0)
    if ($matches.Count -ne $expectedActions.Count) {
        throw "SCM recovery for $Name does not contain exactly three commissioned actions."
    }
    for ($index = 0; $index -lt $expectedActions.Count; $index += 1) {
        if ([string]$matches[$index].Groups[1].Value -cne $expectedActions[$index] -or
            [int]$matches[$index].Groups[2].Value -ne $expectedDelays[$index]) {
            throw "SCM recovery for $Name has an unexpected action or delay."
        }
    }
}

function Assert-RecoveryPolicyExact {
    param([Parameter(Mandatory = $true)][string]$Name)
    $recovery = Invoke-NativeText -FilePath $script:trustedScPath -Arguments @("qfailure", $Name) -Label "SCM recovery preflight for $Name"
    Assert-RecoveryTextExact -Name $Name -Text $recovery
    $failureFlag = Invoke-NativeText -FilePath $script:trustedScPath -Arguments @("qfailureflag", $Name) -Label "SCM failureflag preflight for $Name"
    if ($failureFlag -notmatch "(?im)^\s*FAILURE_ACTIONS_ON_NONCRASH_FAILURES\s*:\s*TRUE\s*$") {
        throw "Existing service $Name failureflag is not safely restorable; no service was changed."
    }
}

function Assert-SnapshotContainsOnlyApprovedNonsecretState {
    param([Parameter(Mandatory = $true)][object]$Snapshot)
    $name = [string]$Snapshot.Name
    $environmentSnapshot = $Snapshot.RegistryValues["Environment"]
    if (-not [bool]$environmentSnapshot.Exists -or [string]$environmentSnapshot.Kind -cne "MultiString") {
        throw "Existing service $name has no exact approved nonsecret Environment snapshot; no service was changed."
    }
    $actualEnvironment = @($environmentSnapshot.Value)
    $environmentValues = @{}
    foreach ($entry in $actualEnvironment) {
        $parts = ([string]$entry).Split(@("="), 2, [System.StringSplitOptions]::None)
        if ($parts.Count -ne 2 -or $environmentValues.ContainsKey($parts[0])) {
            throw "Existing service $name has malformed or duplicate environment names; no service was changed."
        }
        $environmentValues[$parts[0]] = $parts[1]
    }
    if (-not $environmentValues.ContainsKey("LOKI_APP_ROOT")) {
        throw "Existing service $name omits approved LOKI_APP_ROOT; no service was changed."
    }
    $previousRelease = [System.IO.Path]::GetFullPath([string]$environmentValues["LOKI_APP_ROOT"])
    $releaseBase = [System.IO.Path]::GetFullPath((Join-Path $env:ProgramData "Loki\releases")).TrimEnd("\")
    $releaseParent = [System.IO.Path]::GetDirectoryName($previousRelease).TrimEnd("\")
    $releaseLeaf = [System.IO.Path]::GetFileName($previousRelease.TrimEnd("\"))
    if ($releaseParent -ine $releaseBase -or $releaseLeaf -cnotmatch "^loki-[A-Za-z0-9._-]+$") {
        throw "Existing service $name LOKI_APP_ROOT is outside a versioned LOKI release; no service was changed."
    }
    $approvedConfig = [System.IO.Path]::GetFullPath("C:\ProgramData\Loki\config\lokithesungod.env")
    $expectedEnvironment = Get-ExpectedServiceEnvironment -Name $name -Release $previousRelease -Config $approvedConfig
    Assert-ExactServiceEnvironment -Name $name -Actual $actualEnvironment -Expected $expectedEnvironment

    $pathName = [string]$Snapshot.PathName
    if ($pathName -cnotmatch '^"[^"\r\n]+\\pythonservice\.exe"$') {
        throw "Existing service $name image path is not an argument-free pythonservice.exe path; no service was changed."
    }
    $serviceHost = [System.IO.Path]::GetFullPath($pathName.Substring(1, $pathName.Length - 2))
    $venvDirectory = [System.IO.Path]::GetDirectoryName($serviceHost).TrimEnd("\")
    $venvBase = [System.IO.Path]::GetFullPath((Join-Path $env:ProgramData "Loki\venvs")).TrimEnd("\")
    if ([System.IO.Path]::GetDirectoryName($venvDirectory).TrimEnd("\") -ine $venvBase -or
        [System.IO.Path]::GetFileName($venvDirectory) -cnotmatch "^loki-[A-Za-z0-9._-]+$") {
        throw "Existing service $name image path is outside a release-specific LOKI venv; no service was changed."
    }
    $imagePathSnapshot = $Snapshot.RegistryValues["ImagePath"]
    if (-not [bool]$imagePathSnapshot.Exists -or [string]$imagePathSnapshot.Value -cne $pathName) {
        throw "Existing service $name image path snapshot is inconsistent; no service was changed."
    }
    $objectNameSnapshot = $Snapshot.RegistryValues["ObjectName"]
    if (-not [bool]$objectNameSnapshot.Exists -or [string]$objectNameSnapshot.Value -cne $serviceAccount) {
        throw "Existing service $name account snapshot is inconsistent; no service was changed."
    }
    foreach ($requiredValue in @("Start", "Type", "ErrorControl", "FailureActions", "FailureActionsOnNonCrashFailures")) {
        if (-not [bool]$Snapshot.RegistryValues[$requiredValue].Exists) {
            throw "Existing service $name omits exact registry state $requiredValue; no service was changed."
        }
    }
    $requiredDwordValues = @{
        "Start" = 2
        "Type" = 16
        "ErrorControl" = 1
        "FailureActionsOnNonCrashFailures" = 1
        "DelayedAutoStart" = 1
    }
    foreach ($valueName in $requiredDwordValues.Keys) {
        $valueSnapshot = $Snapshot.RegistryValues[$valueName]
        if (-not [bool]$valueSnapshot.Exists -or
            [string]$valueSnapshot.Kind -cne "DWord" -or
            [int]$valueSnapshot.Value -ne [int]$requiredDwordValues[$valueName]) {
            throw "Existing service $name registry value $valueName is not exact commissioned state; no service was changed."
        }
    }
    $failureActionsSnapshot = $Snapshot.RegistryValues["FailureActions"]
    if ([string]$failureActionsSnapshot.Kind -cne "Binary" -or
        @($failureActionsSnapshot.Value).Count -eq 0) {
        throw "Existing service $name recovery blob is not exact commissioned state; no service was changed."
    }
    if (@($Snapshot.ServiceDependencies).Count -ne 0) {
        throw "Existing service $name has unapproved dependencies; no service was changed."
    }
    $expectedDisplayName = if ($name -ceq "LokiTHESunGodBot") { "Loki THE SUN GOD Bot" } else { "Loki THE SUN GOD Dashboard" }
    $expectedDescription = if ($name -ceq "LokiTHESunGodBot") { "LOKI Discord gateway and local health runtime" } else { "LOKI local operator dashboard" }
    if ([string]$Snapshot.DisplayName -cne $expectedDisplayName -or [string]$Snapshot.Description -cne $expectedDescription) {
        throw "Existing service $name display metadata is not approved nonsecret state; no service was changed."
    }
    $descriptionSnapshot = $Snapshot.RegistryValues["Description"]
    if (-not [bool]$descriptionSnapshot.Exists -or
        [string]$descriptionSnapshot.Kind -cne "String" -or
        [string]$descriptionSnapshot.Value -cne $expectedDescription) {
        throw "Existing service $name registry description is not exact approved nonsecret state; no service was changed."
    }
    $dependencySnapshot = $Snapshot.RegistryValues["DependOnService"]
    if ([bool]$dependencySnapshot.Exists -and
        ([string]$dependencySnapshot.Kind -cne "MultiString" -or @($dependencySnapshot.Value).Count -ne 0)) {
        throw "Existing service $name registry dependencies are not exact approved nonsecret state; no service was changed."
    }
    $previousInstallId = $Snapshot.RegistryValues["LokiInstallId"]
    if ([bool]$previousInstallId.Exists -and
        ([string]$previousInstallId.Kind -cne "String" -or [string]$previousInstallId.Value -cnotmatch "^[0-9a-f]{32}$")) {
        throw "Existing service $name install id is not exact approved nonsecret state; no service was changed."
    }
    $expectedPythonClass = Get-ExpectedPythonClass -Name $name -Release $previousRelease
    if (-not [bool]$Snapshot.PythonClass.KeyExists -or
        -not [bool]$Snapshot.PythonClass.Value.Exists -or
        [string]$Snapshot.PythonClass.Value.Kind -cne "String") {
        throw "Existing service $name PythonClass is not exact approved state; no service was changed."
    }
    Assert-ExactPythonClass -Name $name -Actual ([string]$Snapshot.PythonClass.Value.Value) -Expected $expectedPythonClass
    Assert-RollbackArtifacts -Name $name -Release $previousRelease -Venv $venvDirectory -ServiceHost $serviceHost
    $Snapshot | Add-Member -NotePropertyName RollbackReleaseRoot -NotePropertyValue $previousRelease -Force
    $Snapshot | Add-Member -NotePropertyName RollbackVenvPath -NotePropertyValue $venvDirectory -Force
    $Snapshot | Add-Member -NotePropertyName RollbackCandidateId -NotePropertyValue $releaseLeaf -Force
}

function Assert-RollbackArtifacts {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Release,
        [Parameter(Mandatory = $true)][string]$Venv,
        [Parameter(Mandatory = $true)][string]$ServiceHost
    )
    $releaseLeaf = [System.IO.Path]::GetFileName($Release.TrimEnd("\"))
    $venvLeaf = [System.IO.Path]::GetFileName($Venv.TrimEnd("\"))
    if ($releaseLeaf -cne $venvLeaf) {
        throw "Existing service $Name release and venv candidates do not match; no service was changed."
    }
    $wrapper = if ($Name -ceq "LokiTHESunGodBot") {
        Join-Path $Release "scripts\loki_bot_service.py"
    } else {
        Join-Path $Release "scripts\loki_dashboard_service.py"
    }
    $entryPoint = if ($Name -ceq "LokiTHESunGodBot") {
        Join-Path $Release "local_loki_runtime.py"
    } else {
        Join-Path $Release "dashboard_app.py"
    }
    $manifestPath = Join-Path $Release "release-manifest.json"
    $requiredFiles = @(
        $manifestPath,
        $wrapper,
        $entryPoint,
        (Join-Path $Release "scripts\windows_service_common.py"),
        $ServiceHost,
        (Join-Path $Venv "pythonservice.exe"),
        (Join-Path $Venv "Scripts\python.exe")
    )
    foreach ($requiredFile in $requiredFiles) {
        if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
            throw "Existing service $Name has an unusable rollback artifact; no service was changed: $requiredFile"
        }
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ([string]$manifest.schema -cne "loki-release-manifest/v1" -or
        [string]$manifest.candidate_id -cne $releaseLeaf) {
        throw "Existing service $Name rollback manifest does not bind its release directory; no service was changed."
    }
}

function Assert-RollbackReleaseManifest {
    param(
        [Parameter(Mandatory = $true)][object]$Snapshot,
        [Parameter(Mandatory = $true)][string]$PythonRuntime,
        [Parameter(Mandatory = $true)][string]$ManifestHelper
    )
    if (-not [bool]$Snapshot.Exists) {
        return
    }
    $rollbackRelease = [string]$Snapshot.RollbackReleaseRoot
    $rollbackVenv = [string]$Snapshot.RollbackVenvPath
    foreach ($requiredVenvArtifact in @(
        (Join-Path $rollbackVenv "pythonservice.exe"),
        (Join-Path $rollbackVenv "Scripts\python.exe")
    )) {
        if (-not (Test-Path -LiteralPath $requiredVenvArtifact -PathType Leaf)) {
            throw "Existing service $($Snapshot.Name) rollback venv artifact disappeared before mutation."
        }
    }
    $verificationJson = Invoke-NativeText -FilePath $PythonRuntime -Arguments @(
        "-I", "-B", $ManifestHelper, "verify-directory", "--root", $rollbackRelease
    ) -Label "Rollback release verification for $($Snapshot.Name)"
    $verification = $verificationJson | ConvertFrom-Json
    if ([string]$verification.candidate_id -cne [string]$Snapshot.RollbackCandidateId) {
        throw "Existing service $($Snapshot.Name) rollback manifest verification returned the wrong candidate."
    }
}

function Assert-ServiceSnapshotSafeForMutation {
    param(
        [Parameter(Mandatory = $true)][object]$Snapshot,
        [Parameter(Mandatory = $true)][bool]$IdentityMustExist
    )
    if (-not [bool]$Snapshot.Exists) {
        if ($IdentityMustExist) {
            throw "-PreserveExistingIdentity requires existing $($Snapshot.Name) under exact account $serviceAccount."
        }
        return
    }
    if ([string]$Snapshot.State -cne "Stopped") {
        throw "Service $($Snapshot.Name) must be stopped before update. No service was changed."
    }
    if ([string]$Snapshot.StartName -cne $serviceAccount) {
        throw "Existing service $($Snapshot.Name) must already use exact account $serviceAccount; safe password-free rollback is otherwise impossible. No service was changed."
    }
    Assert-SnapshotContainsOnlyApprovedNonsecretState -Snapshot $Snapshot
    Assert-RecoveryPolicyExact -Name ([string]$Snapshot.Name)
}

function Set-RegistryValueFromSnapshot {
    param(
        [Parameter(Mandatory = $true)][Microsoft.Win32.RegistryKey]$Key,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Name,
        [Parameter(Mandatory = $true)][object]$Snapshot
    )
    if (-not [bool]$Snapshot.Exists) {
        $Key.DeleteValue($Name, $false)
        return
    }
    $kind = [Microsoft.Win32.RegistryValueKind][Enum]::Parse(
        [Microsoft.Win32.RegistryValueKind], [string]$Snapshot.Kind
    )
    $Key.SetValue($Name, $Snapshot.Value, $kind)
}

function Assert-ServiceSnapshotRestored {
    param([Parameter(Mandatory = $true)][object]$Snapshot)
    $actual = Get-ServiceSnapshot -Name ([string]$Snapshot.Name)
    foreach ($field in @("Exists", "State", "StartMode", "StartName", "PathName", "DisplayName", "Description", "ServiceType", "ErrorControl")) {
        if ([string]$actual.$field -cne [string]$Snapshot.$field) {
            throw "Rollback did not restore exact $field for $($Snapshot.Name)."
        }
    }
    $expectedDependencies = @($Snapshot.ServiceDependencies) | ConvertTo-Json -Compress
    $actualDependencies = @($actual.ServiceDependencies) | ConvertTo-Json -Compress
    if ($actualDependencies -cne $expectedDependencies) {
        throw "Rollback did not restore exact ServiceDependencies for $($Snapshot.Name)."
    }
    foreach ($name in $Snapshot.RegistryValues.Keys) {
        $expectedJson = $Snapshot.RegistryValues[$name] | ConvertTo-Json -Compress -Depth 6
        $actualJson = $actual.RegistryValues[$name] | ConvertTo-Json -Compress -Depth 6
        if ($actualJson -cne $expectedJson) {
            throw "Rollback did not restore exact registry value $name for $($Snapshot.Name)."
        }
    }
    $expectedPythonClass = $Snapshot.PythonClass | ConvertTo-Json -Compress -Depth 6
    $actualPythonClass = $actual.PythonClass | ConvertTo-Json -Compress -Depth 6
    if ($actualPythonClass -cne $expectedPythonClass) {
        throw "Rollback did not restore exact PythonClass for $($Snapshot.Name)."
    }
}

function Restore-ServiceSnapshot {
    param(
        [Parameter(Mandatory = $true)][object]$Snapshot,
        [AllowNull()][System.Management.Automation.PSCredential]$Credential
    )
    $name = [string]$Snapshot.Name
    $service = CimCmdlets\Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction Stop
    if ([string]$service.State -cne "Stopped") {
        throw "Rollback requires stopped service $name."
    }
    foreach ($requiredValue in @("Type", "Start", "ErrorControl")) {
        if (-not [bool]$Snapshot.RegistryValues[$requiredValue].Exists) {
            throw "Rollback snapshot omits required SCM value $requiredValue for $name."
        }
    }
    $dependencyValues = if ([bool]$Snapshot.RegistryValues["DependOnService"].Exists) {
        @($Snapshot.RegistryValues["DependOnService"].Value)
    } else {
        @()
    }
    $dependencyMultiString = if ($dependencyValues.Count -eq 0) {
        [string]([char]0) + [char]0
    } else {
        ($dependencyValues -join [char]0) + [char]0 + [char]0
    }
    $description = if ([bool]$Snapshot.RegistryValues["Description"].Exists) {
        [string]$Snapshot.RegistryValues["Description"].Value
    } else {
        $null
    }
    Initialize-NativeServiceApi
    [Loki.ServiceNativeApi]::RestoreCoreConfiguration(
        $name,
        [uint32]$Snapshot.RegistryValues["Type"].Value,
        [uint32]$Snapshot.RegistryValues["Start"].Value,
        [uint32]$Snapshot.RegistryValues["ErrorControl"].Value,
        [string]$Snapshot.PathName,
        $dependencyMultiString,
        [string]$Snapshot.DisplayName,
        $description
    )
    if ($null -ne $Credential) {
        Set-ServiceIdentitySecurely -Credential $Credential -Names @($name)
    }
    $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$name"
    $registry = Get-Item -LiteralPath $registryPath -ErrorAction Stop
    foreach ($valueName in $Snapshot.RegistryValues.Keys) {
        Set-RegistryValueFromSnapshot -Key $registry -Name $valueName -Snapshot $Snapshot.RegistryValues[$valueName]
    }
    $pythonClassPath = Join-Path $registryPath "PythonClass"
    if ([bool]$Snapshot.PythonClass.KeyExists) {
        New-Item -Path $pythonClassPath -Force | Out-Null
        $pythonClassKey = Get-Item -LiteralPath $pythonClassPath -ErrorAction Stop
        Set-RegistryValueFromSnapshot -Key $pythonClassKey -Name "" -Snapshot $Snapshot.PythonClass.Value
    } else {
        $registry.DeleteSubKeyTree("PythonClass", $false)
    }
    Assert-ServiceSnapshotRestored -Snapshot $Snapshot
}

function Remove-NewService {
    param([Parameter(Mandatory = $true)][string]$Name)
    $service = CimCmdlets\Get-CimInstance Win32_Service -Filter "Name='$Name'" -ErrorAction SilentlyContinue
    if ($null -eq $service) {
        return
    }
    if ([string]$service.State -cne "Stopped") {
        throw "New service $Name unexpectedly started; automatic removal refused."
    }
    Invoke-Native -FilePath $script:trustedScPath -Arguments @("delete", $Name) -Label "Remove newly created service $Name"
    for ($attempt = 0; $attempt -lt 20; $attempt += 1) {
        if ($null -eq (CimCmdlets\Get-CimInstance Win32_Service -Filter "Name='$Name'" -ErrorAction SilentlyContinue)) {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    throw "New service $Name remained registered after rollback removal."
}

function Disable-ResidualService {
    param([Parameter(Mandatory = $true)][string]$Name)
    $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$Name"
    $service = CimCmdlets\Get-CimInstance Win32_Service -Filter "Name='$Name'" -ErrorAction SilentlyContinue
    if ($null -eq $service) {
        return
    }
    if ([string]$service.State -cne "Stopped") {
        $stop = CimCmdlets\Invoke-CimMethod -InputObject $service -MethodName StopService
        if ([int]$stop.ReturnValue -notin @(0, 5, 6)) {
            throw "Residual service $Name could not be stopped."
        }
    }
    Set-ItemProperty -LiteralPath $registryPath -Name "Start" -Type DWord -Value 4
    New-ItemProperty -LiteralPath $registryPath -Name "DelayedAutoStart" -PropertyType DWord -Value 0 -Force | Out-Null
    Invoke-Native -FilePath $script:trustedScPath -Arguments @("config", $Name, "start=", "disabled") -Label "Disable residual service $Name"
    $registry = Get-Item -LiteralPath $registryPath -ErrorAction Stop
    if ([int]$registry.GetValue("Start", -1) -ne 4 -or [int]$registry.GetValue("DelayedAutoStart", -1) -ne 0) {
        throw "Residual service $Name did not reach safe disabled state."
    }
}

function Invoke-ServiceMutationTransaction {
    param(
        [Parameter(Mandatory = $true)][object[]]$Snapshots,
        [Parameter(Mandatory = $true)][scriptblock]$Mutate,
        [Parameter(Mandatory = $true)][scriptblock]$TestExists,
        [Parameter(Mandatory = $true)][scriptblock]$RemoveNew,
        [Parameter(Mandatory = $true)][scriptblock]$RestoreExisting,
        [Parameter(Mandatory = $true)][scriptblock]$DisableResidual
    )
    try {
        & $Mutate
    } catch {
        $originalFailure = $_
        $residualNames = New-Object System.Collections.Generic.List[string]
        for ($index = $Snapshots.Count - 1; $index -ge 0; $index -= 1) {
            $snapshot = $Snapshots[$index]
            $name = [string]$snapshot.Name
            try {
                if ([bool]$snapshot.Exists) {
                    & $RestoreExisting $snapshot
                } elseif (& $TestExists $name) {
                    & $RemoveNew $name
                }
            } catch {
                $residualNames.Add($name)
                try {
                    & $DisableResidual $name
                } catch {
                    # Residual name remains explicit in the terminal error below.
                }
            }
        }
        if ($residualNames.Count -ne 0) {
            $residual = (($residualNames | Sort-Object -Unique) -join ", ")
            throw "Service transaction failed; rollback incomplete for: $residual. Every surviving residue was forced toward stopped/disabled state."
        }
        throw $originalFailure
    }
}

# Trust bootstrap: this block must use only built-in PowerShell/.NET facilities.
# Do not invoke py, candidate scripts, or extracted release code before all three
# digests (operator expectation, transferred archive, and sidecar) are equal.
$archiveTrustStream = $null
$sidecarTrustStream = $null
$bootstrapRoot = $null
$stagedInstallerRunRoot = $null
$reuseAuthorization = $null
$gitTrustStream = $null
$protectedTempRoot = $null
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$previousPath = $env:PATH
$previousPathExt = $env:PATHEXT
$previousComSpec = $env:COMSPEC
try {
if (-not $EvidenceOnly) {
    $stagedInstallerRunRoot = Assert-StagedInstallerInvocation
}
$ArchivePath = [System.IO.Path]::GetFullPath($ArchivePath)
if ([string]::IsNullOrWhiteSpace($SidecarPath)) {
    $SidecarPath = "$ArchivePath.sha256.json"
}
$SidecarPath = [System.IO.Path]::GetFullPath($SidecarPath)
foreach ($requiredFile in @($ArchivePath, $SidecarPath)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required deployment evidence file is missing: $requiredFile"
    }
}
if ([string]$ExpectedArchiveSha256 -cnotmatch "^[0-9A-Fa-f]{64}$") {
    throw "ExpectedArchiveSha256 must be exactly 64 hexadecimal characters."
}
$trustedArchiveHash = ([string]$ExpectedArchiveSha256).ToLowerInvariant()
$archiveTrustStream = [System.IO.File]::Open(
    $ArchivePath,
    [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read,
    [System.IO.FileShare]::None
)
$sidecarTrustStream = [System.IO.File]::Open(
    $SidecarPath,
    [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read,
    [System.IO.FileShare]::None
)
$archiveFile = Get-Item -LiteralPath $ArchivePath
$archiveHash = Get-Sha256Hex -Stream $archiveTrustStream
if ($archiveHash -cne $trustedArchiveHash) {
    throw "Trusted archive SHA-256 mismatch. Candidate code was not invoked."
}
$sidecar = Read-JsonEvidenceStream -Stream $sidecarTrustStream
if ([string]$sidecar.schema -cne "loki-release-archive-digest/v1") {
    throw "Archive SHA-256 sidecar schema is unsupported."
}
if ([string]$sidecar.archive_name -cne $archiveFile.Name) {
    throw "Archive SHA-256 sidecar does not bind this archive name."
}
if ([long]$sidecar.archive_size -ne [long]$archiveFile.Length) {
    throw "Archive SHA-256 sidecar size mismatch."
}
$sidecarArchiveHash = [string]$sidecar.archive_sha256
if ($sidecarArchiveHash -cnotmatch "^[0-9A-Fa-f]{64}$") {
    throw "Archive SHA-256 sidecar digest must be exactly 64 hexadecimal characters."
}
$sidecarArchiveHash = $sidecarArchiveHash.ToLowerInvariant()
if ($sidecarArchiveHash -cne $trustedArchiveHash) {
    throw "Trusted sidecar SHA-256 mismatch. Candidate code was not invoked."
}
if ($EvidenceOnly) {
    Write-Output "Archive and sidecar match the operator-supplied SHA-256. No candidate code was invoked."
    return
}

Assert-WindowsAdministrator
$canonicalWindowsRoot = [System.IO.Path]::GetFullPath("C:\Windows").TrimEnd("\")
$windowsRoot = [System.IO.Path]::GetFullPath($env:WINDIR).TrimEnd("\")
if ($windowsRoot -ine $canonicalWindowsRoot) {
    throw "WINDIR must resolve to the canonical Windows root $canonicalWindowsRoot."
}
$launcher = Get-TrustedSystemExecutable `
    -Path $TrustedPythonLauncher `
    -ExpectedPath (Join-Path $windowsRoot "py.exe") `
    -Label "TrustedPythonLauncher"
$pythonRuntime = Get-TrustedSystemExecutable `
    -Path $TrustedPythonRuntime `
    -ExpectedPath "C:\Program Files\Python312\python.exe" `
    -Label "TrustedPythonRuntime"
$trustedGitExecutable = Get-TrustedSystemExecutable `
    -Path $TrustedGitExecutable `
    -ExpectedPath "C:\Program Files\Git\cmd\git.exe" `
    -Label "Trusted Git"
$trustedPowerShell = Get-TrustedSystemExecutable `
    -Path (Join-Path $windowsRoot "System32\WindowsPowerShell\v1.0\powershell.exe") `
    -ExpectedPath "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -Label "Windows PowerShell"
$script:trustedScPath = Get-TrustedSystemExecutable `
    -Path (Join-Path $windowsRoot "System32\sc.exe") `
    -ExpectedPath "C:\Windows\System32\sc.exe" `
    -Label "Service Controller"
$gitTrustStream = [System.IO.File]::Open(
    $trustedGitExecutable,
    [System.IO.FileMode]::Open,
    [System.IO.FileAccess]::Read,
    [System.IO.FileShare]::Read
)
$trustedProcessPath = [string]::Join(";", [string[]]@(
    $trustedPowerShellHome,
    (Join-Path $windowsRoot "System32"),
    $windowsRoot,
    [System.IO.Path]::GetDirectoryName($pythonRuntime),
    [System.IO.Path]::GetDirectoryName($trustedGitExecutable)
))
$env:PATH = $trustedProcessPath
$env:PATHEXT = ".COM;.EXE;.BAT;.CMD"
$env:COMSPEC = "C:\Windows\System32\cmd.exe"
$protectedTempRoot = Join-Path $stagedInstallerRunRoot (
    "installer-temp-" + [Guid]::NewGuid().ToString("N")
)
[void][System.IO.Directory]::CreateDirectory($protectedTempRoot)
Protect-RollbackEvidenceAcl -Path $protectedTempRoot -Directory
$env:TEMP = $protectedTempRoot
$env:TMP = $protectedTempRoot
$ReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseRoot)
$ConfigPath = [System.IO.Path]::GetFullPath($ConfigPath)
$commissionedConfigPath = [System.IO.Path]::GetFullPath("C:\ProgramData\Loki\config\lokithesungod.env")
if ($ConfigPath -ine $commissionedConfigPath) {
    throw "ConfigPath must be the commissioned stable path $commissionedConfigPath."
}
if (-not (Test-Path -LiteralPath $ConfigPath -PathType Leaf)) {
    throw "Required deployment config file is missing: $ConfigPath"
}
if (-not (Test-Path -LiteralPath $ReleaseRoot -PathType Container)) {
    throw "Extracted release root is missing: $ReleaseRoot"
}
$lokiRoot = [System.IO.Path]::GetFullPath((Join-Path $env:ProgramData "Loki"))
$releaseBase = [System.IO.Path]::GetFullPath((Join-Path $lokiRoot "releases")).TrimEnd("\")
$actualParent = [System.IO.Path]::GetDirectoryName($ReleaseRoot).TrimEnd("\")
if ($actualParent -ine $releaseBase) {
    throw "ReleaseRoot must be directly under $releaseBase."
}
Assert-StableConfig -Path $ConfigPath
$initialSnapshots = @()
foreach ($name in $serviceNames) {
    $snapshot = Get-ServiceSnapshot -Name $name
    Assert-ServiceSnapshotSafeForMutation -Snapshot $snapshot -IdentityMustExist ([bool]$PreserveExistingIdentity)
    $initialSnapshots += $snapshot
}
if ($ReuseExistingVenv) {
    $reuseAuthorization = Open-ReuseVenvAuthorization -Snapshots $initialSnapshots
}
Protect-AdministratorTree -Root $lokiRoot
foreach ($managedDirectory in @(
    (Join-Path $lokiRoot "releases"),
    (Join-Path $lokiRoot "venvs"),
    (Join-Path $lokiRoot "config"),
    (Join-Path $lokiRoot "logs"),
    (Join-Path $lokiRoot "data"),
    (Join-Path $lokiRoot "cache"),
    (Join-Path $lokiRoot "rollback"),
    (Join-Path $lokiRoot "verification")
)) {
    if (-not (Test-Path -LiteralPath $managedDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $managedDirectory | Out-Null
    }
}
Protect-AdministratorTree -Root $lokiRoot

$bootstrapRoot = Join-Path $stagedInstallerRunRoot ("inner-trust-" + [Guid]::NewGuid().ToString("N"))
$trustedManifestHelper = Join-Path $bootstrapRoot "release_manifest.py"
[void][System.IO.Directory]::CreateDirectory($bootstrapRoot)
Protect-RollbackEvidenceAcl -Path $bootstrapRoot -Directory
$trustedArchivePath = Join-Path $bootstrapRoot $archiveFile.Name
$trustedSidecarPath = "$trustedArchivePath.sha256.json"
Copy-LockedEvidenceFile -Source $archiveTrustStream -Destination $trustedArchivePath
Copy-LockedEvidenceFile -Source $sidecarTrustStream -Destination $trustedSidecarPath
Protect-RollbackEvidenceAcl -Path $trustedArchivePath
Protect-RollbackEvidenceAcl -Path $trustedSidecarPath
$trustedCopyHash = Get-Sha256Hex -Path $trustedArchivePath
if ($trustedCopyHash -cne $trustedArchiveHash) {
    throw "Protected archive copy SHA-256 mismatch. Candidate code was not invoked."
}
$sidecar = Get-Content -LiteralPath $trustedSidecarPath -Raw | ConvertFrom-Json
if ([string]$sidecar.schema -cne "loki-release-archive-digest/v1" -or
    [string]$sidecar.archive_name -cne $archiveFile.Name -or
    [long]$sidecar.archive_size -ne [long](Get-Item -LiteralPath $trustedArchivePath).Length -or
    [string]$sidecar.archive_sha256 -cnotmatch "^[0-9A-Fa-f]{64}$" -or
    ([string]$sidecar.archive_sha256).ToLowerInvariant() -cne $trustedArchiveHash) {
    throw "Protected sidecar does not exactly bind the trusted archive copy. Candidate code was not invoked."
}
Copy-TrustedManifestHelper -Archive $trustedArchivePath -Destination $trustedManifestHelper
Protect-RollbackEvidenceAcl -Path $trustedManifestHelper

$runtimeVersion = Invoke-NativeText -FilePath $pythonRuntime -Arguments @("-I", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Python 3.12 runtime validation"
if (-not $runtimeVersion.StartsWith("3.12.")) {
    throw "Trusted Python runtime is not Python 3.12.x. Found $runtimeVersion."
}
$manifestHelper = $trustedManifestHelper
$archiveManifestJson = Invoke-NativeText -FilePath $pythonRuntime -Arguments @(
    "-I", "-B", $trustedManifestHelper,
    "verify-archive", "--archive", $trustedArchivePath, "--sidecar", $trustedSidecarPath
) -Label "Transferred release archive verification"
$directoryManifestJson = Invoke-NativeText -FilePath $pythonRuntime -Arguments @(
    "-I", "-B", $trustedManifestHelper,
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

$actualLeaf = [System.IO.Path]::GetFileName($ReleaseRoot.TrimEnd("\"))
if ($actualLeaf -cne $candidateId) {
    throw "ReleaseRoot must be the versioned path $releaseBase\$candidateId."
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
if ($ReuseExistingVenv) {
    Assert-ReuseEvidenceBindsTarget `
        -Authorization $reuseAuthorization `
        -CandidateId $candidateId `
        -Release $ReleaseRoot `
        -Venv $VenvPath `
        -Config $ConfigPath
} else {
    if (Test-Path -LiteralPath $VenvPath) {
        throw "Candidate venv must not already exist: $VenvPath. Use a new immutable candidate; no preexisting venv will be executed."
    }
    $stagingVenvPath = Join-Path $venvBase (".staging-$candidateId-" + [Guid]::NewGuid().ToString("N"))
    $previousAppRoot = $env:LOKI_APP_ROOT
    $previousEnvPath = $env:LOKI_ENV_PATH
    try {
        $env:LOKI_APP_ROOT = $ReleaseRoot
        $env:LOKI_ENV_PATH = $ConfigPath
        $verificationBase = Join-Path $env:ProgramData "LokiVerification"
        if (-not [System.IO.Directory]::Exists($verificationBase)) {
            [void][System.IO.Directory]::CreateDirectory($verificationBase)
            Protect-RollbackEvidenceAcl -Path $verificationBase -Directory
        }
        Invoke-Native -FilePath $trustedPowerShell -Arguments @(
            "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $ReleaseRoot "scripts\install_loki_local.ps1"),
            "-TrustedPythonLauncher", $launcher,
            "-TrustedPythonRuntime", $pythonRuntime,
            "-TrustedGitExecutable", $trustedGitExecutable,
            "-VenvPath", $stagingVenvPath,
            "-VerificationRoot", (Join-Path $verificationBase $candidateId)
        ) -Label "Release-specific Python 3.12 environment preparation"
    } finally {
        $env:LOKI_APP_ROOT = $previousAppRoot
        $env:LOKI_ENV_PATH = $previousEnvPath
    }
    if (-not (Test-Path -LiteralPath $stagingVenvPath -PathType Container)) {
        throw "Verified staging venv is missing after preparation: $stagingVenvPath"
    }
    if (Test-Path -LiteralPath $VenvPath) {
        throw "Candidate venv target appeared during preparation; protected staging was retained: $stagingVenvPath"
    }
    [System.IO.Directory]::Move($stagingVenvPath, $VenvPath)
}
# Tests may create source-adjacent bytecode after local preparation; remove
# only generated release caches before the immutable post-test verification.
foreach ($cache in @(Get-ChildItem -LiteralPath $ReleaseRoot -Recurse -Force -Directory -Filter "__pycache__" -ErrorAction Stop)) {
    [System.IO.Directory]::Delete($cache.FullName, $true)
}
foreach ($generated in @(
    (Join-Path $ReleaseRoot "data"),
    (Join-Path $ReleaseRoot "tests\fixtures\mcp\generated"),
    (Join-Path $ReleaseRoot "desktop_config.json")
)) {
    if ([System.IO.Directory]::Exists($generated)) {
        [System.IO.Directory]::Delete($generated, $true)
    } elseif ([System.IO.File]::Exists($generated)) {
        [System.IO.File]::Delete($generated)
    }
}
Protect-AdministratorTree -Root $lokiRoot
$postVerificationJson = Invoke-NativeText -FilePath $pythonRuntime -Arguments @(
    "-I", "-B", $manifestHelper,
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
$venvIdentity = Invoke-NativeText -FilePath $venvPython -Arguments @(
    "-I", "-B", "-c", "import os, sys; print('.'.join(map(str, sys.version_info[:3])) + '|' + os.path.normcase(os.path.abspath(sys.prefix)))"
) -Label "Service Python version and prefix validation"
$venvIdentityParts = $venvIdentity.Split(@("|"), 2, [System.StringSplitOptions]::None)
$venvVersion = if ($venvIdentityParts.Count -eq 2) { [string]$venvIdentityParts[0] } else { "" }
$reportedPrefix = if ($venvIdentityParts.Count -eq 2) { [string]$venvIdentityParts[1] } else { "" }
if (-not $venvVersion.StartsWith("3.12.") -or
    -not [string]::Equals([System.IO.Path]::GetFullPath($reportedPrefix), $VenvPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Service Python must be exact Python 3.12.x under the requested venv."
}
Invoke-Native -FilePath $venvPython -Arguments @("-I", "-B", "-c", "import win32service, win32cred") -Label "Service pywin32 import validation"

$serviceLogonRightAdded = $false
$serviceLogonRightCommitted = $false
$serviceLogonRightPreexisting = $false
$credential = $null
try {
    $serviceLogonRightPreexisting = Test-ServiceLogonRight
    if (-not $serviceLogonRightPreexisting) {
        Grant-ServiceLogonRight
        $serviceLogonRightAdded = $true
    }
    if (-not $PreserveExistingIdentity) {
        $credential = Get-ValidatedServiceCredential
    }

    # Re-snapshot after the interactive credential step to close the preflight race.
    $serviceSnapshots = @()
    foreach ($name in $serviceNames) {
        $snapshot = Get-ServiceSnapshot -Name $name
        Assert-ServiceSnapshotSafeForMutation -Snapshot $snapshot -IdentityMustExist ([bool]$PreserveExistingIdentity)
        $serviceSnapshots += $snapshot
    }
    foreach ($snapshot in $serviceSnapshots) {
        Assert-RollbackReleaseManifest -Snapshot $snapshot -PythonRuntime $pythonRuntime -ManifestHelper $manifestHelper
    }
    if ($ReuseExistingVenv) {
        Assert-ReuseAuthorizationStillCurrent -Authorization $reuseAuthorization -Snapshots $serviceSnapshots
    }
    $installId = [Guid]::NewGuid().ToString("N")
    $rollbackPath = Save-RollbackEvidence `
        -InstallId $installId `
        -CandidateId $candidateId `
        -Release $ReleaseRoot `
        -Venv $VenvPath `
        -Snapshots $serviceSnapshots `
        -ServiceLogonRightPreexisting $serviceLogonRightPreexisting

    # BEGIN SERVICE MUTATION TRANSACTION
    $mutateServices = {
        foreach ($snapshot in $serviceSnapshots) {
            $name = [string]$snapshot.Name
            $wrapper = if ($name -ceq "LokiTHESunGodBot") {
                Join-Path $ReleaseRoot "scripts\loki_bot_service.py"
            } else {
                Join-Path $ReleaseRoot "scripts\loki_dashboard_service.py"
            }
            $action = if ([bool]$snapshot.Exists) { "update" } else { "install" }
            Invoke-Native -FilePath $venvPython -Arguments @("-E", "-s", "-B", $wrapper, "--startup", "disabled", $action) -Label "$action disabled service $name"

            $registryPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$name"
            $serviceCache = Join-Path $env:ProgramData "Loki\cache\$name"
            $serviceData = Join-Path $env:ProgramData "Loki\data\bot.db"
            New-Item -ItemType Directory -Path (Split-Path -Parent $serviceData) -Force | Out-Null
            New-Item -ItemType Directory -Path $serviceCache -Force | Out-Null
            $serviceEnvironment = Get-ExpectedServiceEnvironment -Name $name -Release $ReleaseRoot -Config $ConfigPath
            New-ItemProperty -LiteralPath $registryPath -Name "Environment" -PropertyType MultiString -Value $serviceEnvironment -Force | Out-Null
            New-ItemProperty -LiteralPath $registryPath -Name "DelayedAutoStart" -PropertyType DWord -Value 0 -Force | Out-Null
            New-ItemProperty -LiteralPath $registryPath -Name "LokiInstallId" -PropertyType String -Value $installId -Force | Out-Null
        }

        if (-not $PreserveExistingIdentity) {
            Set-ServiceIdentitySecurely -Credential $credential -Names $serviceNames
        }
        foreach ($name in $serviceNames) {
            Assert-InstalledServiceExact `
                -Name $name -Release $ReleaseRoot -Config $ConfigPath `
                -ServiceHost $venvServiceHost -InstallId $installId `
                -ExpectedStartMode "Disabled" -ExpectedDelayed 0
        }

        foreach ($snapshot in $serviceSnapshots) {
            if (-not [bool]$snapshot.Exists) {
                Set-RecoveryPolicy -Name ([string]$snapshot.Name)
            }
        }
        foreach ($name in $serviceNames) {
            Assert-RecoveryPolicyExact -Name $name
            Assert-InstalledServiceExact `
                -Name $name -Release $ReleaseRoot -Config $ConfigPath `
                -ServiceHost $venvServiceHost -InstallId $installId `
                -ExpectedStartMode "Disabled" -ExpectedDelayed 0
        }

        # Delayed automatic startup is the final service-state transition, only
        # after both exact identities, wrappers, environments, and recovery pass.
        foreach ($name in $serviceNames) {
            Invoke-Native -FilePath $script:trustedScPath -Arguments @("config", $name, "start=", "delayed-auto") -Label "Enable delayed automatic startup for $name"
        }
        foreach ($name in $serviceNames) {
            Assert-InstalledServiceExact `
                -Name $name -Release $ReleaseRoot -Config $ConfigPath `
                -ServiceHost $venvServiceHost -InstallId $installId `
                -ExpectedStartMode "Auto" -ExpectedDelayed 1
        }

        $finalVerificationJson = Invoke-NativeText -FilePath $pythonRuntime -Arguments @(
            "-I", "-B", $manifestHelper,
            "verify-directory", "--root", $ReleaseRoot
        ) -Label "Post-registration immutable release verification"
        $finalVerification = $finalVerificationJson | ConvertFrom-Json
        foreach ($field in @("candidate_id", "commit_id", "tree_id")) {
            if ([string]$finalVerification.$field -cne [string]$archiveManifest.$field) {
                throw "Post-registration immutable release evidence mismatch: $field"
            }
        }
        Set-RollbackEvidenceStatus -Path $rollbackPath -Status "installed"
    }

    $testServiceExists = {
        param($name)
        return $null -ne (CimCmdlets\Get-CimInstance Win32_Service -Filter "Name='$name'" -ErrorAction SilentlyContinue)
    }
    $removeNewService = {
        param($name)
        Remove-NewService -Name $name
    }
    $restoreExistingService = {
        param($snapshot)
        Restore-ServiceSnapshot -Snapshot $snapshot -Credential $credential
    }
    $disableResidualService = {
        param($name)
        Disable-ResidualService -Name $name
    }

    try {
        Invoke-ServiceMutationTransaction -Snapshots $serviceSnapshots `
            -Mutate $mutateServices `
            -TestExists $testServiceExists `
            -RemoveNew $removeNewService `
            -RestoreExisting $restoreExistingService `
            -DisableResidual $disableResidualService
    } catch {
        $rollbackStatus = if ($_.Exception.Message -match "rollback incomplete") { "rollback_incomplete" } else { "rolled_back" }
        Set-RollbackEvidenceStatus -Path $rollbackPath -Status $rollbackStatus
        throw
    }
    $serviceLogonRightCommitted = $true
} finally {
    $credential = $null
    if ($serviceLogonRightAdded -and -not $serviceLogonRightCommitted) {
        Revoke-ServiceLogonRight
    }
}

Write-Output "Installed candidate $candidateId with Python $venvVersion. Services remain stopped."
Write-Output "Rollback metadata: $rollbackPath"
Write-Output "Credential Manager values and service-account password were not logged or stored by this script."
} finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    $env:PATH = $previousPath
    $env:PATHEXT = $previousPathExt
    $env:COMSPEC = $previousComSpec
    if ($null -ne $gitTrustStream) {
        $gitTrustStream.Dispose()
    }
    if ($null -ne $reuseAuthorization -and $null -ne $reuseAuthorization.Stream) {
        $reuseAuthorization.Stream.Dispose()
    }
    if ($null -ne $sidecarTrustStream) {
        $sidecarTrustStream.Dispose()
    }
    if ($null -ne $archiveTrustStream) {
        $archiveTrustStream.Dispose()
    }
    if (-not [string]::IsNullOrWhiteSpace($bootstrapRoot) -and
        (Test-Path -LiteralPath $bootstrapRoot -PathType Container)) {
        $bootstrapParent = [System.IO.Path]::GetDirectoryName($bootstrapRoot).TrimEnd("\")
        $expectedBootstrapParent = [System.IO.Path]::GetFullPath($stagedInstallerRunRoot).TrimEnd("\")
        $bootstrapLeaf = [System.IO.Path]::GetFileName($bootstrapRoot)
        if ($bootstrapParent -ieq $expectedBootstrapParent -and
            $bootstrapLeaf -cmatch "^inner-trust-[0-9a-f]{32}$") {
            try {
                [System.IO.Directory]::Delete($bootstrapRoot, $true)
            } catch {
                Write-Warning "Protected trust-bootstrap cleanup failed; retained for inspection: $bootstrapRoot"
            }
        }
    }
}
