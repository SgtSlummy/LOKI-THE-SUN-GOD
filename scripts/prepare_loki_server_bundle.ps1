[CmdletBinding()]
param(
    [string]$OutputPath,
    [switch]$Force
)

if ([string]$PSVersionTable.PSEdition -cne "Desktop" -or
    $PSVersionTable.PSVersion.Major -ne 5 -or
    $PSVersionTable.PSVersion.Minor -ne 1) {
    throw "LOKI bundle preparation requires Windows PowerShell 5.1."
}
$expectedPowerShell = [System.IO.Path]::GetFullPath(
    "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
)
$currentPowerShellProcess = [System.Diagnostics.Process]::GetCurrentProcess()
try {
    $actualPowerShell = [System.IO.Path]::GetFullPath(
        [string]$currentPowerShellProcess.MainModule.FileName
    )
} finally {
    $currentPowerShellProcess.Dispose()
}
if ($actualPowerShell -ine $expectedPowerShell) {
    throw "LOKI bundle preparation requires canonical host $expectedPowerShell."
}
$preparerCommandLine = [System.Environment]::GetCommandLineArgs()
if ($preparerCommandLine.Length -lt 6 -or
    -not $preparerCommandLine[1].Equals("-NoProfile", [StringComparison]::OrdinalIgnoreCase) -or
    -not $preparerCommandLine[2].Equals("-ExecutionPolicy", [StringComparison]::OrdinalIgnoreCase) -or
    -not $preparerCommandLine[3].Equals("Bypass", [StringComparison]::OrdinalIgnoreCase) -or
    -not $preparerCommandLine[4].Equals("-File", [StringComparison]::OrdinalIgnoreCase) -or
    [System.IO.Path]::GetFullPath([string]$preparerCommandLine[5]) -ine
        [System.IO.Path]::GetFullPath($PSCommandPath)) {
    throw "LOKI bundle preparation requires exact powershell.exe -NoProfile ... -File invocation."
}

$ErrorActionPreference = "Stop"
$trustedPowerShellHome = [System.IO.Path]::GetDirectoryName($expectedPowerShell)
$env:PSModulePath = [System.IO.Path]::Combine($trustedPowerShellHome, "Modules")
Microsoft.PowerShell.Core\Import-Module -Name (
    [System.IO.Path]::Combine(
        $trustedPowerShellHome,
        "Modules\Microsoft.PowerShell.Utility\Microsoft.PowerShell.Utility.psd1"
    )
) -Force -ErrorAction Stop
Microsoft.PowerShell.Core\Set-StrictMode -Version 3.0

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

function Initialize-GuardedOutputNativeApi {
    if ($null -ne ("LokiGuardedOutputNative" -as [type])) {
        return
    }
    Microsoft.PowerShell.Utility\Add-Type -TypeDefinition @"
using Microsoft.Win32.SafeHandles;
using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

public static class LokiGuardedOutputNative
{
    private const uint GenericRead = 0x80000000;
    private const uint OpenExisting = 3;
    private const uint FileFlagOpenReparsePoint = 0x00200000;
    private const uint FileAttributeReparsePoint = 0x00000400;

    [StructLayout(LayoutKind.Sequential)]
    private struct FileAttributeTagInfo
    {
        public uint FileAttributes;
        public uint ReparseTag;
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFile(
        string fileName,
        uint desiredAccess,
        FileShare shareMode,
        IntPtr securityAttributes,
        uint creationDisposition,
        uint flagsAndAttributes,
        IntPtr templateFile);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandleEx(
        SafeFileHandle file,
        int fileInformationClass,
        out FileAttributeTagInfo fileInformation,
        uint bufferSize);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandle(
        SafeFileHandle file,
        StringBuilder filePath,
        uint filePathLength,
        uint flags);

    private static string NormalizeFinalPath(string path)
    {
        if (path.StartsWith(@"\\?\UNC\", StringComparison.OrdinalIgnoreCase))
            path = @"\\" + path.Substring(8);
        else if (path.StartsWith(@"\\?\", StringComparison.OrdinalIgnoreCase))
            path = path.Substring(4);
        return Path.GetFullPath(path);
    }

    public static FileStream OpenExistingForRead(string path)
    {
        string expected = Path.GetFullPath(path);
        SafeFileHandle handle = CreateFile(
            expected,
            GenericRead,
            FileShare.Read,
            IntPtr.Zero,
            OpenExisting,
            FileFlagOpenReparsePoint,
            IntPtr.Zero);
        if (handle.IsInvalid)
        {
            int error = Marshal.GetLastWin32Error();
            handle.Dispose();
            throw new Win32Exception(error, "Unable to lock existing guarded file.");
        }
        try
        {
            FileAttributeTagInfo info;
            if (!GetFileInformationByHandleEx(
                    handle,
                    9,
                    out info,
                    (uint)Marshal.SizeOf(typeof(FileAttributeTagInfo))))
                throw new Win32Exception(
                    Marshal.GetLastWin32Error(),
                    "Unable to inspect guarded file handle.");
            if ((info.FileAttributes & FileAttributeReparsePoint) != 0)
                throw new IOException("Guarded file must not be a reparse point: " + expected);

            StringBuilder finalPathBuffer = new StringBuilder(32768);
            uint finalPathLength = GetFinalPathNameByHandle(
                handle,
                finalPathBuffer,
                (uint)finalPathBuffer.Capacity,
                0);
            if (finalPathLength == 0 || finalPathLength >= finalPathBuffer.Capacity)
                throw new Win32Exception(
                    Marshal.GetLastWin32Error(),
                    "Unable to resolve guarded file handle.");
            string finalPath = NormalizeFinalPath(finalPathBuffer.ToString());
            if (!String.Equals(expected, finalPath, StringComparison.OrdinalIgnoreCase))
                throw new IOException("Guarded file resolved outside its exact path: " + expected);

            FileStream stream = new FileStream(handle, FileAccess.Read);
            handle = null;
            return stream;
        }
        finally
        {
            if (handle != null)
                handle.Dispose();
        }
    }

}
"@
}

function Assert-NoReparsePathAncestors {
    param(
        [Parameter(Mandatory = $true)][string]$Directory,
        [switch]$RequireMutationProtection
    )

    if ($RequireMutationProtection) {
        $approvedWriters = @{
            ([string][Security.Principal.WindowsIdentity]::GetCurrent().User.Value) = $true
            "S-1-3-4" = $true
            "S-1-5-18" = $true
            "S-1-5-32-544" = $true
            "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464" = $true
        }
        $mutationMask = [Security.AccessControl.FileSystemRights]::Delete -bor
            [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
            [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
            [Security.AccessControl.FileSystemRights]::TakeOwnership
        $mutationMaskValue = [uint64](([int64]$mutationMask) -band [int64]0xffffffff)
        $genericAllMask = [uint64]0x10000000
    }
    $current = [System.IO.Path]::GetFullPath($Directory)
    while (-not [string]::IsNullOrWhiteSpace($current)) {
        if (-not [System.IO.Directory]::Exists($current)) {
            throw "Guarded path parent directory is missing: $current"
        }
        $attributes = [System.IO.File]::GetAttributes($current)
        if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Guarded path parent must not be a reparse point: $current"
        }
        if ($RequireMutationProtection) {
            $acl = [System.IO.Directory]::GetAccessControl($current)
            $ownerSid = [string]$acl.GetOwner(
                [Security.Principal.SecurityIdentifier]
            ).Value
            if (-not $approvedWriters.ContainsKey($ownerSid)) {
                throw "Guarded path parent owner is not approved: $current"
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
                if (($rightsValue -band ($mutationMaskValue -bor $genericAllMask)) -ne 0 -and
                    -not $approvedWriters.ContainsKey($sid)) {
                    throw "Guarded path parent permits unapproved delete or ACL mutation by ${sid}: $current"
                }
            }
        }
        $parent = [System.IO.Directory]::GetParent($current)
        if ($null -eq $parent) {
            break
        }
        $current = [string]$parent.FullName
    }
}

function Open-GuardedEvidenceReadStream {
    param([Parameter(Mandatory = $true)][string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    Assert-NoReparsePathAncestors -Directory ([System.IO.Path]::GetDirectoryName($fullPath))
    if (-not [System.IO.File]::Exists($fullPath)) {
        throw "Guarded evidence file is missing: $fullPath"
    }
    Initialize-GuardedOutputNativeApi
    return [LokiGuardedOutputNative]::OpenExistingForRead($fullPath)
}

function Open-GuardedOutputStream {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$Overwrite
    )

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    Assert-NoReparsePathAncestors -Directory ([System.IO.Path]::GetDirectoryName($fullPath))
    if ([System.IO.Directory]::Exists($fullPath)) {
        throw "Guarded output path is a directory: $fullPath"
    }
    if ([System.IO.File]::Exists($fullPath)) {
        throw "Release artifact already exists: $fullPath"
    }
    return [System.IO.File]::Open(
        $fullPath,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None
    )
}

function Write-GuardedAsciiFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Value,
        [switch]$Overwrite
    )

    $stream = $null
    try {
        $stream = Open-GuardedOutputStream -Path $Path -Overwrite:$Overwrite
        $bytes = [System.Text.Encoding]::ASCII.GetBytes($Value + [Environment]::NewLine)
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
    }
}

function Copy-GuardedStreamToNewFile {
    param(
        [Parameter(Mandatory = $true)][System.IO.Stream]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    if (-not $Source.CanSeek) {
        throw "Guarded source stream must be seekable."
    }
    $destinationStream = $null
    try {
        $Source.Position = 0
        $destinationStream = Open-GuardedOutputStream -Path $Destination
        $Source.CopyTo($destinationStream)
        $destinationStream.Flush($true)
        $Source.Position = 0
    } finally {
        if ($null -ne $destinationStream) {
            $destinationStream.Dispose()
        }
    }
}

function Get-ProtectedBuildDirectorySecurity {
    $currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $systemSid = [Security.Principal.SecurityIdentifier]::new("S-1-5-18")
    $administratorsSid = [Security.Principal.SecurityIdentifier]::new("S-1-5-32-544")
    $security = [Security.AccessControl.DirectorySecurity]::new()
    $security.SetAccessRuleProtection($true, $false)
    $security.SetOwner($currentSid)
    foreach ($sid in @($currentSid, $systemSid, $administratorsSid)) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            $sid,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
                [Security.AccessControl.InheritanceFlags]::ObjectInherit,
            [Security.AccessControl.PropagationFlags]::None,
            [Security.AccessControl.AccessControlType]::Allow
        )
        [void]$security.AddAccessRule($rule)
    }
    return $security
}

function Assert-ExactProtectedBuildDirectory {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not [System.IO.Directory]::Exists($Path)) {
        throw "Protected build directory is missing: $Path"
    }
    $attributes = [System.IO.File]::GetAttributes($Path)
    if (($attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Protected build directory must not be a reparse point: $Path"
    }
    $currentSid = [string][Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $expectedSids = @{
        $currentSid = $true
        "S-1-5-18" = $true
        "S-1-5-32-544" = $true
    }
    $acl = [System.IO.Directory]::GetAccessControl($Path)
    if ([string]$acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -cne $currentSid -or
        -not $acl.AreAccessRulesProtected) {
        throw "Protected build directory owner or inheritance is not exact: $Path"
    }
    $rules = @($acl.GetAccessRules(
        $true,
        $false,
        [Security.Principal.SecurityIdentifier]
    ))
    if ($rules.Count -ne 3) {
        throw "Protected build directory ACL rule count is not exact: $Path"
    }
    $seen = @{}
    $expectedInheritance = [Security.AccessControl.InheritanceFlags]::ContainerInherit -bor
        [Security.AccessControl.InheritanceFlags]::ObjectInherit
    foreach ($rule in $rules) {
        $sid = [string]$rule.IdentityReference.Value
        if (-not $expectedSids.ContainsKey($sid) -or
            $seen.ContainsKey($sid) -or
            $rule.AccessControlType -ne [Security.AccessControl.AccessControlType]::Allow -or
            $rule.FileSystemRights -ne [Security.AccessControl.FileSystemRights]::FullControl -or
            $rule.InheritanceFlags -ne $expectedInheritance -or
            $rule.PropagationFlags -ne [Security.AccessControl.PropagationFlags]::None -or
            $rule.IsInherited) {
            throw "Protected build directory ACL is not exact: $Path"
        }
        $seen[$sid] = $true
    }
}

function Ensure-ProtectedBuildParent {
    $parent = [System.IO.Path]::GetFullPath("C:\ProgramData\LokiBundleStaging")
    Assert-NoReparsePathAncestors `
        -Directory ([System.IO.Path]::GetDirectoryName($parent)) `
        -RequireMutationProtection
    if (-not [System.IO.Directory]::Exists($parent)) {
        $security = Get-ProtectedBuildDirectorySecurity
        [void][System.IO.Directory]::CreateDirectory($parent, $security)
    }
    Assert-ExactProtectedBuildDirectory -Path $parent
    return $parent
}

function New-ProtectedBuildDirectory {
    param([Parameter(Mandatory = $true)][string]$Parent)

    Assert-ExactProtectedBuildDirectory -Path $Parent
    $security = Get-ProtectedBuildDirectorySecurity
    $buildRoot = [System.IO.Path]::Combine(
        $Parent,
        ".loki-build-" + [Guid]::NewGuid().ToString("N")
    )
    [void][System.IO.Directory]::CreateDirectory($buildRoot, $security)
    Assert-ExactProtectedBuildDirectory -Path $buildRoot
    return $buildRoot
}

function Export-TrustedBootstrap {
    param(
        [Parameter(Mandatory = $true)][string]$Archive,
        [Parameter(Mandatory = $true)][string]$Destination,
        [switch]$Overwrite
    )
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = $null
    $sourceStream = $null
    $destinationStream = $null
    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($Archive)
        $entries = @($zip.Entries | Where-Object {
            [string]$_.FullName -ceq "scripts/bootstrap_loki_services.ps1"
        })
        if ($entries.Count -ne 1 -or [long]$entries[0].Length -le 0) {
            throw "Verified archive must contain exactly one nonempty external service bootstrap."
        }
        $sourceStream = $entries[0].Open()
        $destinationStream = Open-GuardedOutputStream `
            -Path $Destination `
            -Overwrite:$Overwrite
        $sourceStream.CopyTo($destinationStream)
        $destinationStream.Flush($true)
        $destinationStream.Position = 0
        return Get-Sha256Hex -Stream $destinationStream
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

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$launcher = (Get-Command py -ErrorAction Stop).Source
$version = Invoke-NativeText -FilePath $launcher -Arguments @("-3.12", "-I", "-c", "import sys; print('.'.join(map(str, sys.version_info[:3])))") -Label "Python 3.12 launcher validation"
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
$outputDirectory = [System.IO.Path]::GetFullPath($outputDirectory)
Assert-NoReparsePathAncestors -Directory $outputDirectory
$sidecarPath = "$OutputPath.sha256.json"
$textDigestPath = "$OutputPath.sha256"
$bootstrapPath = "$OutputPath.bootstrap.ps1"
$bootstrapDigestPath = "$bootstrapPath.sha256"
foreach ($externalArtifact in @(
    $OutputPath,
    $sidecarPath,
    $textDigestPath,
    $bootstrapPath,
    $bootstrapDigestPath
)) {
    if ([System.IO.File]::Exists($externalArtifact) -or
        [System.IO.Directory]::Exists($externalArtifact)) {
        throw "Release artifact already exists; -Force never overwrites trust evidence: $externalArtifact"
    }
}

$protectedBuildParent = Ensure-ProtectedBuildParent
$buildRoot = New-ProtectedBuildDirectory -Parent $protectedBuildParent
$trustedScratchRoot = New-ProtectedBuildDirectory -Parent $buildRoot
$originalProcessTemp = [System.Environment]::GetEnvironmentVariable(
    "TEMP",
    [System.EnvironmentVariableTarget]::Process
)
$originalProcessTmp = [System.Environment]::GetEnvironmentVariable(
    "TMP",
    [System.EnvironmentVariableTarget]::Process
)
$stagedArchivePath = [System.IO.Path]::Combine(
    $buildRoot,
    [System.IO.Path]::GetFileName($OutputPath)
)
$stagedSidecarPath = "$stagedArchivePath.sha256.json"
$stagedTextDigestPath = "$stagedArchivePath.sha256"
$archiveTrustStream = $null
$sidecarTrustStream = $null
$textDigestTrustStream = $null
try {
    $env:TEMP = $trustedScratchRoot
    $env:TMP = $trustedScratchRoot
    $arguments = @(
        (Join-Path $PSScriptRoot "release_manifest.py"),
        "build",
        "--source", $root,
        "--archive", $stagedArchivePath
    )
    $result = Invoke-NativeText -FilePath $launcher -Arguments (@("-3.12", "-I", "-B") + $arguments) -Label "Immutable release archive build"
    $buildEvidence = $result | ConvertFrom-Json
    $expectedArchiveHash = [string]$buildEvidence.archive_sha256
    if ([string]$buildEvidence.candidate_id -cne $candidateId -or
        [string]$buildEvidence.commit_id -cnotmatch "^[0-9a-f]{40}$" -or
        [string]$buildEvidence.tree_id -cnotmatch "^[0-9a-f]{40}$" -or
        $expectedArchiveHash -cnotmatch "^[0-9a-f]{64}$" -or
        [System.IO.Path]::GetFullPath([string]$buildEvidence.archive_path) -ine $stagedArchivePath) {
        throw "Release builder returned malformed or mismatched immutable evidence."
    }
    foreach ($stagedPath in @(
        $stagedArchivePath,
        $stagedSidecarPath,
        $stagedTextDigestPath
    )) {
        if (-not [System.IO.File]::Exists($stagedPath)) {
            throw "Release builder did not create required staged artifact: $stagedPath"
        }
    }

    $archiveTrustStream = Open-GuardedEvidenceReadStream -Path $stagedArchivePath
    $sidecarTrustStream = Open-GuardedEvidenceReadStream -Path $stagedSidecarPath
    $textDigestTrustStream = Open-GuardedEvidenceReadStream -Path $stagedTextDigestPath
    $archiveHash = Get-Sha256Hex -Stream $archiveTrustStream
    $sidecarHash = Get-Sha256Hex -Stream $sidecarTrustStream
    $textDigestHash = Get-Sha256Hex -Stream $textDigestTrustStream
    if ($archiveHash -cne $expectedArchiveHash) {
        throw "Built archive SHA-256 changed before locked verification."
    }

    $verifiedArchiveJson = Invoke-NativeText -FilePath $launcher -Arguments @(
        "-3.12", "-I", "-B",
        (Join-Path $PSScriptRoot "release_manifest.py"),
        "verify-archive",
        "--archive", $stagedArchivePath,
        "--sidecar", $stagedSidecarPath
    ) -Label "Release archive verification"
    $verifiedArchive = $verifiedArchiveJson | ConvertFrom-Json
    foreach ($field in @("candidate_id", "commit_id", "tree_id")) {
        if ([string]$verifiedArchive.$field -cne [string]$buildEvidence.$field) {
            throw "Build and locked archive identity mismatch: $field"
        }
    }

    $bootstrapHash = Export-TrustedBootstrap `
        -Archive $stagedArchivePath `
        -Destination $bootstrapPath
    if ((Get-Sha256Hex -Stream $archiveTrustStream) -cne $archiveHash) {
        throw "Post-export locked archive SHA-256 mismatch."
    }
    if ((Get-Sha256Hex -Stream $sidecarTrustStream) -cne $sidecarHash) {
        throw "Post-export locked sidecar SHA-256 mismatch."
    }
    if ((Get-Sha256Hex -Stream $textDigestTrustStream) -cne $textDigestHash) {
        throw "Post-export locked portable digest SHA-256 mismatch."
    }
    Invoke-NativeText -FilePath $launcher -Arguments @(
        "-3.12", "-I", "-B",
        (Join-Path $PSScriptRoot "release_manifest.py"),
        "verify-archive",
        "--archive", $stagedArchivePath,
        "--sidecar", $stagedSidecarPath
    ) -Label "Post-export release archive verification" | Out-Null

    Copy-GuardedStreamToNewFile `
        -Source $archiveTrustStream `
        -Destination $OutputPath
    Copy-GuardedStreamToNewFile `
        -Source $sidecarTrustStream `
        -Destination $sidecarPath
    Copy-GuardedStreamToNewFile `
        -Source $textDigestTrustStream `
        -Destination $textDigestPath
    if ((Get-Sha256Hex -Path $OutputPath) -cne $archiveHash -or
        (Get-Sha256Hex -Path $sidecarPath) -cne $sidecarHash -or
        (Get-Sha256Hex -Path $textDigestPath) -cne $textDigestHash) {
        throw "Published release evidence does not match protected staged bytes."
    }
    Write-GuardedAsciiFile `
        -Path $bootstrapDigestPath `
        -Value "$bootstrapHash  $([System.IO.Path]::GetFileName($bootstrapPath))"
} finally {
    if ($null -ne $textDigestTrustStream) {
        $textDigestTrustStream.Dispose()
    }
    if ($null -ne $sidecarTrustStream) {
        $sidecarTrustStream.Dispose()
    }
    if ($null -ne $archiveTrustStream) {
        $archiveTrustStream.Dispose()
    }
    $env:TEMP = $originalProcessTemp
    $env:TMP = $originalProcessTmp
}

Write-Output "Prepared immutable candidate $candidateId from committed HEAD."
Write-Output "Archive: $OutputPath"
Write-Output "Archive SHA-256: $expectedArchiveHash"
Write-Output "SHA-256 evidence: $sidecarPath"
Write-Output "Portable digest: $textDigestPath"
Write-Output "Bootstrap: $bootstrapPath"
Write-Output "Bootstrap SHA-256: $bootstrapHash"
Write-Output "Bootstrap portable digest: $bootstrapDigestPath"
Write-Output "Protected build staging retained: $buildRoot"
