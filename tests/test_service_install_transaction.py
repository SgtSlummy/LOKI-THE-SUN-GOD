from __future__ import annotations

import base64
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_loki_services.ps1"
VERIFIER = ROOT / "scripts" / "verify_loki_services.ps1"


def powershell() -> str:
    shell = shutil.which("powershell") or shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell is unavailable")
    return shell


def run_function_harness(
    function_name: str, body: str, *, source: Path = INSTALLER
) -> subprocess.CompletedProcess[str]:
    installer_path = str(source).replace("'", "''")
    script = f"""
$ErrorActionPreference = "Stop"
trap {{ [Console]::Error.WriteLine("HARNESS_ERROR: " + $_.Exception.Message); exit 1 }}
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    '{installer_path}', [ref]$tokens, [ref]$errors
)
if (@($errors).Count -ne 0) {{ throw "installer parse failed" }}
$functionNode = $ast.Find({{
    param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $node.Name -ceq '{function_name}'
}}, $true)
if ($null -eq $functionNode) {{ throw "function {function_name} not found" }}
Invoke-Expression $functionNode.Extent.Text
{body}
exit 0
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return subprocess.run(
        [powershell(), "-NoProfile", "-EncodedCommand", encoded],
        check=False,
        capture_output=True,
        text=True,
    )


def run_functions_harness(
    functions: list[tuple[Path, str]], body: str
) -> subprocess.CompletedProcess[str]:
    requests = ",\n".join(
        "[pscustomobject]@{ Path = '"
        + str(source).replace("'", "''")
        + "'; Name = '"
        + name.replace("'", "''")
        + "' }"
        for source, name in functions
    )
    script = f"""
$ErrorActionPreference = "Stop"
trap {{ [Console]::Error.WriteLine("HARNESS_ERROR: " + $_.Exception.Message); exit 1 }}
$requests = @({requests})
foreach ($request in $requests) {{
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $request.Path, [ref]$tokens, [ref]$errors
    )
    if (@($errors).Count -ne 0) {{ throw "PowerShell parse failed" }}
    $requestedName = [string]$request.Name
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
        [powershell(), "-NoProfile", "-EncodedCommand", encoded],
        check=False,
        capture_output=True,
        text=True,
    )


def test_credential_validation_precedes_every_service_mutation():
    script = INSTALLER.read_text(encoding="utf-8")
    main_prompt = script.index("$credential = Get-ValidatedServiceCredential")
    transaction_marker = script.index("# BEGIN SERVICE MUTATION TRANSACTION")
    transaction_call = script.index(
        "Invoke-ServiceMutationTransaction -Snapshots", transaction_marker
    )

    assert main_prompt < transaction_marker < transaction_call
    assert script.index("Get-Credential", script.index("function Get-ValidatedServiceCredential")) < main_prompt
    assert "LogonUserW" in script
    assert "LOGON32_LOGON_SERVICE" in script
    assert "PtrToStringBSTR" not in script


def test_transaction_removes_new_services_when_second_install_fails():
    result = run_function_harness(
        "Invoke-ServiceMutationTransaction",
        r"""
$present = @{}
$events = New-Object System.Collections.Generic.List[string]
$snapshots = @(
    [pscustomobject]@{ Name = "one"; Exists = $false },
    [pscustomobject]@{ Name = "two"; Exists = $false }
)
try {
    Invoke-ServiceMutationTransaction -Snapshots $snapshots `
        -Mutate {
            $present["one"] = $true
            $events.Add("installed:one")
            $present["two"] = $true
            throw "second install failed"
        } `
        -TestExists { param($name) return [bool]$present[$name] } `
        -RemoveNew { param($name) $events.Add("removed:$name"); $present.Remove($name) } `
        -RestoreExisting { param($snapshot) throw "unexpected restore" } `
        -DisableResidual { param($name) $events.Add("disabled:$name") }
    throw "transaction unexpectedly succeeded"
} catch {
    if ($_.Exception.Message -eq "transaction unexpectedly succeeded") { throw }
}
if ($present.Count -ne 0) { throw "new service survived rollback" }
if ($events -notcontains "removed:one" -or $events -notcontains "removed:two") {
    throw "new service removal evidence missing"
}
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_transaction_restores_existing_services_after_mid_install_failure():
    result = run_function_harness(
        "Invoke-ServiceMutationTransaction",
        r"""
$events = New-Object System.Collections.Generic.List[string]
$snapshots = @(
    [pscustomobject]@{ Name = "one"; Exists = $true; Token = "before-one" },
    [pscustomobject]@{ Name = "two"; Exists = $true; Token = "before-two" }
)
try {
    Invoke-ServiceMutationTransaction -Snapshots $snapshots `
        -Mutate { throw "mid-install failure" } `
        -TestExists { param($name) return $true } `
        -RemoveNew { param($name) throw "unexpected remove" } `
        -RestoreExisting { param($snapshot) $events.Add("restored:$($snapshot.Token)") } `
        -DisableResidual { param($name) $events.Add("disabled:$name") }
    throw "transaction unexpectedly succeeded"
} catch {
    if ($_.Exception.Message -eq "transaction unexpectedly succeeded") { throw }
}
if ($events -notcontains "restored:before-one" -or $events -notcontains "restored:before-two") {
    throw "existing service restoration evidence missing"
}
if (@($events | Where-Object { $_ -like "disabled:*" }).Count -ne 0) {
    throw "healthy rollback was disabled"
}
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_transaction_disables_residual_service_when_restore_fails():
    result = run_function_harness(
        "Invoke-ServiceMutationTransaction",
        r"""
$events = New-Object System.Collections.Generic.List[string]
$snapshots = @([pscustomobject]@{ Name = "one"; Exists = $true })
$message = ""
try {
    Invoke-ServiceMutationTransaction -Snapshots $snapshots `
        -Mutate { throw "mutation failed" } `
        -TestExists { param($name) return $true } `
        -RemoveNew { param($name) throw "unexpected remove" } `
        -RestoreExisting { param($snapshot) throw "restore failed" } `
        -DisableResidual { param($name) $events.Add("disabled:$name") }
} catch {
    $message = $_.Exception.Message
}
if ($events -notcontains "disabled:one") { throw "residual service was not disabled" }
if ($message -notmatch "rollback incomplete" -or $message -notmatch "one") {
    throw "rollback residue was not reported"
}
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_installer_uses_disabled_then_exact_identity_then_delayed_auto():
    script = INSTALLER.read_text(encoding="utf-8")
    transaction = script[script.index("# BEGIN SERVICE MUTATION TRANSACTION") :]

    disabled = transaction.index('"--startup", "disabled"')
    identity = transaction.index("Set-ServiceIdentitySecurely")
    exact_verify = transaction.index("Assert-InstalledServiceExact")
    delayed = transaction.index('"start=", "delayed-auto"')
    assert disabled < identity < exact_verify < delayed
    assert "ChangeServiceConfigW" in script
    assert "StartPassword" not in script
    assert '"--password"' not in script


def test_service_logon_right_is_granted_before_validation_and_rollback_scoped():
    script = INSTALLER.read_text(encoding="utf-8")
    for native_api in (
        "LsaOpenPolicy",
        "LsaAddAccountRights",
        "LsaRemoveAccountRights",
        "LookupAccountNameW",
        "SeServiceLogonRight",
    ):
        assert native_api in script

    main = script[script.index("$serviceLogonRightAdded = $false") :]
    grant = main.index("Grant-ServiceLogonRight")
    validate = main.index("$credential = Get-ValidatedServiceCredential")
    mutation = main.index("# BEGIN SERVICE MUTATION TRANSACTION")
    commit = main.index("$serviceLogonRightCommitted = $true")
    cleanup = main.index("Revoke-ServiceLogonRight", commit)
    assert grant < validate < mutation < commit < cleanup
    assert "service_logon_right_preexisting" in script

    compiled = run_function_harness(
        "Initialize-NativeServiceApi",
        "Initialize-NativeServiceApi\n"
        "if ($null -eq ('Loki.ServiceNativeApi' -as [type])) "
        "{ throw 'native API missing' }",
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr


def test_exact_service_registry_and_candidate_bound_rollback_evidence():
    installer = INSTALLER.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")

    for script in (installer, verifier):
        assert "Get-ExpectedPythonClass" in script
        assert "Assert-ExactServiceEnvironment" in script
        assert "LokiInstallId" in script
        assert "PythonClass.IndexOf" not in script
        assert "-inotcontains" not in script

    assert 'schema = "loki-service-rollback/v2"' in installer
    assert '-Status "installed"' in installer
    assert "RegistryValues" in installer
    assert "FailureActionsOnNonCrashFailures" in installer
    assert "FailureActions" in installer
    assert "service-config-$installId.json" in verifier
    assert "Sort-Object LastWriteTimeUtc" not in verifier
    assert 'status -cne "installed"' in verifier
    for field in ("candidate_id", "incoming_release_root", "incoming_venv_path"):
        assert field in verifier


def test_exact_service_environment_rejects_extras_duplicates_and_wrong_paths():
    result = run_function_harness(
        "Assert-ExactServiceEnvironment",
        r"""
$expected = @(
    "LOKI_APP_ROOT=C:\ProgramData\Loki\releases\loki-a",
    "LOKI_ENV_PATH=C:\ProgramData\Loki\config\lokithesungod.env",
    "LOKI_DB_PATH=C:\ProgramData\Loki\data\bot.db",
    "PYTHONPYCACHEPREFIX=C:\ProgramData\Loki\cache\Bot",
    "LOKI_LOCAL_ALLOW_FULL=true",
    "RELAY_ENABLED=false",
    "LOKI_ENABLE_SLASH_SYNC=false"
)
Assert-ExactServiceEnvironment -Name "Bot" -Actual $expected -Expected $expected
$badSets = @(
    @($expected + "PYTHONPATH=C:\attacker"),
    @($expected[1..6] + "loki_app_root=C:\attacker"),
    @($expected[0..2] + "PYTHONPYCACHEPREFIX=C:\attacker" + $expected[4..6])
)
foreach ($bad in $badSets) {
    $rejected = $false
    try {
        Assert-ExactServiceEnvironment -Name "Bot" -Actual $bad -Expected $expected
    } catch {
        $rejected = $true
    }
    if (-not $rejected) { throw "unsafe environment set was accepted" }
}
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_recovery_exercise_threads_candidate_install_id():
    verifier = VERIFIER.read_text(encoding="utf-8")
    start = verifier.index("function Wait-ForRecoveredChild")
    end = verifier.index("Assert-WindowsAdministrator", start)
    wait_function = verifier[start:end]

    assert "[string]$InstallId" in wait_function
    assert "-InstallId $InstallId" in wait_function
    assert verifier.count("-InstallId $installId") >= 4


def test_existing_snapshot_must_be_nonsecret_and_rollback_acl_is_hardened():
    installer = INSTALLER.read_text(encoding="utf-8")
    assert "Assert-SnapshotContainsOnlyApprovedNonsecretState" in installer
    assert "Protect-RollbackEvidenceAcl" in installer
    assert "SetAccessRuleProtection" in installer
    assert '"S-1-5-18"' in installer
    assert '"S-1-5-32-544"' in installer
    assert "Assert-SnapshotContainsOnlyApprovedNonsecretState -Snapshot" in installer
    assert "Protect-RollbackEvidenceAcl -Path" in installer


def test_restore_uses_scm_api_and_verifies_every_touched_cached_field():
    installer = INSTALLER.read_text(encoding="utf-8")
    assert "RestoreCoreConfiguration" in installer
    assert "ChangeServiceConfig2W" in installer
    restored = installer[
        installer.index("function Assert-ServiceSnapshotRestored") : installer.index(
            "function Restore-ServiceSnapshot"
        )
    ]
    for field in (
        "ServiceType",
        "ErrorControl",
        "Description",
        "ServiceDependencies",
    ):
        assert field in restored


def test_recovery_parser_rejects_extra_or_wrong_actions():
    result = run_function_harness(
        "Assert-RecoveryTextExact",
        r"""
$exact = @"
RESET_PERIOD (in seconds)    : 86400
REBOOT_MESSAGE               :
COMMAND_LINE                 :
FAILURE_ACTIONS              : RESTART -- Delay = 60000 milliseconds.
                               RESTART -- Delay = 120000 milliseconds.
                               NONE -- Delay = 0 milliseconds.
"@
Assert-RecoveryTextExact -Name "Bot" -Text $exact
$bad = @(
    ($exact + "`nRESTART -- Delay = 1 milliseconds."),
    ($exact -replace "NONE -- Delay = 0", "REBOOT -- Delay = 0"),
    ($exact -replace "86400", "86401"),
    ($exact -replace "COMMAND_LINE                 :", "COMMAND_LINE                 : C:\\attacker.exe"),
    ($exact -replace "REBOOT_MESSAGE               :", "REBOOT_MESSAGE               : unsafe")
)
foreach ($value in $bad) {
    $rejected = $false
    try { Assert-RecoveryTextExact -Name "Bot" -Text $value } catch { $rejected = $true }
    if (-not $rejected) { throw "unsafe recovery actions were accepted" }
}
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_verifier_uses_same_exact_recovery_parser():
    verifier = VERIFIER.read_text(encoding="utf-8")
    recovery = verifier[
        verifier.index("function Assert-RecoveryPolicy") : verifier.index(
            "function Get-ExpectedPythonClass"
        )
    ]
    assert "Assert-RecoveryTextExact" in recovery
    assert "FAILURE_ACTIONS_ON_NONCRASH_FAILURES" in recovery
    assert 'foreach ($required in @("86400"' not in recovery

    result = run_function_harness(
        "Assert-RecoveryTextExact",
        r"""
$extra = @"
RESET_PERIOD (in seconds)    : 86400
REBOOT_MESSAGE               :
COMMAND_LINE                 :
FAILURE_ACTIONS              : RESTART -- Delay = 60000 milliseconds.
                               RESTART -- Delay = 120000 milliseconds.
                               NONE -- Delay = 0 milliseconds.
                               REBOOT -- Delay = 1 milliseconds.
"@
$rejected = $false
try { Assert-RecoveryTextExact -Name "Bot" -Text $extra } catch { $rejected = $true }
if (-not $rejected) { throw "verifier accepted an extra recovery action" }
""",
        source=VERIFIER,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("source", [INSTALLER, VERIFIER])
def test_python_class_path_is_case_insensitive_but_class_name_is_exact(source):
    text = source.read_text(encoding="utf-8")
    assert "function Assert-ExactPythonClass" in text
    result = run_function_harness(
        "Assert-ExactPythonClass",
        r"""
Assert-ExactPythonClass -Name "Bot" `
    -Actual "C:\LOKI\scripts\LOKI_BOT_SERVICE.LokiBotService" `
    -Expected "c:\loki\scripts\loki_bot_service.LokiBotService"
$rejected = $false
try {
    Assert-ExactPythonClass -Name "Bot" `
        -Actual "C:\LOKI\scripts\loki_bot_service.lokibotservice" `
        -Expected "c:\loki\scripts\loki_bot_service.LokiBotService"
} catch {
    $rejected = $true
}
if (-not $rejected) { throw "case-mismatched Python class was accepted" }
""",
        source=source,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_existing_rollback_target_requires_matching_verified_artifacts():
    installer = INSTALLER.read_text(encoding="utf-8")
    assert "function Assert-RollbackArtifacts" in installer
    rollback = installer[
        installer.index("function Assert-RollbackArtifacts") : installer.index(
            "function Assert-ServiceSnapshotSafeForMutation"
        )
    ]
    for required in (
        "release-manifest.json",
        "pythonservice.exe",
        "Scripts\\python.exe",
        "loki_bot_service.py",
        "loki_dashboard_service.py",
        "local_loki_runtime.py",
        "dashboard_app.py",
        "RollbackReleaseRoot",
        "RollbackVenvPath",
    ):
        assert required in rollback
    assert "Assert-RollbackReleaseManifest" in installer
    assert '"verify-directory", "--root", $rollbackRelease' in installer
    assert "Invoke-NativeText -FilePath $rollbackPython" not in installer
    assert "Rollback Python validation" not in installer


def test_rollback_snapshot_rejects_unapproved_persisted_strings():
    installer = INSTALLER.read_text(encoding="utf-8")
    approval = installer[
        installer.index("function Assert-SnapshotContainsOnlyApprovedNonsecretState") : installer.index(
            "function Assert-RollbackArtifacts"
        )
    ]
    for value_name in ('["Description"]', '["DependOnService"]', '["LokiInstallId"]'):
        assert value_name in approval
    assert "approved nonsecret" in approval


def test_verifier_requires_protected_complete_rollback_evidence():
    verifier = VERIFIER.read_text(encoding="utf-8")
    assert "function Assert-ProtectedRollbackAcl" in verifier
    evidence = verifier[verifier.index('$rollbackRoot = Join-Path $env:ProgramData "Loki\\rollback"') :]
    assert "Assert-ProtectedRollbackAcl -Path $rollbackRoot -Directory" in evidence
    assert "Assert-ProtectedRollbackAcl -Path $rollbackEvidencePath" in evidence
    installer = INSTALLER.read_text(encoding="utf-8")
    protect = installer[
        installer.index("function Protect-RollbackEvidenceAcl") : installer.index(
            "function Save-RollbackEvidence"
        )
    ]
    verify_acl = verifier[
        verifier.index("function Assert-ProtectedRollbackAcl") : verifier.index(
            "function Assert-ExactPropertyNames"
        )
    ]
    assert "S-1-5-18" in protect and "S-1-5-32-544" in protect
    assert "S-1-5-18" in verify_acl and "S-1-5-32-544" in verify_acl
    assert "SetOwner" in protect
    assert "GetOwner" in verify_acl
    assert "ReparsePoint" in protect
    assert "ReparsePoint" in verify_acl
    assert "currentSid" not in protect
    assert "currentSid" not in verify_acl
    for field in (
        "Description",
        "DependOnService",
        "Type",
        "ErrorControl",
        "LokiInstallId",
        "ServiceType",
        "ServiceDependencies",
        "RollbackReleaseRoot",
        "RollbackVenvPath",
    ):
        assert field in evidence


def test_installer_and_verifier_cannot_bypass_commissioned_paths():
    installer = INSTALLER.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")
    assert "AllowNonStandardReleaseRoot" not in installer
    assert '"http://127.0.0.1:9101/healthz"' in verifier
    assert '"http://127.0.0.1:5000/healthz"' in verifier
    assert "Health URLs must be exact commissioned loopback endpoints" in verifier


def test_programdata_payloads_are_acl_hardened_before_python_execution():
    installer = INSTALLER.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")
    assert "function Protect-AdministratorTree" in installer
    assert installer.count("Protect-AdministratorTree -Root $lokiRoot") >= 3
    first_hardening = installer.index("Protect-AdministratorTree -Root $lokiRoot")
    candidate_python = installer.index("$runtimeVersion = Invoke-NativeText")
    assert first_hardening < candidate_python
    for managed in ("releases", "venvs", "config", "logs", "data", "cache"):
        assert f'(Join-Path $lokiRoot "{managed}")' in installer

    assert "function Assert-AdministratorTreeAcl" in verifier
    tree_check = verifier.index("Assert-AdministratorTreeAcl -Root $lokiRoot")
    python_check = verifier.index("$pythonVersion = Invoke-NativeText")
    assert tree_check < python_check
    assert "Assert-ProtectedRollbackAcl -Path $Path -Directory:$Directory" in verifier
    assert (
        "Assert-AdministratorOnlyPathAcl -Path $directory -Directory "
        "-RequireProtected:$isRoot"
    ) in verifier
    assert "Commissioned LOKI path ACL must contain exactly two effective rules" in verifier
    assert "Commissioned LOKI directory ACL does not secure future descendants" in verifier


def test_candidate_venv_must_be_fresh_and_prep_uses_exact_windows_powershell():
    installer = INSTALLER.read_text(encoding="utf-8")
    fresh_check = installer.index("Candidate venv must not already exist")
    preparation = installer.index(
        '"-File", (Join-Path $ReleaseRoot "scripts\\install_loki_local.ps1")'
    )
    assert fresh_check < preparation
    assert '"System32\\WindowsPowerShell\\v1.0\\powershell.exe"' in installer
    assert "Get-Command powershell.exe" not in installer
    assert 'Join-Path $PSHOME "powershell.exe"' not in installer


def test_existing_venv_reuse_requires_current_bound_rollback_evidence():
    installer = INSTALLER.read_text(encoding="utf-8")
    assert "[switch]$ReuseExistingVenv" in installer
    assert "-ReuseExistingVenv requires -PreserveExistingIdentity" in installer
    assert "function Open-ReuseVenvAuthorization" in installer
    assert "function Assert-ReuseEvidenceBindsTarget" in installer
    assert "function Assert-ReuseAuthorizationStillCurrent" in installer
    assert '[System.IO.FileShare]::None' in installer
    authorization = installer.index("$reuseAuthorization = Open-ReuseVenvAuthorization")
    first_hardening = installer.index("Protect-AdministratorTree -Root $lokiRoot")
    assert authorization < first_hardening
    assert '"-I", "-B", "-c", "import os, sys;' in installer
    assert "Authorized rollback venv" in installer


def test_local_installer_ignores_python_startup_environment():
    installer = (ROOT / "scripts" / "install_loki_local.ps1").read_text(encoding="utf-8")
    assert '$bootstrapPrefix = @("-3.12")' in installer
    assert '$bootstrapPrefix + @("-I", "-c"' in installer
    assert '$bootstrapPrefix + @("-I", "-m", "venv"' in installer
    assert installer.count('"-E", "-s", "-B"') >= 8
    assert '"pip", "--isolated", "install"' in installer
    assert '"--no-cache-dir"' in installer


def test_production_installer_uses_protected_process_temp_before_candidate_execution():
    installer = INSTALLER.read_text(encoding="utf-8")
    local_installer = (ROOT / "scripts" / "install_loki_local.ps1").read_text(
        encoding="utf-8"
    )

    temp_setup = installer.index("$protectedTempRoot = Join-Path $stagedInstallerRunRoot")
    candidate_python = installer.index("$runtimeVersion = Invoke-NativeText")
    local_preparation = installer.index("Release-specific Python 3.12 environment preparation")
    assert temp_setup < candidate_python < local_preparation
    assert "$env:TEMP = $protectedTempRoot" in installer
    assert "$env:TMP = $protectedTempRoot" in installer
    assert "$env:TEMP = $previousTemp" in installer
    assert "$env:TMP = $previousTmp" in installer
    assert "Production verification TEMP must be under" in local_installer
    assert "$env:TEMP -ine $env:TMP" in local_installer


def test_production_installer_uses_only_handed_off_system_python_launcher():
    installer = INSTALLER.read_text(encoding="utf-8")
    local_installer = (ROOT / "scripts" / "install_loki_local.ps1").read_text(
        encoding="utf-8"
    )
    assert "[string]$TrustedPythonLauncher" in installer
    assert "[string]$TrustedPythonRuntime" in installer
    assert "[string]$TrustedGitExecutable" in installer
    assert "TrustedPythonLauncher must be exact system-wide launcher" in installer
    assert "(Get-Command py -ErrorAction Stop).Source" not in installer
    assert '"-TrustedPythonLauncher", $launcher' in installer
    assert '"-TrustedPythonRuntime", $pythonRuntime' in installer
    assert '"-TrustedGitExecutable", $trustedGitExecutable' in installer
    assert "[string]$TrustedPythonLauncher" in local_installer
    assert "[string]$TrustedPythonRuntime" in local_installer
    assert "[string]$TrustedGitExecutable" in local_installer
    assert "Get-Command py -ErrorAction Stop" in local_installer
    assert "$launcher = [System.IO.Path]::GetFullPath($TrustedPythonLauncher)" in local_installer
    assert "$bootstrapPython = [System.IO.Path]::GetFullPath($TrustedPythonRuntime)" in local_installer
    assert "$gitExecutable = [System.IO.Path]::GetFullPath($TrustedGitExecutable)" in local_installer
    assert r"C:\Program Files\Python312\python.exe" in installer
    assert r"C:\Program Files\Python312\python.exe" in local_installer
    assert r"C:\Program Files\Git\cmd\git.exe" in installer
    assert r"C:\Program Files\Git\cmd\git.exe" in local_installer


def test_production_installer_sanitizes_path_before_candidate_python_and_tests():
    installer = INSTALLER.read_text(encoding="utf-8")
    local_installer = (ROOT / "scripts" / "install_loki_local.ps1").read_text(
        encoding="utf-8"
    )

    installer_path = installer.index("$env:PATH = $trustedProcessPath")
    candidate_python = installer.index("$runtimeVersion = Invoke-NativeText")
    assert installer_path < candidate_python
    assert "$env:PATHEXT = \".COM;.EXE;.BAT;.CMD\"" in installer
    assert '$env:COMSPEC = "C:\\Windows\\System32\\cmd.exe"' in installer
    assert "$env:PATH = $trustedProcessPath" in local_installer
    assert '$gitExecutable = "git.exe"' in local_installer
    assert 'Invoke-NativeText -FilePath $gitExecutable' in local_installer
    assert '$localCommandLine[1].Equals("-NoProfile"' in local_installer
    assert '$localCommandLine[2].Equals("-ExecutionPolicy"' in local_installer
    assert '$localCommandLine[3].Equals("Bypass"' in local_installer
    assert '$localCommandLine[4].Equals("-File"' in local_installer


def test_installer_and_verifier_use_only_exact_system_service_controller():
    installer = INSTALLER.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")
    for source in (installer, verifier):
        assert r"C:\Windows\System32\sc.exe" in source
        assert '-FilePath "sc.exe"' not in source
        assert "$script:trustedScPath" in source


def test_installer_and_verifier_bind_exact_powershell_and_cim_module():
    installer = INSTALLER.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")
    for source in (installer, verifier):
        assert r"C:\Windows\System32\WindowsPowerShell\v1.0" in source
        assert "[System.Environment]::GetCommandLineArgs()" in source
        assert '$arguments[1].Equals("-NoProfile"' in source
        assert '$arguments[2].Equals("-ExecutionPolicy"' in source
        assert '$arguments[3].Equals("Bypass"' in source
        assert '$arguments[4].Equals("-File"' in source
        assert 'Join-Path $trustedPowerShellHome "Modules\\CimCmdlets\\CimCmdlets.psd1"' in source
        assert "$env:PSModulePath = [System.IO.Path]::Combine" in source
        assert "CimCmdlets\\Get-CimInstance" in source
        assert " Get-CimInstance " not in source


def test_service_environment_pins_safe_commissioning_flags():
    installer = INSTALLER.read_text(encoding="utf-8")
    verifier = VERIFIER.read_text(encoding="utf-8")
    service_host = (ROOT / "scripts" / "windows_service_common.py").read_text(
        encoding="utf-8"
    )
    for source in (installer, verifier, service_host):
        assert 'LOKI_LOCAL_ALLOW_FULL"] = "true"' in source or "LOKI_LOCAL_ALLOW_FULL=true" in source
        assert 'RELAY_ENABLED"] = "false"' in source or "RELAY_ENABLED=false" in source
        assert 'LOKI_ENABLE_SLASH_SYNC"] = "false"' in source or "LOKI_ENABLE_SLASH_SYNC=false" in source


def test_rollback_acl_round_trip_rejects_unapproved_principal(tmp_path):
    elevation = subprocess.run(
        [
            powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$i=[Security.Principal.WindowsIdentity]::GetCurrent();"
            "$p=New-Object Security.Principal.WindowsPrincipal($i);"
            "$p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if elevation.returncode != 0 or elevation.stdout.strip() != "True":
        pytest.skip("exact SYSTEM/Administrators ACL round trip requires elevation")
    rollback_root = tmp_path / "rollback"
    rollback_root.mkdir()
    evidence = rollback_root / "service-config-test.json"
    evidence.write_text("{}", encoding="utf-8")
    root_ps = str(rollback_root).replace("'", "''")
    evidence_ps = str(evidence).replace("'", "''")
    result = run_functions_harness(
        [
            (INSTALLER, "Protect-RollbackEvidenceAcl"),
            (VERIFIER, "Assert-ProtectedRollbackAcl"),
        ],
        rf"""
$root = '{root_ps}'
$evidence = '{evidence_ps}'
try {{
    Protect-RollbackEvidenceAcl -Path $root -Directory
}} catch {{
    throw "protect directory: $($_.Exception.Message)"
}}
try {{ Protect-RollbackEvidenceAcl -Path $evidence }} catch {{ throw "protect file: $($_.Exception.Message)" }}
try {{
    Assert-ProtectedRollbackAcl -Path $root -Directory
}} catch {{
    throw "verify directory: $($_.Exception.Message)"
}}
try {{ Assert-ProtectedRollbackAcl -Path $evidence }} catch {{ throw "verify file: $($_.Exception.Message)" }}
$acl = Get-Acl -LiteralPath $evidence
$everyone = New-Object Security.Principal.SecurityIdentifier("S-1-1-0")
$rule = New-Object Security.AccessControl.FileSystemAccessRule(
    $everyone,
    [Security.AccessControl.FileSystemRights]::ReadData,
    [Security.AccessControl.AccessControlType]::Allow
)
[void]$acl.AddAccessRule($rule)
Set-Acl -LiteralPath $evidence -AclObject $acl
$rejected = $false
try {{ Assert-ProtectedRollbackAcl -Path $evidence }} catch {{ $rejected = $true }}
if (-not $rejected) {{ throw "unapproved rollback ACL principal was accepted" }}
""",
    )
    assert result.returncode == 0, result.stdout + result.stderr
