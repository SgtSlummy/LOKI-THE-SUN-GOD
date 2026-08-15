from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts" / "bootstrap_loki_services.ps1"
BUNDLE_PREPARER = ROOT / "scripts" / "prepare_loki_server_bundle.ps1"


def source() -> str:
    return BOOTSTRAP.read_text(encoding="utf-8")


def executable_body(script: str) -> str:
    return script[script.index("$canonicalBootstrapRoot =") :]


def powershell() -> str:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell is unavailable")
    return shell


def run_functions_harness(
    script_path: Path, function_names: list[str], body: str
) -> subprocess.CompletedProcess[str]:
    escaped_path = str(script_path).replace("'", "''")
    names = ", ".join(f"'{name}'" for name in function_names)
    script = f"""
$ErrorActionPreference = "Stop"
trap {{ [Console]::Error.WriteLine("HARNESS_ERROR: " + $_.Exception.Message); exit 1 }}
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    '{escaped_path}', [ref]$tokens, [ref]$errors
)
if (@($errors).Count -ne 0) {{ throw "PowerShell parse failed" }}
foreach ($requestedName in @({names})) {{
    $functionNode = $ast.Find({{
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -ceq $requestedName
    }}, $true)
    if ($null -eq $functionNode) {{ throw "function $requestedName not found" }}
    Invoke-Expression $functionNode.Extent.Text
}}
{body}
exit 0
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return subprocess.run(
        [powershell(), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_bootstrap_exposes_only_operator_evidence_and_reuse_parameters():
    script = source()
    match = re.search(r"(?ms)^param\(\s*(.*?)\s*\)\s*\n", script)
    assert match is not None
    names = re.findall(r"\]\$([A-Za-z][A-Za-z0-9]*)", match.group(1))
    assert names == [
        "ArchivePath",
        "ExpectedArchiveSha256",
        "SidecarPath",
        "PreserveExistingIdentity",
        "ReuseExistingVenv",
    ]
    assert match.group(1).count("[Parameter(Mandatory = $true)]") == 2


def test_bootstrap_requires_canonical_protected_self_before_input_use():
    script = source()
    body = executable_body(script)
    canonical = "C:\\ProgramData\\Loki\\bootstrap\\bootstrap_loki_services.ps1"
    assert canonical in script
    assert "Assert-CanonicalBootstrap" in script
    assert "Assert-ExactProtectedAcl" in script
    assert "[System.IO.FileAttributes]::ReparsePoint" in script
    assert '"S-1-5-18"' in script
    assert '"S-1-5-32-544"' in script
    assert ".GetOwner([Security.Principal.SecurityIdentifier]).Value" in script
    assert (
        'foreach ($ancestorPath in @("C:\\", "C:\\ProgramData", "C:\\ProgramData\\Loki", '
        "$bootstrapRoot, $expectedPath))"
    ) in script
    assert 'Assert-NoUnapprovedAncestorMutationAcl -Path "C:\\"' in script
    assert 'Assert-NoUnapprovedAncestorMutationAcl -Path "C:\\ProgramData"' in script
    assert 'Assert-ExactProtectedAcl -Path "C:\\ProgramData\\Loki" -Directory' in script
    assert body.index("Assert-CanonicalBootstrap -ScriptPath $PSCommandPath") < body.index(
        "$ArchivePath = [System.IO.Path]::GetFullPath($ArchivePath)"
    )


def test_bootstrap_requires_exact_protected_windows_powershell_51_before_all_trust_checks():
    script = source()
    host_call = script.index("\nAssert-TrustedWindowsPowerShellHost\n")
    assert host_call < script.index('$ErrorActionPreference = "Stop"')
    assert 'GetFullPath("C:\\Windows")' in script
    assert '"System32\\WindowsPowerShell\\v1.0"' in script
    assert '[System.IO.Path]::Combine($expectedPowerShellHome, "powershell.exe")' in script
    assert '$PSVersionTable.PSEdition -cne "Desktop"' in script
    assert "$PSVersionTable.PSVersion.Major -ne 5" in script
    assert "$PSVersionTable.PSVersion.Minor -ne 1" in script
    assert "[string]$currentProcess.MainModule.FileName" in script
    assert "[System.Environment]::GetCommandLineArgs()" in script
    assert '$commandLineArguments[1].Equals("-NoProfile"' in script
    assert '$commandLineArguments[2].Equals("-ExecutionPolicy"' in script
    assert '$commandLineArguments[3].Equals("Bypass"' in script
    assert '$commandLineArguments[4].Equals("-File"' in script
    assert "$invokedScript -ine [System.IO.Path]::GetFullPath($PSCommandPath)" in script
    assert "[System.IO.Directory]::GetAccessControl($trustedPath)" in script
    assert "[System.IO.File]::GetAccessControl($trustedPath)" in script
    assert "Import-TrustedSecurityModule" not in script
    assert "Get-Module" not in script
    assert "Import-Module" not in script


def test_bootstrap_requires_elevation_before_deployment_mutation():
    script = source()
    body = executable_body(script)
    assert "Assert-WindowsAdministrator" in script
    assert "WindowsBuiltInRole]::Administrator" in script
    assert body.index("Assert-WindowsAdministrator") < body.index(
        "$archiveTrustStream = [System.IO.File]::Open("
    )


def test_existing_managed_directories_are_asserted_not_acl_blessed():
    script = source()
    ensure = script[
        script.index("function Ensure-ProtectedDirectory") : script.index(
            "function Assert-CanonicalBootstrap"
        )
    ]
    assert "$created = $false" in ensure
    assert "if ($created)" in ensure
    assert "Assert-ExactProtectedAcl -Path $Path -Directory" in ensure


def test_bootstrap_locks_and_bounds_external_evidence_before_candidate_code():
    script = source()
    body = executable_body(script)
    archive_open = re.search(
        r"(?s)\$archiveTrustStream\s*=\s*\[System\.IO\.File\]::Open\(.*?"
        r"\[System\.IO\.FileShare\]::None\s*\)",
        body,
    )
    sidecar_open = re.search(
        r"(?s)\$sidecarTrustStream\s*=\s*\[System\.IO\.File\]::Open\(.*?"
        r"\[System\.IO\.FileShare\]::None\s*\)",
        body,
    )
    assert archive_open is not None
    assert sidecar_open is not None
    assert "$maximumSidecarBytes = 65536" in script
    assert "ExpectedArchiveSha256 must be exactly 64 hexadecimal characters" in script
    assert "Trusted archive SHA-256 mismatch. Candidate code was not invoked." in script
    assert "Trusted sidecar SHA-256 mismatch. Candidate code was not invoked." in script
    candidate_helper = body.index("$archiveManifestJson = Invoke-NativeText")
    assert body.index("Trusted archive SHA-256 mismatch") < candidate_helper
    assert body.index("Assert-ExactSidecar `") < candidate_helper
    bounded_read = body.index("$sidecar = Read-BoundedUtf8JsonStream")
    sidecar_hash = body.index("$sourceSidecarHash = Get-Sha256Hex")
    assert bounded_read < sidecar_hash


def test_bootstrap_copies_locked_evidence_to_protected_run_and_rehashes_both():
    script = source()
    assert '"run-" + [Guid]::NewGuid().ToString("N")' in script
    assert "Copy-LockedEvidenceFile -Source $archiveTrustStream" in script
    assert "Copy-LockedEvidenceFile -Source $sidecarTrustStream" in script
    assert "Protected archive copy SHA-256 mismatch" in script
    assert "Protected sidecar copy SHA-256 mismatch" in script
    assert "Set-ProtectedTreeAcl -Root $runRoot" in script
    assert script.index("Protected archive copy SHA-256 mismatch") < script.index("    Expand-TrustedBootstrapFiles `")


def test_bootstrap_extracts_only_fixed_trusted_helpers_before_archive_verification():
    script = source()
    assert "System.IO.Compression.ZipFile" in script
    assert '"scripts/release_manifest.py"' in script
    assert '"scripts/install_loki_services.ps1"' in script
    assert "Archive must contain exactly one case-sensitive bootstrap entry" in script
    assert '"-I", "-B", $trustedManifestHelper' in script
    assert "Invoke-NativeText -FilePath $pythonRuntime" in script
    assert '"verify-archive", "--archive", $protectedArchivePath, "--sidecar", $protectedSidecarPath' in script


def test_bootstrap_derives_exact_release_and_venv_paths_from_verified_candidate():
    script = source()
    assert 'if ($candidateId -cnotmatch "^loki-[0-9a-f]{12}$")' in script
    assert "[System.IO.Path]::Combine($releaseBase, $candidateId)" in script
    assert "[System.IO.Path]::Combine($venvBase, $candidateId)" in script
    assert "Final release root already exists; immutable deployment refused" in script
    assert (
        "Candidate venv already exists; pass -ReuseExistingVenv only for an operator-approved exact candidate" in script
    )


def test_bootstrap_stages_verifies_and_atomically_promotes_new_release():
    script = source()
    assert '".staging-" + $candidateId + "-" + [Guid]::NewGuid().ToString("N")' in script
    assert "[System.IO.Compression.ZipFile]::ExtractToDirectory(" in script
    assert "Expand-Archive" not in script
    assert "Set-ProtectedTreeAcl -Root $releaseStagingRoot" in script
    directory_verify = script.index('"verify-directory", "--root", $releaseStagingRoot')
    atomic_move = script.index("[System.IO.Directory]::Move($releaseStagingRoot, $releaseRoot)")
    assert directory_verify < atomic_move
    assert atomic_move < script.index('"verify-directory", "--root", $releaseRoot', atomic_move)


def test_reuse_mode_never_overwrites_release_and_is_forwarded_to_installer():
    script = source()
    assert "ReuseExistingVenv requires PreserveExistingIdentity" in script
    assert script.index("ReuseExistingVenv requires PreserveExistingIdentity") < script.index(
        "$ArchivePath = [System.IO.Path]::GetFullPath($ArchivePath)"
    )
    assert "$releaseTargetExists = [System.IO.Directory]::Exists($releaseRoot)" in script
    assert "$venvTargetExists = [System.IO.Directory]::Exists($venvPath)" in script
    assert "ReuseExistingVenv requires an existing exact release and venv pair" in script
    assert "Normal deployment requires absent release and venv targets" in script
    state_matrix = script.index("ReuseExistingVenv requires an existing exact release and venv pair")
    assert state_matrix < script.index("$releaseStagingRoot = [System.IO.Path]::Combine(")
    assert "if ($ReuseExistingVenv)" in script
    assert "Assert-ProtectedTreeAcl -Root $releaseRoot" in script
    assert "Assert-ProtectedTreeAcl -Root $venvPath" in script
    assert "Set-ProtectedTreeAcl -Root $releaseRoot" not in script
    assert "Set-ProtectedTreeAcl -Root $venvPath" not in script
    assert '"verify-directory", "--root", $releaseRoot' in script
    assert '$installerArguments += "-ReuseExistingVenv"' in script
    assert "Remove-Item -LiteralPath $releaseRoot" not in script


def test_reuse_binds_exact_release_manifest_bytes_to_trusted_archive():
    script = source()
    assert "function Get-TrustedArchiveManifestSha256" in script
    assert '"release-manifest.json"' in script
    assert "$trustedReleaseManifestSha256 = Get-TrustedArchiveManifestSha256" in script
    assert "$Label release manifest bytes do not match the trusted archive" in script
    reuse_acl = script.index("Assert-ProtectedTreeAcl -Root $releaseRoot")
    byte_binding = script.index("Assert-ReleaseManifestBytes `", reuse_acl)
    reuse_verify = script.index('"verify-directory", "--root", $releaseRoot', reuse_acl)
    assert reuse_acl < byte_binding < reuse_verify


def test_bootstrap_invokes_protected_staged_installer_without_secrets_or_start():
    script = source()
    assert "$powershell = Get-TrustedSystemExecutable" in script
    assert '"-TrustedPythonLauncher", $pythonLauncher' in script
    assert '"-File", $trustedServiceInstaller' in script
    assert 'Join-Path $releaseRoot "scripts\\install_loki_services.ps1"' not in script
    assert '"-ArchivePath", $protectedArchivePath' in script
    assert '"-SidecarPath", $protectedSidecarPath' in script
    assert '"-ExpectedArchiveSha256", $trustedArchiveHash' in script
    assert '"-TrustedPythonLauncher", $pythonLauncher' in script
    assert '"-TrustedPythonRuntime", $pythonRuntime' in script
    assert '"-TrustedGitExecutable", $trustedGitExecutable' in script
    assert '[System.IO.Path]::Combine($env:WINDIR, "py.exe")' in script
    assert 'GetFullPath("C:\\Program Files")' in script
    assert '"Python312\\python.exe"' in script
    assert '"Git\\cmd\\git.exe"' in script
    assert '$pythonInventory = Invoke-NativeText `' in script
    assert '-Arguments @("-0p")' in script
    assert 'Invoke-NativeText -FilePath $pythonRuntime -Arguments @(' in script
    assert '"-3.12"' not in script
    assert '"System32\\WindowsPowerShell\\v1.0\\powershell.exe"' in script
    for secret_name in (
        "DISCORD_TOKEN",
        "DISCORD_CLIENT_SECRET",
        "DASHBOARD_SECRET_KEY",
        "OPENAI_API_KEY",
    ):
        assert secret_name not in script
    assert "Start-Service" not in script
    assert '"start"' not in script


def test_bootstrap_rejects_ambient_path_launchers_and_write_capable_acl():
    script = source()
    assert "function Get-TrustedSystemExecutable" in script
    assert "function Assert-NoUnapprovedWriteAcl" in script
    assert "$env:WINDIR" in script
    assert 'GetFullPath("C:\\Windows")' in script
    assert '[System.IO.Path]::Combine($env:WINDIR, "py.exe")' in script
    assert "[Security.AccessControl.FileSystemRights]::Write" in script
    assert '"S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"' in script
    assert "Get-Command -Name $ExpectedPath" not in script
    assert "$pathsToValidate.Add($TrustedRoot)" in script
    assert "Assert-NoReparsePoint -Path $normalizedPath" in script
    assert "Assert-NoUnapprovedWriteAcl -Path $protectedPath" in script
    assert "Assert-NoUnapprovedAncestorMutationAcl -Path $volumeRoot" in script
    assert "[Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles" in script
    assert "0x50000000" in script
    assert "$pythonLauncherTrustStream = [System.IO.File]::Open(" in script
    assert "$pythonRuntimeTrustStream = [System.IO.File]::Open(" in script
    assert "$gitTrustStream = [System.IO.File]::Open(" in script
    assert "function Assert-TrustedMachineRuntimeTree" in script
    assert "Assert-TrustedMachineRuntimeTree `" in script
    assert "Assert-TrustedMachineRuntimeTree -Root $trustedGitRoot" in script
    assert "[System.IO.Directory]::EnumerateFileSystemEntries($directory)" in script
    assert '"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\Modules"' in script
    assert "$env:PSModulePath = $trustedPowerShellModuleRoot" in script
    assert "Assert-TrustedMachineRuntimeTree -Root $trustedPowerShellModuleRoot" in script
    assert "$powershellTrustStream = [System.IO.File]::Open(" in script
    assert script.count("$pythonLauncherTrustStream.Dispose()") == 1
    assert script.count("$pythonRuntimeTrustStream.Dispose()") == 1
    assert script.count("$gitTrustStream.Dispose()") == 1
    assert script.count("$powershellTrustStream.Dispose()") == 1
    assert "Get-Command py" not in script
    assert "Get-Command powershell.exe" not in script


def test_bootstrap_cleanup_is_confined_to_exact_run_staging():
    script = source()
    assert 'if ($runParent -ieq $canonicalBootstrapRoot -and $runLeaf -cmatch "^run-[0-9a-f]{32}$")' in script
    assert "[System.IO.Directory]::Delete($runRoot, $true)" in script
    assert "[System.IO.Directory]::Delete($releaseStagingRoot" not in script
    assert "[System.IO.Directory]::Delete($releaseRoot" not in script
    assert "[System.IO.Directory]::Delete($venvPath" not in script


def test_bootstrap_rejects_pwsh_before_canonical_or_archive_checks(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell 7 is unavailable")
    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(BOOTSTRAP),
            "-ArchivePath",
            str(tmp_path / "missing.zip"),
            "-ExpectedArchiveSha256",
            "0" * 64,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "requires Windows PowerShell 5.1" in output
    assert "must run only from the provisioned canonical path" not in output
    assert "Required deployment evidence file is missing" not in output


def test_bootstrap_rejects_same_session_invocation_before_canonical_checks(tmp_path):
    escaped_script = str(BOOTSTRAP).replace("'", "''")
    escaped_archive = str(tmp_path / "missing.zip").replace("'", "''")
    command = (
        f"& '{escaped_script}' -ArchivePath '{escaped_archive}' "
        f"-ExpectedArchiveSha256 '{'0' * 64}'"
    )
    result = subprocess.run(
        [powershell(), "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "requires exact powershell.exe -NoProfile ... -File invocation" in output
    assert "must run only from the provisioned canonical path" not in output


def test_bootstrap_rejects_abbreviated_command_mode_before_canonical_checks(tmp_path):
    escaped_script = str(BOOTSTRAP).replace("'", "''")
    escaped_archive = str(tmp_path / "missing.zip").replace("'", "''")
    command = (
        f"& '{escaped_script}' -ArchivePath '{escaped_archive}' "
        f"-ExpectedArchiveSha256 '{'0' * 64}'; #"
    )
    result = subprocess.run(
        [powershell(), "-NoProfile", "-Com", command, "-File", str(BOOTSTRAP)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "requires exact powershell.exe -NoProfile ... -File invocation" in output
    assert "must run only from the provisioned canonical path" not in output


def test_bootstrap_host_gate_rejects_abbreviated_encoded_mode():
    escaped_script = str(BOOTSTRAP).replace("'", "''")
    command = f"""
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    '{escaped_script}', [ref]$null, [ref]$null
)
$node = $ast.Find({{
    param($candidate)
    $candidate -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $candidate.Name -ceq 'Assert-TrustedWindowsPowerShellHost'
}}, $true)
Invoke-Expression $node.Extent.Text
Assert-TrustedWindowsPowerShellHost
"""
    encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [powershell(), "-NoProfile", "-Encod", encoded],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "requires exact powershell.exe -NoProfile ... -File invocation" in output


def test_bootstrap_rejects_noprofile_token_after_file_as_script_value(tmp_path):
    result = subprocess.run(
        [
            powershell(),
            "-NonInteractive",
            "-File",
            str(BOOTSTRAP),
            "-ArchivePath",
            "-NoProfile",
            "-ExpectedArchiveSha256",
            "0" * 64,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "requires exact powershell.exe -NoProfile ... -File invocation" in output
    assert "must run only from the provisioned canonical path" not in output


def test_trusted_system_executable_accepts_canonical_windows_powershell():
    result = run_functions_harness(
        BOOTSTRAP,
        [
            "Assert-NoReparsePoint",
            "Assert-NoUnapprovedWriteAcl",
            "Assert-NoUnapprovedAncestorMutationAcl",
            "Get-TrustedMachineExecutable",
            "Get-TrustedSystemExecutable",
        ],
        r"""
$windowsRoot = [System.IO.Path]::GetFullPath("C:\Windows")
$expected = Join-Path $windowsRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$actual = Get-TrustedSystemExecutable -ExpectedPath $expected -WindowsRoot $windowsRoot
if ([System.IO.Path]::GetFullPath($actual) -ine [System.IO.Path]::GetFullPath($expected)) {
    throw "trusted PowerShell path mismatch"
}
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_stock_programdata_acl_blocks_swap_rights_without_rejecting_create_only_aces():
    result = run_functions_harness(
        BOOTSTRAP,
        ["Assert-NoUnapprovedAncestorMutationAcl"],
        'Assert-NoUnapprovedAncestorMutationAcl -Path "C:\\ProgramData"',
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_noncanonical_repo_copy_fails_before_archive_access(tmp_path):
    archive = tmp_path / "missing.zip"
    result = subprocess.run(
        [
            powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BOOTSTRAP),
            "-ArchivePath",
            str(archive),
            "-ExpectedArchiveSha256",
            "0" * 64,
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode != 0
    output = result.stdout + result.stderr
    assert "must run only from the provisioned canonical path" in output
    assert "requires exact powershell.exe -NoProfile ... -File invocation" not in output
    assert "Required deployment evidence file is missing" not in output


def test_bootstrap_parses_in_windows_powershell():
    path = str(BOOTSTRAP).replace("'", "''")
    command = (
        "$tokens=$null;$errors=$null;"
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$tokens,[ref]$errors);"
        "if($errors.Count -ne 0){$errors|ForEach-Object{$_.Message};exit 1}"
    )
    result = subprocess.run(
        [powershell(), "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_bundle_verification_and_bootstrap_export_share_locked_archive_bytes():
    script = BUNDLE_PREPARER.read_text(encoding="utf-8")
    assert "LOKI bundle preparation requires Windows PowerShell 5.1" in script
    assert "requires exact powershell.exe -NoProfile ... -File invocation" in script
    assert '$preparerCommandLine[1].Equals("-NoProfile"' in script
    assert '$preparerCommandLine[2].Equals("-ExecutionPolicy"' in script
    assert '$preparerCommandLine[3].Equals("Bypass"' in script
    assert '$preparerCommandLine[4].Equals("-File"' in script
    assert "$buildEvidence = $result | ConvertFrom-Json" in script
    assert "Built archive SHA-256 changed before locked verification" in script
    assert "Build and locked archive identity mismatch" in script
    assert "$protectedBuildParent = Ensure-ProtectedBuildParent" in script
    assert "$buildRoot = New-ProtectedBuildDirectory -Parent $protectedBuildParent" in script
    assert "$trustedScratchRoot = New-ProtectedBuildDirectory -Parent $buildRoot" in script
    assert "$env:TEMP = $trustedScratchRoot" in script
    assert "$env:TMP = $trustedScratchRoot" in script
    assert "$env:TEMP = $originalProcessTemp" in script
    assert "$env:TMP = $originalProcessTmp" in script
    assert script.index("$env:TEMP = $trustedScratchRoot") < script.index(
        "$archiveTrustStream = Open-GuardedEvidenceReadStream"
    )
    assert 'GetFullPath("C:\\ProgramData\\LokiBundleStaging")' in script
    assert "Assert-ExactProtectedBuildDirectory -Path $buildRoot" in script
    assert "[System.IO.Directory]::Delete($buildRoot" not in script
    assert 'Write-Output "Protected build staging retained: $buildRoot"' in script
    assert "$archiveTrustStream = Open-GuardedEvidenceReadStream -Path $stagedArchivePath" in script
    assert "$sidecarTrustStream = Open-GuardedEvidenceReadStream -Path $stagedSidecarPath" in script
    assert "$textDigestTrustStream = Open-GuardedEvidenceReadStream" in script
    assert "OpenExistingForRead" in script
    assert "FileFlagOpenReparsePoint = 0x00200000" in script
    assert "$trustedArchiveStream = Copy-LockedEvidenceFile" not in script
    assert "$trustedSidecarStream = Copy-LockedEvidenceFile" not in script
    assert '"--archive", $stagedArchivePath' in script
    assert '"--sidecar", $stagedSidecarPath' in script
    assert "-Archive $stagedArchivePath" in script
    assert "$bootstrapHash = Export-TrustedBootstrap" in script
    assert "function Open-GuardedOutputStream" in script
    assert "FileFlagOpenReparsePoint = 0x00200000" in script
    assert "GetFileInformationByHandleEx" in script
    assert "GetFinalPathNameByHandle" in script
    assert "[System.IO.FileMode]::CreateNew" in script
    assert "Write-GuardedAsciiFile `" in script
    assert "-Force never overwrites trust evidence" in script
    assert '$arguments += "--force"' not in script
    assert "Copy-GuardedStreamToNewFile `" in script
    assert 'Write-Output "Archive SHA-256: $expectedArchiveHash"' in script
    assert "Set-Content -LiteralPath $bootstrapDigestPath" not in script
    assert script.count("Get-Sha256Hex -Stream $archiveTrustStream") >= 2
    assert "Post-export locked archive SHA-256 mismatch" in script
    assert script.count("$archiveTrustStream.Dispose()") == 1
    assert script.count("$sidecarTrustStream.Dispose()") == 1


def test_bundle_preparer_rejects_pwsh_before_repository_or_output_access(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell 7 is unavailable")
    output = tmp_path / "candidate.zip"
    result = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(BUNDLE_PREPARER),
            "-OutputPath",
            str(output),
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0
    assert "requires Windows PowerShell 5.1" in result.stdout + result.stderr
    assert not output.exists()


def test_bundle_preparer_rejects_late_noprofile_script_value():
    result = subprocess.run(
        [
            powershell(),
            "-NonInteractive",
            "-File",
            str(BUNDLE_PREPARER),
            "-OutputPath",
            "-NoProfile",
        ],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode != 0
    assert (
        "requires exact powershell.exe -NoProfile ... -File invocation"
        in result.stdout + result.stderr
    )


def test_bundle_read_lock_blocks_replacement_and_allows_zip_export(tmp_path):
    archive = tmp_path / "candidate.zip"
    bootstrap_bytes = b"Write-Output 'trusted bootstrap'\r\n"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("scripts/bootstrap_loki_services.ps1", bootstrap_bytes)
    destination = tmp_path / "bootstrap.ps1"
    archive_ps = str(archive).replace("'", "''")
    destination_ps = str(destination).replace("'", "''")
    result = run_functions_harness(
        BUNDLE_PREPARER,
        [
            "Initialize-GuardedOutputNativeApi",
            "Assert-NoReparsePathAncestors",
            "Open-GuardedEvidenceReadStream",
            "Open-GuardedOutputStream",
            "Get-Sha256Hex",
            "Export-TrustedBootstrap",
        ],
        rf"""
$archive = '{archive_ps}'
$destination = '{destination_ps}'
$archiveLock = Open-GuardedEvidenceReadStream -Path $archive
try {{
    $writeHandle = $null
    try {{
        $writeHandle = [System.IO.File]::Open(
            $archive,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::ReadWrite
        )
    }} catch [System.IO.IOException] {{
    }}
    if ($null -ne $writeHandle) {{
        $writeHandle.Dispose()
        throw "read lock allowed write access"
    }}
    $deleteBlocked = $false
    try {{
        [System.IO.File]::Delete($archive)
    }} catch [System.IO.IOException] {{
        $deleteBlocked = $true
    }}
    if (-not $deleteBlocked) {{ throw "read lock allowed deletion" }}
    $before = Get-Sha256Hex -Stream $archiveLock
    $bootstrapHash = Export-TrustedBootstrap -Archive $archive -Destination $destination
    $after = Get-Sha256Hex -Stream $archiveLock
    if ($before -cne $after) {{ throw "locked archive changed" }}
    Write-Output $bootstrapHash
}} finally {{
    $archiveLock.Dispose()
}}
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert hashlib.sha256(bootstrap_bytes).hexdigest() in result.stdout


def test_protected_build_directory_creation_works_in_windows_powershell_51(tmp_path):
    parent = tmp_path / "protected-build-parent"
    parent_ps = str(parent).replace("'", "''")
    result = run_functions_harness(
        BUNDLE_PREPARER,
        [
            "Get-ProtectedBuildDirectorySecurity",
            "Assert-ExactProtectedBuildDirectory",
            "New-ProtectedBuildDirectory",
        ],
        rf"""
$parent = '{parent_ps}'
$security = Get-ProtectedBuildDirectorySecurity
[void][System.IO.Directory]::CreateDirectory($parent, $security)
$child = New-ProtectedBuildDirectory -Parent $parent
Assert-ExactProtectedBuildDirectory -Path $child
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_bundle_staging_parent_accepts_stock_programdata_create_only_acl():
    result = run_functions_harness(
        BUNDLE_PREPARER,
        ["Assert-NoReparsePathAncestors"],
        'Assert-NoReparsePathAncestors -Directory "C:\\ProgramData" -RequireMutationProtection',
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_bundle_evidence_lock_rejects_reparse_leaf(tmp_path):
    victim = tmp_path / "victim.zip"
    victim.write_bytes(b"victim")
    evidence = tmp_path / "candidate.zip"
    try:
        evidence.symlink_to(victim)
    except OSError as error:
        pytest.skip(f"Windows symlink creation unavailable: {error}")
    evidence_ps = str(evidence).replace("'", "''")
    result = run_functions_harness(
        BUNDLE_PREPARER,
        [
            "Initialize-GuardedOutputNativeApi",
            "Assert-NoReparsePathAncestors",
            "Open-GuardedEvidenceReadStream",
        ],
        rf"$stream = Open-GuardedEvidenceReadStream -Path '{evidence_ps}'; $stream.Dispose()",
    )
    assert result.returncode != 0
    assert "Guarded file must not be a reparse point" in result.stderr
    assert victim.read_bytes() == b"victim"


def test_guarded_output_refuses_nonforce_collision(tmp_path):
    destination = tmp_path / "bootstrap.ps1.sha256"
    destination.write_text("sentinel", encoding="ascii")
    destination_ps = str(destination).replace("'", "''")
    result = run_functions_harness(
        BUNDLE_PREPARER,
        [
            "Initialize-GuardedOutputNativeApi",
            "Assert-NoReparsePathAncestors",
            "Open-GuardedOutputStream",
            "Write-GuardedAsciiFile",
        ],
        rf"Write-GuardedAsciiFile -Path '{destination_ps}' -Value 'replacement'",
    )
    assert result.returncode != 0
    assert "Release artifact already exists" in result.stderr
    assert destination.read_text(encoding="ascii") == "sentinel"


def test_guarded_force_refuses_normal_existing_leaf(tmp_path):
    archive = tmp_path / "candidate.zip"
    bootstrap_bytes = b"Write-Output 'replacement'\r\n"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("scripts/bootstrap_loki_services.ps1", bootstrap_bytes)
    destination = tmp_path / "bootstrap.ps1"
    destination.write_bytes(b"sentinel")
    archive_ps = str(archive).replace("'", "''")
    destination_ps = str(destination).replace("'", "''")
    result = run_functions_harness(
        BUNDLE_PREPARER,
        [
            "Initialize-GuardedOutputNativeApi",
            "Assert-NoReparsePathAncestors",
            "Open-GuardedOutputStream",
            "Get-Sha256Hex",
            "Export-TrustedBootstrap",
        ],
        rf"Export-TrustedBootstrap -Archive '{archive_ps}' -Destination '{destination_ps}' -Overwrite",
    )
    assert result.returncode != 0
    assert "Release artifact already exists" in result.stderr
    assert destination.read_bytes() == b"sentinel"


def test_guarded_force_refuses_hard_link_without_truncating_target(tmp_path):
    archive = tmp_path / "candidate.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("scripts/bootstrap_loki_services.ps1", b"replacement")
    victim = tmp_path / "victim.ps1"
    victim.write_bytes(b"victim")
    destination = tmp_path / "bootstrap.ps1"
    os.link(victim, destination)
    archive_ps = str(archive).replace("'", "''")
    destination_ps = str(destination).replace("'", "''")
    result = run_functions_harness(
        BUNDLE_PREPARER,
        [
            "Initialize-GuardedOutputNativeApi",
            "Assert-NoReparsePathAncestors",
            "Open-GuardedOutputStream",
            "Get-Sha256Hex",
            "Export-TrustedBootstrap",
        ],
        rf"Export-TrustedBootstrap -Archive '{archive_ps}' -Destination '{destination_ps}' -Overwrite",
    )
    assert result.returncode != 0
    assert "Release artifact already exists" in result.stderr
    assert victim.read_bytes() == b"victim"


def test_guarded_force_rejects_reparse_destination(tmp_path):
    archive = tmp_path / "candidate.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("scripts/bootstrap_loki_services.ps1", b"replacement")
    victim = tmp_path / "victim.ps1"
    victim.write_bytes(b"victim")
    destination = tmp_path / "bootstrap.ps1"
    try:
        destination.symlink_to(victim)
    except OSError as error:
        pytest.skip(f"Windows symlink creation unavailable: {error}")
    archive_ps = str(archive).replace("'", "''")
    destination_ps = str(destination).replace("'", "''")
    result = run_functions_harness(
        BUNDLE_PREPARER,
        [
            "Initialize-GuardedOutputNativeApi",
            "Assert-NoReparsePathAncestors",
            "Open-GuardedOutputStream",
            "Get-Sha256Hex",
            "Export-TrustedBootstrap",
        ],
        rf"Export-TrustedBootstrap -Archive '{archive_ps}' -Destination '{destination_ps}' -Overwrite",
    )
    assert result.returncode != 0
    assert "Release artifact already exists" in result.stderr
    assert victim.read_bytes() == b"victim"
