[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ArchivePath,
    [Parameter(Mandatory = $true)][string]$ExpectedArchiveSha256,
    [string]$SidecarPath,
    [switch]$PreserveExistingIdentity,
    [switch]$ReuseExistingVenv
)

# SECURITY BOUNDARY: provision this script at the canonical path and verify its
# SHA-256 out of band before execution. Release code cannot establish trust in
# this bootstrap; only the operator-provisioned copy may run.
function Assert-TrustedWindowsPowerShellHost {
    $expectedWindowsRoot = [System.IO.Path]::GetFullPath("C:\Windows").TrimEnd("\")
    $expectedPowerShellHome = [System.IO.Path]::GetFullPath((
        [System.IO.Path]::Combine(
            $expectedWindowsRoot,
            "System32\WindowsPowerShell\v1.0"
        )
    ))
    $expectedExecutable = [System.IO.Path]::GetFullPath((
        [System.IO.Path]::Combine($expectedPowerShellHome, "powershell.exe")
    ))
    if ([string]$PSVersionTable.PSEdition -cne "Desktop" -or
        $PSVersionTable.PSVersion.Major -ne 5 -or
        $PSVersionTable.PSVersion.Minor -ne 1) {
        throw "LOKI service bootstrap requires Windows PowerShell 5.1."
    }
    if ([System.IO.Path]::GetFullPath($PSHOME).TrimEnd("\") -ine $expectedPowerShellHome) {
        throw "LOKI service bootstrap requires canonical PSHOME $expectedPowerShellHome."
    }

    $currentProcess = [System.Diagnostics.Process]::GetCurrentProcess()
    try {
        $actualExecutable = [System.IO.Path]::GetFullPath(
            [string]$currentProcess.MainModule.FileName
        )
    } finally {
        $currentProcess.Dispose()
    }
    if ($actualExecutable -ine $expectedExecutable) {
        throw "LOKI service bootstrap requires canonical host $expectedExecutable."
    }

    $commandLineArguments = [System.Environment]::GetCommandLineArgs()
    if ($commandLineArguments.Length -lt 6 -or
        -not $commandLineArguments[1].Equals("-NoProfile", [StringComparison]::OrdinalIgnoreCase) -or
        -not $commandLineArguments[2].Equals("-ExecutionPolicy", [StringComparison]::OrdinalIgnoreCase) -or
        -not $commandLineArguments[3].Equals("Bypass", [StringComparison]::OrdinalIgnoreCase) -or
        -not $commandLineArguments[4].Equals("-File", [StringComparison]::OrdinalIgnoreCase)) {
        throw "LOKI service bootstrap requires exact powershell.exe -NoProfile ... -File invocation."
    }
    $invokedScript = [System.IO.Path]::GetFullPath(
        [string]$commandLineArguments[5]
    )
    if ([string]::IsNullOrWhiteSpace($PSCommandPath) -or
        $invokedScript -ine [System.IO.Path]::GetFullPath($PSCommandPath)) {
        throw "LOKI service bootstrap -File target does not match its executing script path."
    }

    $approvedWriters = @{
        "S-1-5-18" = $true
        "S-1-5-32-544" = $true
        "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464" = $true
    }
    $approvedWriters[[string]([Security.Principal.WindowsIdentity]::GetCurrent().User.Value)] = $true
    $writeMask = [Security.AccessControl.FileSystemRights]::Write -bor
        [Security.AccessControl.FileSystemRights]::Delete -bor
        [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
        [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
        [Security.AccessControl.FileSystemRights]::TakeOwnership
    $writeMaskValue = [uint64](([int64]$writeMask) -band [int64]0xffffffff)
    $ancestorMutationMask = [Security.AccessControl.FileSystemRights]::Delete -bor
        [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
        [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
        [Security.AccessControl.FileSystemRights]::TakeOwnership
    $ancestorMutationMaskValue = [uint64]((
        [int64]$ancestorMutationMask
    ) -band [int64]0xffffffff)
    $genericWriteMask = [uint64]0x50000000
    $genericAllMask = [uint64]0x10000000
    $volumeRoot = [System.IO.Path]::GetPathRoot($expectedWindowsRoot)
    foreach ($trustedPath in @(
        $volumeRoot,
        $expectedWindowsRoot,
        [System.IO.Path]::Combine($expectedWindowsRoot, "System32"),
        [System.IO.Path]::Combine($expectedWindowsRoot, "System32\WindowsPowerShell"),
        $expectedPowerShellHome,
        $expectedExecutable
    )) {
        $isDirectory = [System.IO.Directory]::Exists($trustedPath)
        $isFile = [System.IO.File]::Exists($trustedPath)
        if (-not $isDirectory -and -not $isFile) {
            throw "Required trusted Windows PowerShell path is missing: $trustedPath"
        }
        $attributes = [System.IO.File]::GetAttributes($trustedPath)
        if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Trusted Windows PowerShell path must not be a reparse point: $trustedPath"
        }
        $acl = if ($isDirectory) {
            [System.IO.Directory]::GetAccessControl($trustedPath)
        } else {
            [System.IO.File]::GetAccessControl($trustedPath)
        }
        $ownerSid = [string]$acl.GetOwner(
            [Security.Principal.SecurityIdentifier]
        ).Value
        if (-not $approvedWriters.ContainsKey($ownerSid)) {
            throw "Trusted Windows PowerShell path owner is not approved: $trustedPath"
        }
        $rules = @($acl.GetAccessRules(
            $true,
            $true,
            [Security.Principal.SecurityIdentifier]
        ))
        foreach ($rule in $rules) {
            if ($rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
                ($rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0) {
                continue
            }
            $sid = [string]$rule.IdentityReference.Value
            $rightsValue = [uint64](([int64]$rule.FileSystemRights) -band [int64]0xffffffff)
            $forbiddenMask = if ($trustedPath -ieq $volumeRoot) {
                $ancestorMutationMaskValue -bor $genericAllMask
            } else {
                $writeMaskValue -bor $genericWriteMask
            }
            if (($rightsValue -band $forbiddenMask) -ne 0 -and
                -not $approvedWriters.ContainsKey($sid)) {
                throw "Trusted Windows PowerShell path is writable by an unapproved principal ${sid}: $trustedPath"
            }
        }
    }
}

Assert-TrustedWindowsPowerShellHost
$trustedPowerShellModuleRoot = [System.IO.Path]::GetFullPath(
    "C:\Windows\System32\WindowsPowerShell\v1.0\Modules"
)
if (-not [System.IO.Directory]::Exists($trustedPowerShellModuleRoot)) {
    throw "Trusted Windows PowerShell module root is missing: $trustedPowerShellModuleRoot"
}
$env:PSModulePath = $trustedPowerShellModuleRoot
$ErrorActionPreference = "Stop"
Microsoft.PowerShell.Core\Set-StrictMode -Version 3.0

function Convert-IdentityReferenceToSid {
    param([Parameter(Mandatory = $true)]$IdentityReference)

    if ($IdentityReference -is [Security.Principal.SecurityIdentifier]) {
        return [string]$IdentityReference.Value
    }
    $translated = $IdentityReference.Translate(
        [Security.Principal.SecurityIdentifier]
    )
    return [string]$translated.Value
}

function Assert-NoReparsePoint {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $isDirectory = [System.IO.Directory]::Exists($fullPath)
    $isFile = [System.IO.File]::Exists($fullPath)
    if (-not $isDirectory -and -not $isFile) {
        throw "Protected deployment path is missing: $fullPath"
    }
    $attributes = [System.IO.File]::GetAttributes($fullPath)
    if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Protected deployment path must not be a reparse point: $Path"
    }
    return [PSCustomObject]@{
        Attributes = $attributes
        FullName = $fullPath
        PSIsContainer = $isDirectory
    }
}

function Assert-ExactProtectedAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$Directory
    )

    $item = Assert-NoReparsePoint -Path $Path
    if ($Directory -and -not $item.PSIsContainer) {
        throw "Protected deployment directory is not a directory: $Path"
    }
    if (-not $Directory -and $item.PSIsContainer) {
        throw "Protected deployment file is not a file: $Path"
    }

    $systemSid = "S-1-5-18"
    $administratorsSid = "S-1-5-32-544"
    $acl = if ($Directory) {
        [System.IO.Directory]::GetAccessControl($Path)
    } else {
        [System.IO.File]::GetAccessControl($Path)
    }
    $ownerSid = [string]$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if ($ownerSid -cne $administratorsSid) {
        throw "Protected deployment ACL owner must be BUILTIN\Administrators: $Path"
    }
    if (-not $acl.AreAccessRulesProtected) {
        throw "Protected deployment ACL must disable inheritance: $Path"
    }

    $rules = @($acl.GetAccessRules(
        $true,
        $false,
        [Security.Principal.SecurityIdentifier]
    ))
    if ($rules.Count -ne 2) {
        throw "Protected deployment ACL must contain exactly two explicit rules: $Path"
    }
    $expectedInheritance = if ($Directory) {
        [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
            [Security.AccessControl.InheritanceFlags]::ObjectInherit
    } else {
        [Security.AccessControl.InheritanceFlags]::None
    }
    $seen = @{}
    foreach ($rule in $rules) {
        $sid = Convert-IdentityReferenceToSid -IdentityReference $rule.IdentityReference
        if ($sid -cne $systemSid -and $sid -cne $administratorsSid) {
            throw "Protected deployment ACL contains an unapproved principal: $Path"
        }
        if ($seen.ContainsKey($sid)) {
            throw "Protected deployment ACL contains a duplicate principal: $Path"
        }
        $seen[$sid] = $true
        if ($rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            $rule.FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl -or
            $rule.InheritanceFlags -ne $expectedInheritance -or
            $rule.PropagationFlags -ne [Security.AccessControl.PropagationFlags]::None -or
            $rule.IsInherited) {
            throw "Protected deployment ACL rule is not exact FullControl: $Path"
        }
    }
    if (-not $seen.ContainsKey($systemSid) -or -not $seen.ContainsKey($administratorsSid)) {
        throw "Protected deployment ACL is missing SYSTEM or BUILTIN\Administrators: $Path"
    }
}

function Set-ExactProtectedAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$Directory
    )

    [void](Assert-NoReparsePoint -Path $Path)
    $systemSid = [Security.Principal.SecurityIdentifier]::new("S-1-5-18")
    $administratorsSid = [Security.Principal.SecurityIdentifier]::new("S-1-5-32-544")
    $security = if ($Directory) {
        [Security.AccessControl.DirectorySecurity]::new()
    } else {
        [Security.AccessControl.FileSecurity]::new()
    }
    $inheritance = if ($Directory) {
        [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
            [Security.AccessControl.InheritanceFlags]::ObjectInherit
    } else {
        [Security.AccessControl.InheritanceFlags]::None
    }
    $security.SetAccessRuleProtection($true, $false)
    $security.SetOwner($administratorsSid)
    foreach ($sid in @($systemSid, $administratorsSid)) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            $inheritance,
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        )
        [void]$security.AddAccessRule($rule)
    }
    if ($Directory) {
        [System.IO.Directory]::SetAccessControl($Path, $security)
    } else {
        [System.IO.File]::SetAccessControl($Path, $security)
    }
    Assert-ExactProtectedAcl -Path $Path -Directory:$Directory
}

function Set-ProtectedTreeAcl {
    param([Parameter(Mandatory = $true)][string]$Root)

    $rootItem = Assert-NoReparsePoint -Path $Root
    if (-not $rootItem.PSIsContainer) {
        throw "Protected tree root is not a directory: $Root"
    }
    Set-ExactProtectedAcl -Path $Root -Directory
    $pending = [System.Collections.Generic.Queue[string]]::new()
    $pending.Enqueue([System.IO.Path]::GetFullPath($Root))
    while ($pending.Count -ne 0) {
        $directory = $pending.Dequeue()
        foreach ($childPath in [System.IO.Directory]::EnumerateFileSystemEntries($directory)) {
            $child = Assert-NoReparsePoint -Path $childPath
            if ($child.PSIsContainer) {
                Set-ExactProtectedAcl -Path $child.FullName -Directory
                $pending.Enqueue([string]$child.FullName)
            } else {
                Set-ExactProtectedAcl -Path $child.FullName
            }
        }
    }
}

function Assert-ProtectedTreeAcl {
    param([Parameter(Mandatory = $true)][string]$Root)

    $rootItem = Assert-NoReparsePoint -Path $Root
    if (-not $rootItem.PSIsContainer) {
        throw "Protected tree root is not a directory: $Root"
    }
    $pending = [System.Collections.Generic.Queue[string]]::new()
    $pending.Enqueue([System.IO.Path]::GetFullPath($Root))
    while ($pending.Count -ne 0) {
        $directory = $pending.Dequeue()
        Assert-ExactProtectedAcl -Path $directory -Directory
        foreach ($childPath in [System.IO.Directory]::EnumerateFileSystemEntries($directory)) {
            $child = Assert-NoReparsePoint -Path $childPath
            if ($child.PSIsContainer) {
                $pending.Enqueue([string]$child.FullName)
            } else {
                Assert-ExactProtectedAcl -Path $child.FullName
            }
        }
    }
}

function Ensure-ProtectedDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)

    $created = $false
    if (-not [System.IO.Directory]::Exists($Path) -and -not [System.IO.File]::Exists($Path)) {
        [void][System.IO.Directory]::CreateDirectory($Path)
        $created = $true
    }
    if (-not [System.IO.Directory]::Exists($Path)) {
        throw "Protected deployment directory is not a directory: $Path"
    }
    if ($created) {
        Set-ExactProtectedAcl -Path $Path -Directory
    } else {
        Assert-ExactProtectedAcl -Path $Path -Directory
    }
}

function Assert-CanonicalBootstrap {
    param([Parameter(Mandatory = $true)][string]$ScriptPath)

    $expectedPath = [System.IO.Path]::GetFullPath(
        "C:\ProgramData\Loki\bootstrap\bootstrap_loki_services.ps1"
    )
    $actualPath = [System.IO.Path]::GetFullPath($ScriptPath)
    if ($actualPath -ine $expectedPath) {
        throw "LOKI service bootstrap must run only from the provisioned canonical path $expectedPath."
    }
    $bootstrapRoot = [System.IO.Path]::GetDirectoryName($expectedPath)
    foreach ($ancestorPath in @("C:\", "C:\ProgramData", "C:\ProgramData\Loki", $bootstrapRoot, $expectedPath)) {
        [void](Assert-NoReparsePoint -Path $ancestorPath)
    }
    Assert-NoUnapprovedAncestorMutationAcl -Path "C:\"
    Assert-NoUnapprovedAncestorMutationAcl -Path "C:\ProgramData"
    Assert-ExactProtectedAcl -Path "C:\ProgramData\Loki" -Directory
    Assert-ExactProtectedAcl -Path $bootstrapRoot -Directory
    Assert-ExactProtectedAcl -Path $expectedPath
}

function Assert-WindowsAdministrator {
    if ($env:OS -ne "Windows_NT") {
        throw "LOKI service bootstrap is supported only on Windows."
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "LOKI service bootstrap requires an elevated PowerShell session."
    }
}

function Assert-NoUnapprovedWriteAcl {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][hashtable]$ApprovedWriters
    )

    $acl = if ([System.IO.Directory]::Exists($Path)) {
        [System.IO.Directory]::GetAccessControl($Path)
    } elseif ([System.IO.File]::Exists($Path)) {
        [System.IO.File]::GetAccessControl($Path)
    } else {
        throw "Trusted system path is missing: $Path"
    }
    $ownerSid = [string]$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if (-not $ApprovedWriters.ContainsKey($ownerSid)) {
        throw "Trusted system path owner is not approved: $Path"
    }
    $writeMask = [Security.AccessControl.FileSystemRights]::Write -bor
        [Security.AccessControl.FileSystemRights]::Delete -bor
        [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
        [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
        [Security.AccessControl.FileSystemRights]::TakeOwnership
    $writeMaskValue = [uint64](([int64]$writeMask) -band [int64]0xffffffff)
    $genericWriteMask = [uint64]0x50000000
    $rules = @($acl.GetAccessRules(
        $true,
        $true,
        [Security.Principal.SecurityIdentifier]
    ))
    foreach ($rule in $rules) {
        if ($rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            ($rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0) {
            continue
        }
        $sid = [string]$rule.IdentityReference.Value
        $rightsValue = [uint64](([int64]$rule.FileSystemRights) -band [int64]0xffffffff)
        if (($rightsValue -band ($writeMaskValue -bor $genericWriteMask)) -ne 0 -and
            -not $ApprovedWriters.ContainsKey($sid)) {
            throw "Trusted system path is writable by an unapproved principal ${sid}: $Path"
        }
    }
}

function Assert-NoUnapprovedAncestorMutationAcl {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not [System.IO.Directory]::Exists($Path)) {
        throw "Trusted ancestor directory is missing: $Path"
    }
    $approvedWriters = @{
        "S-1-5-18" = $true
        "S-1-5-32-544" = $true
        "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464" = $true
    }
    $approvedWriters[[string]([Security.Principal.WindowsIdentity]::GetCurrent().User.Value)] = $true
    $acl = [System.IO.Directory]::GetAccessControl($Path)
    $ownerSid = [string]$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value
    if (-not $approvedWriters.ContainsKey($ownerSid)) {
        throw "Trusted ancestor owner is not approved: $Path"
    }
    $mutationMask = [Security.AccessControl.FileSystemRights]::Delete -bor
        [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
        [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
        [Security.AccessControl.FileSystemRights]::TakeOwnership
    $mutationMaskValue = [uint64](([int64]$mutationMask) -band [int64]0xffffffff)
    $genericAllMask = [uint64]0x10000000
    $rules = @($acl.GetAccessRules(
        $true,
        $true,
        [Security.Principal.SecurityIdentifier]
    ))
    foreach ($rule in $rules) {
        if ($rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            ($rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -ne 0) {
            continue
        }
        $sid = [string]$rule.IdentityReference.Value
        $rightsValue = [uint64](([int64]$rule.FileSystemRights) -band [int64]0xffffffff)
        if (($rightsValue -band ($mutationMaskValue -bor $genericAllMask)) -ne 0 -and
            -not $approvedWriters.ContainsKey($sid)) {
            throw "Trusted ancestor permits unapproved delete or ACL mutation by ${sid}: $Path"
        }
    }
}

function Get-TrustedMachineExecutable {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedPath,
        [Parameter(Mandatory = $true)][string]$TrustedRoot
    )

    $ExpectedPath = [System.IO.Path]::GetFullPath($ExpectedPath)
    $TrustedRoot = [System.IO.Path]::GetFullPath($TrustedRoot).TrimEnd("\")
    if (-not $ExpectedPath.StartsWith($TrustedRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "Trusted executable must be below its canonical machine root: $ExpectedPath"
    }
    if (-not [System.IO.File]::Exists($ExpectedPath)) {
        throw "Required trusted system executable is missing: $ExpectedPath"
    }
    $pathsToValidate = [System.Collections.Generic.List[string]]::new()
    $pathsToValidate.Add($TrustedRoot)
    $ancestor = [System.IO.Path]::GetDirectoryName($ExpectedPath)
    while (-not [string]::IsNullOrWhiteSpace($ancestor) -and
        $ancestor.StartsWith($TrustedRoot + "\", [StringComparison]::OrdinalIgnoreCase)) {
        $pathsToValidate.Add($ancestor)
        $ancestor = [System.IO.Path]::GetDirectoryName($ancestor)
    }
    $pathsToValidate.Add($ExpectedPath)

    $approvedWriters = @{
        "S-1-5-18" = $true
        "S-1-5-32-544" = $true
        "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464" = $true
    }
    $approvedWriters[[string]([Security.Principal.WindowsIdentity]::GetCurrent().User.Value)] = $true
    $volumeRoot = [System.IO.Path]::GetPathRoot($TrustedRoot)
    [void](Assert-NoReparsePoint -Path $volumeRoot)
    Assert-NoUnapprovedAncestorMutationAcl -Path $volumeRoot
    $seenPaths = @{}
    foreach ($protectedPath in $pathsToValidate) {
        $normalizedPath = [System.IO.Path]::GetFullPath($protectedPath)
        if ($seenPaths.ContainsKey($normalizedPath.ToLowerInvariant())) {
            continue
        }
        $seenPaths[$normalizedPath.ToLowerInvariant()] = $true
        [void](Assert-NoReparsePoint -Path $normalizedPath)
        Assert-NoUnapprovedWriteAcl -Path $protectedPath -ApprovedWriters $approvedWriters
    }

    return $ExpectedPath
}

function Get-TrustedSystemExecutable {
    param(
        [Parameter(Mandatory = $true)][string]$ExpectedPath,
        [Parameter(Mandatory = $true)][string]$WindowsRoot
    )

    return Get-TrustedMachineExecutable `
        -ExpectedPath $ExpectedPath `
        -TrustedRoot $WindowsRoot
}

function Assert-TrustedMachineRuntimeTree {
    param([Parameter(Mandatory = $true)][string]$Root)

    $Root = [System.IO.Path]::GetFullPath($Root)
    if (-not [System.IO.Directory]::Exists($Root)) {
        throw "Trusted machine runtime root is missing: $Root"
    }
    $approvedWriters = @{
        "S-1-5-18" = $true
        "S-1-5-32-544" = $true
        "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464" = $true
    }
    $approvedWriters[[string]([Security.Principal.WindowsIdentity]::GetCurrent().User.Value)] = $true
    $pending = [System.Collections.Generic.Queue[string]]::new()
    $pending.Enqueue($Root)
    while ($pending.Count -ne 0) {
        $directory = $pending.Dequeue()
        [void](Assert-NoReparsePoint -Path $directory)
        Assert-NoUnapprovedWriteAcl -Path $directory -ApprovedWriters $approvedWriters
        foreach ($childPath in [System.IO.Directory]::EnumerateFileSystemEntries($directory)) {
            $child = Assert-NoReparsePoint -Path $childPath
            Assert-NoUnapprovedWriteAcl -Path $child.FullName -ApprovedWriters $approvedWriters
            if ($child.PSIsContainer) {
                $pending.Enqueue([string]$child.FullName)
            }
        }
    }
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

function Read-BoundedUtf8JsonStream {
    param(
        [Parameter(Mandatory = $true)][System.IO.Stream]$Stream,
        [Parameter(Mandatory = $true)][long]$MaximumBytes
    )

    if (-not $Stream.CanSeek) {
        throw "JSON evidence stream must be seekable."
    }
    if ($Stream.Length -le 0 -or $Stream.Length -gt $MaximumBytes) {
        throw "Archive SHA-256 sidecar must contain between 1 and $MaximumBytes bytes."
    }
    if ($Stream.Length -gt [int]::MaxValue) {
        throw "Archive SHA-256 sidecar is too large to read safely."
    }
    $Stream.Position = 0
    $buffer = [byte[]]::new([int]$Stream.Length)
    $offset = 0
    while ($offset -lt $buffer.Length) {
        $count = $Stream.Read($buffer, $offset, $buffer.Length - $offset)
        if ($count -le 0) {
            throw "Archive SHA-256 sidecar ended unexpectedly."
        }
        $offset += $count
    }
    $Stream.Position = 0
    $utf8 = [System.Text.UTF8Encoding]::new($false, $true)
    try {
        $json = $utf8.GetString($buffer)
        return $json | Microsoft.PowerShell.Utility\ConvertFrom-Json
    } catch {
        throw "Archive SHA-256 sidecar is not valid bounded UTF-8 JSON."
    }
}

function Assert-ExactSidecar {
    param(
        [Parameter(Mandatory = $true)]$Evidence,
        [Parameter(Mandatory = $true)][string]$ArchiveName,
        [Parameter(Mandatory = $true)][long]$ArchiveSize,
        [Parameter(Mandatory = $true)][string]$ArchiveSha256
    )

    $requiredNames = @(
        "schema",
        "candidate_id",
        "commit_id",
        "tree_id",
        "archive_name",
        "archive_sha256",
        "archive_size"
    )
    $actualNames = @()
    foreach ($property in $Evidence.PSObject.Properties) {
        $actualNames += [string]$property.Name
    }
    if ($actualNames.Count -ne $requiredNames.Count) {
        throw "Archive SHA-256 sidecar must contain exactly the required fields."
    }
    foreach ($name in $requiredNames) {
        if (-not ($actualNames -ccontains $name)) {
            throw "Archive SHA-256 sidecar is missing exact field: $name"
        }
    }
    if ([string]$Evidence.schema -cne "loki-release-archive-digest/v1") {
        throw "Archive SHA-256 sidecar schema is unsupported."
    }
    if ([string]$Evidence.archive_name -cne $ArchiveName) {
        throw "Archive SHA-256 sidecar does not bind this archive name."
    }
    if ([long]$Evidence.archive_size -ne $ArchiveSize) {
        throw "Archive SHA-256 sidecar size mismatch."
    }
    $sidecarHash = [string]$Evidence.archive_sha256
    if ($sidecarHash -cnotmatch "^[0-9A-Fa-f]{64}$") {
        throw "Archive SHA-256 sidecar digest must be exactly 64 hexadecimal characters."
    }
    if ($sidecarHash.ToLowerInvariant() -cne $ArchiveSha256) {
        throw "Trusted sidecar SHA-256 mismatch. Candidate code was not invoked."
    }
    if ([string]$Evidence.candidate_id -cnotmatch "^loki-[0-9a-f]{12}$" -or
        [string]$Evidence.commit_id -cnotmatch "^[0-9a-f]{40}$" -or
        [string]$Evidence.tree_id -cnotmatch "^[0-9a-f]{40}$") {
        throw "Archive SHA-256 sidecar contains malformed candidate identity."
    }
}

function Copy-LockedEvidenceFile {
    param(
        [Parameter(Mandatory = $true)][System.IO.Stream]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    if (-not $Source.CanSeek) {
        throw "Deployment evidence stream must be seekable."
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

function Expand-TrustedBootstrapFiles {
    param(
        [Parameter(Mandatory = $true)][string]$Archive,
        [Parameter(Mandatory = $true)][string]$ManifestDestination,
        [Parameter(Mandatory = $true)][string]$InstallerDestination
    )

    Microsoft.PowerShell.Utility\Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = $null
    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($Archive)
        $specifications = @(
            @("scripts/release_manifest.py", $ManifestDestination),
            @("scripts/install_loki_services.ps1", $InstallerDestination)
        )
        foreach ($specification in $specifications) {
            $entryName = [string]$specification[0]
            $destination = [string]$specification[1]
            $entries = @()
            foreach ($zipEntry in $zip.Entries) {
                if ([string]$zipEntry.FullName -ceq $entryName) {
                    $entries += $zipEntry
                }
            }
            if ($entries.Count -ne 1) {
                throw "Archive must contain exactly one case-sensitive bootstrap entry: $entryName"
            }
            $entry = $entries[0]
            if ($entry.Length -le 0 -or $entry.Length -gt 4194304) {
                throw "Trusted bootstrap entry has an unsafe expanded size: $entryName"
            }
            $sourceStream = $null
            $destinationStream = $null
            try {
                $sourceStream = $entry.Open()
                $destinationStream = [System.IO.File]::Open(
                    $destination,
                    [System.IO.FileMode]::CreateNew,
                    [System.IO.FileAccess]::Write,
                    [System.IO.FileShare]::None
                )
                $sourceStream.CopyTo($destinationStream)
                $destinationStream.Flush($true)
            } finally {
                if ($null -ne $destinationStream) {
                    $destinationStream.Dispose()
                }
                if ($null -ne $sourceStream) {
                    $sourceStream.Dispose()
                }
            }
        }
    } finally {
        if ($null -ne $zip) {
            $zip.Dispose()
        }
    }
}

function Get-TrustedArchiveManifestSha256 {
    param([Parameter(Mandatory = $true)][string]$Archive)

    Microsoft.PowerShell.Utility\Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = $null
    $entryStream = $null
    $sha256 = $null
    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($Archive)
        $entries = @()
        foreach ($zipEntry in $zip.Entries) {
            if ([string]$zipEntry.FullName -ceq "release-manifest.json") {
                $entries += $zipEntry
            }
        }
        if ($entries.Count -ne 1) {
            throw "Archive must contain exactly one case-sensitive release-manifest.json entry."
        }
        $entry = $entries[0]
        if ($entry.Length -le 0 -or $entry.Length -gt 16777216) {
            throw "Trusted release manifest has an unsafe expanded size."
        }
        $entryStream = $entry.Open()
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        $digest = $sha256.ComputeHash($entryStream)
        return [System.BitConverter]::ToString($digest).Replace("-", "").ToLowerInvariant()
    } finally {
        if ($null -ne $sha256) {
            $sha256.Dispose()
        }
        if ($null -ne $entryStream) {
            $entryStream.Dispose()
        }
        if ($null -ne $zip) {
            $zip.Dispose()
        }
    }
}

function Assert-ReleaseManifestBytes {
    param(
        [Parameter(Mandatory = $true)][string]$Release,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $manifestPath = [System.IO.Path]::Combine($Release, "release-manifest.json")
    if (-not [System.IO.File]::Exists($manifestPath)) {
        throw "$Label release-manifest.json is missing."
    }
    [void](Assert-NoReparsePoint -Path $manifestPath)
    if ((Get-Sha256Hex -Path $manifestPath) -cne $ExpectedSha256) {
        throw "$Label release manifest bytes do not match the trusted archive."
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

    $output = (& $FilePath @Arguments 2>&1 | Microsoft.PowerShell.Utility\Out-String).Trim()
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "$Label failed with exit code $exitCode."
    }
    return $output
}

function Assert-ManifestIdentity {
    param(
        [Parameter(Mandatory = $true)]$Expected,
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)][string]$Label
    )

    foreach ($field in @("candidate_id", "commit_id", "tree_id")) {
        if ([string]$Expected.$field -cne [string]$Actual.$field) {
            throw "$Label identity mismatch: $field"
        }
    }
}

$canonicalBootstrapRoot = [System.IO.Path]::GetFullPath("C:\ProgramData\Loki\bootstrap")
$runRoot = $null
$releaseStagingRoot = $null
$archiveTrustStream = $null
$sidecarTrustStream = $null
$pythonLauncherTrustStream = $null
$pythonRuntimeTrustStream = $null
$gitTrustStream = $null
$powershellTrustStream = $null
try {
    Assert-CanonicalBootstrap -ScriptPath $PSCommandPath
    Assert-WindowsAdministrator
    Assert-TrustedMachineRuntimeTree -Root $trustedPowerShellModuleRoot
    if ($ReuseExistingVenv -and -not $PreserveExistingIdentity) {
        throw "ReuseExistingVenv requires PreserveExistingIdentity to prevent an interactive identity mutation."
    }

    $ArchivePath = [System.IO.Path]::GetFullPath($ArchivePath)
    if ([string]::IsNullOrWhiteSpace($SidecarPath)) {
        $SidecarPath = "$ArchivePath.sha256.json"
    }
    $SidecarPath = [System.IO.Path]::GetFullPath($SidecarPath)
    foreach ($requiredFile in @($ArchivePath, $SidecarPath)) {
        if (-not [System.IO.File]::Exists($requiredFile)) {
            throw "Required deployment evidence file is missing: $requiredFile"
        }
        [void](Assert-NoReparsePoint -Path $requiredFile)
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
    $archiveLeaf = [System.IO.Path]::GetFileName($ArchivePath)
    if ([string]::IsNullOrWhiteSpace($archiveLeaf) -or
        $archiveLeaf.IndexOfAny([System.IO.Path]::GetInvalidFileNameChars()) -ne -1) {
        throw "Release archive must have a safe Windows file name."
    }
    $archiveHash = Get-Sha256Hex -Stream $archiveTrustStream
    if ($archiveHash -cne $trustedArchiveHash) {
        throw "Trusted archive SHA-256 mismatch. Candidate code was not invoked."
    }
    $maximumSidecarBytes = 65536
    $sidecar = Read-BoundedUtf8JsonStream `
        -Stream $sidecarTrustStream `
        -MaximumBytes $maximumSidecarBytes
    $sourceSidecarHash = Get-Sha256Hex -Stream $sidecarTrustStream
    Assert-ExactSidecar `
        -Evidence $sidecar `
        -ArchiveName $archiveLeaf `
        -ArchiveSize $archiveTrustStream.Length `
        -ArchiveSha256 $trustedArchiveHash

    $runRoot = [System.IO.Path]::Combine($canonicalBootstrapRoot, (
        "run-" + [Guid]::NewGuid().ToString("N")
    ))
    [void][System.IO.Directory]::CreateDirectory($runRoot)
    Set-ProtectedTreeAcl -Root $runRoot
    $protectedArchivePath = [System.IO.Path]::Combine($runRoot, $archiveLeaf)
    $protectedSidecarPath = "$protectedArchivePath.sha256.json"
    $trustedManifestHelper = [System.IO.Path]::Combine($runRoot, "release_manifest.py")
    $trustedServiceInstaller = [System.IO.Path]::Combine($runRoot, "install_loki_services.ps1")

    Copy-LockedEvidenceFile -Source $archiveTrustStream -Destination $protectedArchivePath
    Copy-LockedEvidenceFile -Source $sidecarTrustStream -Destination $protectedSidecarPath
    Set-ProtectedTreeAcl -Root $runRoot
    if ((Get-Sha256Hex -Path $protectedArchivePath) -cne $trustedArchiveHash) {
        throw "Protected archive copy SHA-256 mismatch. Candidate code was not invoked."
    }
    if ((Get-Sha256Hex -Path $protectedSidecarPath) -cne $sourceSidecarHash) {
        throw "Protected sidecar copy SHA-256 mismatch. Candidate code was not invoked."
    }

    Expand-TrustedBootstrapFiles `
        -Archive $protectedArchivePath `
        -ManifestDestination $trustedManifestHelper `
        -InstallerDestination $trustedServiceInstaller
    Set-ProtectedTreeAcl -Root $runRoot

    $windowsRoot = [System.IO.Path]::GetFullPath($env:WINDIR).TrimEnd("\")
    $canonicalWindowsRoot = [System.IO.Path]::GetFullPath("C:\Windows").TrimEnd("\")
    if ($windowsRoot -ine $canonicalWindowsRoot) {
        throw "WINDIR must resolve to the canonical Windows root $canonicalWindowsRoot."
    }
    $trustedPythonPath = [System.IO.Path]::GetFullPath((
        [System.IO.Path]::Combine($env:WINDIR, "py.exe")
    ))
    $trustedPowerShellPath = [System.IO.Path]::GetFullPath((
        [System.IO.Path]::Combine(
            $env:WINDIR,
            "System32\WindowsPowerShell\v1.0\powershell.exe"
        )
    ))
    $trustedProgramFilesRoot = [System.IO.Path]::GetFullPath("C:\Program Files").TrimEnd("\")
    $trustedPythonRuntimePath = [System.IO.Path]::GetFullPath((
        [System.IO.Path]::Combine(
            $trustedProgramFilesRoot,
            "Python312\python.exe"
        )
    ))
    $trustedGitRoot = [System.IO.Path]::GetFullPath((
        [System.IO.Path]::Combine($trustedProgramFilesRoot, "Git")
    )).TrimEnd("\")
    $trustedGitPath = [System.IO.Path]::GetFullPath((
        [System.IO.Path]::Combine($trustedProgramFilesRoot, "Git\cmd\git.exe")
    ))
    $pythonLauncher = Get-TrustedSystemExecutable `
        -ExpectedPath $trustedPythonPath `
        -WindowsRoot $windowsRoot
    $pythonRuntime = Get-TrustedMachineExecutable `
        -ExpectedPath $trustedPythonRuntimePath `
        -TrustedRoot $trustedProgramFilesRoot
    Assert-TrustedMachineRuntimeTree `
        -Root ([System.IO.Path]::GetDirectoryName($pythonRuntime))
    $trustedGitExecutable = Get-TrustedMachineExecutable `
        -ExpectedPath $trustedGitPath `
        -TrustedRoot $trustedProgramFilesRoot
    Assert-TrustedMachineRuntimeTree -Root $trustedGitRoot
    $powershell = Get-TrustedSystemExecutable `
        -ExpectedPath $trustedPowerShellPath `
        -WindowsRoot $windowsRoot
    $pythonLauncherTrustStream = [System.IO.File]::Open(
        $pythonLauncher,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::Read
    )
    $pythonRuntimeTrustStream = [System.IO.File]::Open(
        $pythonRuntime,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::Read
    )
    $gitTrustStream = [System.IO.File]::Open(
        $trustedGitExecutable,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::Read
    )
    $powershellTrustStream = [System.IO.File]::Open(
        $powershell,
        [System.IO.FileMode]::Open,
        [System.IO.FileAccess]::Read,
        [System.IO.FileShare]::Read
    )
    $pythonInventory = Invoke-NativeText `
        -FilePath $pythonLauncher `
        -Arguments @("-0p") `
        -Label "Machine-wide Python launcher inventory"
    $runtimeListed = $false
    foreach ($inventoryLine in @($pythonInventory -split "`r?`n")) {
        $trimmedInventoryLine = $inventoryLine.Trim()
        if ($trimmedInventoryLine -match "^-(?:V:)?3\.12(?:-\d+)?\s+(?:\*\s+)?(.+?)(?:\s+\*)?$") {
            $listedPath = [string]$Matches[1]
            $listedPath = $listedPath.Trim().Trim('"')
            if ([System.IO.Path]::IsPathRooted($listedPath) -and
                [System.IO.Path]::GetFullPath($listedPath) -ieq $pythonRuntime) {
                $runtimeListed = $true
            }
        }
    }
    if (-not $runtimeListed) {
        throw "Trusted py.exe inventory does not list exact machine-wide Python 3.12 runtime $pythonRuntime."
    }
    $pythonVersion = Invoke-NativeText -FilePath $pythonRuntime -Arguments @(
        "-I", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    ) -Label "Machine-wide Python 3.12 runtime validation"
    if (-not $pythonVersion.StartsWith("3.12.")) {
        throw "Machine-wide runtime is not Python 3.12.x. Found $pythonVersion."
    }
    $archiveManifestJson = Invoke-NativeText -FilePath $pythonRuntime -Arguments @(
        "-I", "-B", $trustedManifestHelper,
        "verify-archive", "--archive", $protectedArchivePath, "--sidecar", $protectedSidecarPath
    ) -Label "Protected release archive verification"
    $archiveManifest = $archiveManifestJson | Microsoft.PowerShell.Utility\ConvertFrom-Json
    Assert-ManifestIdentity -Expected $sidecar -Actual $archiveManifest -Label "Archive and sidecar"
    $trustedReleaseManifestSha256 = Get-TrustedArchiveManifestSha256 `
        -Archive $protectedArchivePath

    $candidateId = [string]$archiveManifest.candidate_id
    if ($candidateId -cnotmatch "^loki-[0-9a-f]{12}$") {
        throw "Verified candidate_id is not a canonical Loki release identifier."
    }
    $commitId = [string]$archiveManifest.commit_id
    $treeId = [string]$archiveManifest.tree_id
    if ($commitId -cnotmatch "^[0-9a-f]{40}$" -or
        $treeId -cnotmatch "^[0-9a-f]{40}$" -or
        $candidateId -cne ("loki-" + $commitId.Substring(0, 12))) {
        throw "Verified archive contains malformed or inconsistent Git identity."
    }

    $lokiRoot = [System.IO.Path]::GetFullPath("C:\ProgramData\Loki")
    $releaseBase = [System.IO.Path]::GetFullPath("C:\ProgramData\Loki\releases")
    $venvBase = [System.IO.Path]::GetFullPath("C:\ProgramData\Loki\venvs")
    Ensure-ProtectedDirectory -Path $lokiRoot
    Ensure-ProtectedDirectory -Path $releaseBase
    Ensure-ProtectedDirectory -Path $venvBase
    $releaseRoot = [System.IO.Path]::Combine($releaseBase, $candidateId)
    $venvPath = [System.IO.Path]::Combine($venvBase, $candidateId)
    $releaseTargetExists = [System.IO.Directory]::Exists($releaseRoot) -or
        [System.IO.File]::Exists($releaseRoot)
    $venvTargetExists = [System.IO.Directory]::Exists($venvPath) -or
        [System.IO.File]::Exists($venvPath)
    if ($ReuseExistingVenv) {
        if (-not $releaseTargetExists -or
            -not $venvTargetExists -or
            -not [System.IO.Directory]::Exists($releaseRoot) -or
            -not [System.IO.Directory]::Exists($venvPath)) {
            throw "ReuseExistingVenv requires an existing exact release and venv pair."
        }
    } else {
        if ($releaseTargetExists) {
            throw "Final release root already exists; immutable deployment refused: $releaseRoot. Normal deployment requires absent release and venv targets."
        }
        if ($venvTargetExists) {
            throw "Candidate venv already exists; pass -ReuseExistingVenv only for an operator-approved exact candidate: $venvPath. Normal deployment requires absent release and venv targets."
        }
    }

    $releaseManifest = $null
    if ($ReuseExistingVenv) {
        Assert-ProtectedTreeAcl -Root $releaseRoot
        Assert-ReleaseManifestBytes `
            -Release $releaseRoot `
            -ExpectedSha256 $trustedReleaseManifestSha256 `
            -Label "Existing"
        $releaseManifestJson = Invoke-NativeText -FilePath $pythonRuntime -Arguments @(
            "-I", "-B", $trustedManifestHelper,
            "verify-directory", "--root", $releaseRoot
        ) -Label "Existing immutable release verification"
        $releaseManifest = $releaseManifestJson | Microsoft.PowerShell.Utility\ConvertFrom-Json
        Assert-ManifestIdentity -Expected $archiveManifest -Actual $releaseManifest -Label "Existing release"
    } else {
        $releaseStagingRoot = [System.IO.Path]::Combine(
            $releaseBase,
            ".staging-" + $candidateId + "-" + [Guid]::NewGuid().ToString("N")
        )
        [void][System.IO.Directory]::CreateDirectory($releaseStagingRoot)
        Set-ProtectedTreeAcl -Root $releaseStagingRoot
        [System.IO.Compression.ZipFile]::ExtractToDirectory(
            $protectedArchivePath,
            $releaseStagingRoot
        )
        Set-ProtectedTreeAcl -Root $releaseStagingRoot
        Assert-ReleaseManifestBytes `
            -Release $releaseStagingRoot `
            -ExpectedSha256 $trustedReleaseManifestSha256 `
            -Label "Staged"
        $releaseManifestJson = Invoke-NativeText -FilePath $pythonRuntime -Arguments @(
            "-I", "-B", $trustedManifestHelper,
            "verify-directory", "--root", $releaseStagingRoot
        ) -Label "Staged release manifest verification"
        $releaseManifest = $releaseManifestJson | Microsoft.PowerShell.Utility\ConvertFrom-Json
        Assert-ManifestIdentity -Expected $archiveManifest -Actual $releaseManifest -Label "Staged release"
        if ([System.IO.Directory]::Exists($releaseRoot) -or
            [System.IO.File]::Exists($releaseRoot)) {
            throw "Final release root appeared during staging; protected staging was retained: $releaseStagingRoot"
        }
        [System.IO.Directory]::Move($releaseStagingRoot, $releaseRoot)
        $releaseStagingRoot = $null
        Assert-ReleaseManifestBytes `
            -Release $releaseRoot `
            -ExpectedSha256 $trustedReleaseManifestSha256 `
            -Label "Promoted"
        $releaseManifestJson = Invoke-NativeText -FilePath $pythonRuntime -Arguments @(
            "-I", "-B", $trustedManifestHelper,
            "verify-directory", "--root", $releaseRoot
        ) -Label "Promoted release manifest verification"
        $releaseManifest = $releaseManifestJson | Microsoft.PowerShell.Utility\ConvertFrom-Json
        Assert-ManifestIdentity -Expected $archiveManifest -Actual $releaseManifest -Label "Promoted release"
    }

    if ($ReuseExistingVenv) {
        Assert-ProtectedTreeAcl -Root $venvPath
    }

    $installerArguments = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", $trustedServiceInstaller,
        "-ReleaseRoot", $releaseRoot,
        "-VenvPath", $venvPath,
        "-ArchivePath", $protectedArchivePath,
        "-SidecarPath", $protectedSidecarPath,
        "-ExpectedArchiveSha256", $trustedArchiveHash,
        "-TrustedPythonLauncher", $pythonLauncher,
        "-TrustedPythonRuntime", $pythonRuntime,
        "-TrustedGitExecutable", $trustedGitExecutable
    )
    if ($PreserveExistingIdentity) {
        $installerArguments += "-PreserveExistingIdentity"
    }
    if ($ReuseExistingVenv) {
        $installerArguments += "-ReuseExistingVenv"
    }
    Invoke-Native `
        -FilePath $powershell `
        -Arguments $installerArguments `
        -Label "Protected Loki service installer"

    Microsoft.PowerShell.Utility\Write-Output "Prepared candidate $candidateId through trusted bootstrap. Services remain stopped."
} finally {
    if ($null -ne $powershellTrustStream) {
        $powershellTrustStream.Dispose()
    }
    if ($null -ne $pythonLauncherTrustStream) {
        $pythonLauncherTrustStream.Dispose()
    }
    if ($null -ne $pythonRuntimeTrustStream) {
        $pythonRuntimeTrustStream.Dispose()
    }
    if ($null -ne $gitTrustStream) {
        $gitTrustStream.Dispose()
    }
    if ($null -ne $sidecarTrustStream) {
        $sidecarTrustStream.Dispose()
    }
    if ($null -ne $archiveTrustStream) {
        $archiveTrustStream.Dispose()
    }
    try {
        if (-not [string]::IsNullOrWhiteSpace($runRoot) -and
            [System.IO.Directory]::Exists($runRoot)) {
            $runParent = [System.IO.Path]::GetDirectoryName($runRoot).TrimEnd("\")
            $runLeaf = [System.IO.Path]::GetFileName($runRoot)
            if ($runParent -ieq $canonicalBootstrapRoot -and $runLeaf -cmatch "^run-[0-9a-f]{32}$") {
                $runAttributes = [System.IO.File]::GetAttributes($runRoot)
                if (($runAttributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
                    Microsoft.PowerShell.Utility\Write-Warning "Protected bootstrap run cleanup refused a reparse point: $runRoot"
                } else {
                    [System.IO.Directory]::Delete($runRoot, $true)
                }
            }
        }
    } catch {
        Microsoft.PowerShell.Utility\Write-Warning "Protected bootstrap run cleanup failed; retained for inspection: $runRoot"
    }
}
