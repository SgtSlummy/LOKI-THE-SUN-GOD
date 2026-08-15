from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def load_script(name: str):
    path = SCRIPTS / name
    assert path.is_file(), f"missing deployment helper: {path}"
    spec = importlib.util.spec_from_file_location(f"test_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def make_git_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    run_git(source, "init")
    run_git(source, "config", "user.email", "tests@example.invalid")
    run_git(source, "config", "user.name", "LOKI Tests")
    (source / "app.py").write_text("print('safe')\n", encoding="utf-8")
    (source / ".env.example").write_text("TOKEN=replace-me\n", encoding="utf-8")
    (source / "data").mkdir()
    (source / "data" / "runtime.db").write_bytes(b"forbidden")
    (source / "runtime-logs").mkdir()
    (source / "runtime-logs" / "service.log").write_text("forbidden", encoding="utf-8")
    (source / "root-runtime.log").write_text("forbidden", encoding="utf-8")
    run_git(source, "add", ".")
    run_git(source, "commit", "-m", "fixture")
    return source


def test_pywin32_is_pinned_for_windows_only():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert 'pywin32==312; sys_platform == "win32"' in requirements


def test_install_local_is_strict_python312_and_preserves_existing_venvs():
    script = (SCRIPTS / "install_loki_local.ps1").read_text(encoding="utf-8")
    assert "-3.12" in script
    assert "Get-Command python" not in script
    assert "Get-Command uv" not in script
    assert "Remove-Item" not in script
    assert "requirements-dev.txt" in script
    assert "import win32service, win32cred" in script
    for check in ("compileall", "ruff", "secret_scan.py", "--preflight", "release_check.py", "pytest"):
        assert check in script
    for external_path_control in ("LOKI_DB_PATH", "PYTHONPYCACHEPREFIX", "RUFF_CACHE_DIR", "VerificationRoot"):
        assert external_path_control in script
    assert '"no:cacheprovider"' in script
    assert "VerificationRoot must be outside the source/release root" in script


@pytest.mark.parametrize(
    "name",
    [
        "install_loki_local.ps1",
        "prepare_loki_server_bundle.ps1",
        "bootstrap_loki_services.ps1",
        "install_loki_services.ps1",
        "verify_loki_services.ps1",
    ],
)
def test_powershell_deployment_scripts_parse(name: str):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if not shell:
        pytest.skip("PowerShell parser is unavailable")
    path = SCRIPTS / name
    assert path.is_file(), f"missing deployment script: {path}"
    command = (
        "$errors=$null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$null,[ref]$errors); "
        "if($errors.Count){$errors | ForEach-Object {$_.Message}; exit 1}"
    )
    result = subprocess.run([shell, "-NoProfile", "-Command", command], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_release_archive_manifest_verifies_and_detects_tampering(tmp_path):
    manifest = load_script("release_manifest.py")
    source = make_git_source(tmp_path)
    archive = tmp_path / "loki-candidate.zip"

    result = manifest.build_release_archive(source, archive)

    assert result["archive_path"] == str(archive.resolve())
    verified = manifest.verify_archive(archive, archive.with_suffix(".zip.sha256.json"))
    assert verified["candidate_id"].startswith("loki-")
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        release_manifest = json.loads(bundle.read("release-manifest.json"))
    assert "app.py" in names
    assert ".env.example" in names
    assert "data/runtime.db" not in names
    assert "runtime-logs/service.log" not in names
    assert "root-runtime.log" not in names
    assert "release-manifest.json" not in {item["path"] for item in release_manifest["files"]}

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive) as source_bundle, zipfile.ZipFile(tampered, "x") as tampered_bundle:
        for info in source_bundle.infolist():
            content = source_bundle.read(info.filename)
            if info.filename == "app.py":
                content = b"print('tampered')\n"
            tampered_bundle.writestr(info, content)
    with pytest.raises(manifest.ManifestError, match="digest|size"):
        manifest.verify_archive(tampered)


def test_release_directory_manifest_detects_tampering(tmp_path):
    manifest = load_script("release_manifest.py")
    source = make_git_source(tmp_path)
    archive = tmp_path / "release.zip"
    manifest.build_release_archive(source, archive)
    release_root = tmp_path / "release"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(release_root)

    manifest.verify_directory(release_root)
    cache_file = release_root / "__pycache__" / "unexpected.pyc"
    cache_file.parent.mkdir()
    cache_file.write_bytes(b"cache drift")
    with pytest.raises(manifest.ManifestError, match="exactly"):
        manifest.verify_directory(release_root)
    cache_file.unlink()
    cache_file.parent.rmdir()
    (release_root / "app.py").write_text("changed\n", encoding="utf-8")
    with pytest.raises(manifest.ManifestError, match="digest|size"):
        manifest.verify_directory(release_root)


def test_release_builder_rejects_dirty_source(tmp_path):
    manifest = load_script("release_manifest.py")
    source = make_git_source(tmp_path)
    (source / "untracked.txt").write_text("not reviewed\n", encoding="utf-8")

    with pytest.raises(manifest.ManifestError, match="clean"):
        manifest.build_release_archive(source, tmp_path / "dirty.zip")


@pytest.mark.parametrize(
    "unsafe",
    ["../escape.py", "dir/file:stream", "NUL.txt", "dir/trailing. ", "C:/absolute.py"],
)
def test_release_manifest_rejects_windows_unsafe_paths(unsafe):
    manifest = load_script("release_manifest.py")
    with pytest.raises(manifest.ManifestError, match="unsafe|Unsafe"):
        manifest._safe_relative_path(unsafe)


def test_external_archive_sidecar_binds_sha256_and_size(tmp_path):
    manifest = load_script("release_manifest.py")
    source = make_git_source(tmp_path)
    archive = tmp_path / "release.zip"
    manifest.build_release_archive(source, archive)
    sidecar = json.loads(archive.with_suffix(".zip.sha256.json").read_text(encoding="utf-8"))

    assert sidecar["archive_sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert sidecar["archive_size"] == archive.stat().st_size
    assert sidecar["archive_name"] == archive.name


def test_bundle_builder_emits_external_bootstrap_and_digest():
    script = (SCRIPTS / "prepare_loki_server_bundle.ps1").read_text(encoding="utf-8")
    assert '"scripts/bootstrap_loki_services.ps1"' in script
    assert '"$OutputPath.bootstrap.ps1"' in script
    assert '"$bootstrapPath.sha256"' in script
    assert "System.IO.Compression.ZipFile" in script
    assert "Export-TrustedBootstrap" in script
    assert "Copy-Item -LiteralPath $bootstrapSource" not in script
    assert "Bootstrap:" in script
    assert "Bootstrap SHA-256:" in script
    assert "$env:PSModulePath = [System.IO.Path]::Combine" in script
    assert "Microsoft.PowerShell.Utility.psd1" in script
    assert '$preparerCommandLine[1].Equals("-NoProfile"' in script
    assert '$preparerCommandLine[4].Equals("-File"' in script


def test_credential_cli_is_interactive_allowlisted_and_redacted(monkeypatch, capsys):
    cli = load_script("set_loki_credentials.py")
    secret = "value-that-must-never-appear"
    prompts: list[str] = []
    writes: list[tuple[str, str]] = []

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return secret

    monkeypatch.setattr(cli.getpass, "getpass", fake_getpass)
    monkeypatch.setattr(cli.credential_store, "write_credential", lambda name, value: writes.append((name, value)))
    monkeypatch.setattr(cli, "assert_service_identity", lambda: "LOKI\\Administrator")

    assert cli.main(["set", "DISCORD_TOKEN"]) == 0
    output = capsys.readouterr()
    assert writes == [("DISCORD_TOKEN", secret)]
    assert len(prompts) == 2
    assert secret not in output.out + output.err
    assert "DISCORD_TOKEN" in output.out
    assert "LOKI/LokiTHESunGod/DISCORD_TOKEN" in output.out


def test_credential_cli_cannot_write_bytecode_into_immutable_release():
    script = (SCRIPTS / "set_loki_credentials.py").read_text(encoding="utf-8")
    assert script.index("sys.dont_write_bytecode = True") < script.index(
        "from utils import credential_store"
    )


def test_credential_cli_uses_token_backed_identity_not_environment_names():
    script = (SCRIPTS / "set_loki_credentials.py").read_text(encoding="utf-8")
    assert "OpenProcessToken" in script
    assert "LookupAccountSid" in script
    assert "USERDOMAIN" not in script
    assert "raise SystemExit(child.returncode)" in script
    assert "LOKI_CREDENTIAL_PYTHON" not in script
    assert 'Path(r"C:\\ProgramData")' in script
    assert '[str(candidate), "-I", "-B", "-c"' in script
    assert '[str(candidate), "-I", "-B", str(Path(__file__).resolve())' in script
    assert "pip install" not in script


def test_credential_cli_reexec_propagates_child_failure(tmp_path, monkeypatch):
    cli = load_script("set_loki_credentials.py")
    candidate = tmp_path / "python.exe"
    candidate.write_bytes(b"test executable placeholder")
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0 if len(calls) == 1 else 17)

    monkeypatch.setattr(cli, "_candidate_pythons", lambda: [candidate])
    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as error:
        cli.maybe_reexec_with_pywin32(platform_name="nt", pywin32_ready=False)
    assert error.value.code == 17
    assert len(calls) == 2


def test_credential_cli_redacts_non_os_provider_errors(monkeypatch, capsys):
    cli = load_script("set_loki_credentials.py")

    class ProviderFailure(Exception):
        pass

    secret = "provider-failure-value-never-print"
    monkeypatch.setattr(cli, "assert_service_identity", lambda: "LOKI\\Administrator")
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: secret)
    monkeypatch.setattr(
        cli.credential_store,
        "write_credential",
        lambda _name, _value: (_ for _ in ()).throw(ProviderFailure(secret)),
    )

    with pytest.raises(SystemExit) as error:
        cli.main(["set", "DISCORD_TOKEN"])
    assert error.value.code == 1
    output = capsys.readouterr()
    assert "ProviderFailure" in output.err
    assert secret not in output.out + output.err


def test_credential_cli_rejects_non_allowlisted_name_before_prompt(monkeypatch):
    cli = load_script("set_loki_credentials.py")
    prompted = False

    def fake_getpass(_prompt: str) -> str:
        nonlocal prompted
        prompted = True
        return "secret"

    monkeypatch.setattr(cli.getpass, "getpass", fake_getpass)
    monkeypatch.setattr(cli, "assert_service_identity", lambda: "LOKI\\Administrator")
    with pytest.raises(SystemExit):
        cli.main(["set", "UNREVIEWED_SECRET"])
    assert prompted is False


def test_service_installer_has_secure_identity_recovery_and_no_autostart():
    script = (SCRIPTS / "install_loki_services.ps1").read_text(encoding="utf-8")
    assert '"LOKI\\Administrator"' in script
    assert "Get-Credential" in script
    assert "Invoke-CimMethod" in script
    assert "SecureStringToBSTR" in script
    assert "ZeroFreeBSTR" in script
    assert "ChangeServiceConfigW" in script
    assert "StartPassword" not in script
    assert "--password" not in script
    assert "Start-Service" not in script
    assert "failureflag" in script
    assert 'restart/60000/restart/120000/""/0' in script
    assert "reset=" in script and "86400" in script
    for flag in ("LOKI_LOCAL_ALLOW_FULL", "RELAY_ENABLED", "LOKI_ENABLE_SLASH_SYNC"):
        assert flag in script
    assert "ConfigPath must be the commissioned stable path" in script
    assert "Post-test immutable release verification" in script
    assert "Post-registration immutable release verification" in script
    assert "PYTHONPYCACHEPREFIX" in script
    assert "LOKI_DB_PATH" in script
    assert "rollback" in script.lower()


@pytest.mark.parametrize("name", ["loki_bot_service.py", "loki_dashboard_service.py"])
def test_service_wrappers_disable_bytecode_before_common_import(name: str):
    script = (SCRIPTS / name).read_text(encoding="utf-8")
    assert "sys.dont_write_bytecode = True" in script
    assert script.index("sys.dont_write_bytecode = True") < script.index("windows_service_common")


def test_service_verifier_is_read_only_unless_recovery_is_explicitly_confirmed():
    script = (SCRIPTS / "verify_loki_services.ps1").read_text(encoding="utf-8")
    assert "ExerciseRecovery" in script
    assert "EXERCISE LOKI SERVICE RECOVERY" in script
    assert "Stop-Process" in script
    assert "Get-CimInstance" in script
    assert "DelayedAutoStart" in script
    assert "qfailure" in script
    assert "qfailureflag" in script
    assert "/healthz" in script
    assert "scan_service_logs.py" in script
    assert "Live immutable release verification" in script
    for flag in ("LOKI_LOCAL_ALLOW_FULL", "RELAY_ENABLED", "LOKI_ENABLE_SLASH_SYNC"):
        assert flag in script


def test_log_scanner_reports_secret_names_not_values(tmp_path, monkeypatch, capsys):
    scanner = load_script("scan_service_logs.py")
    secret = "credential-value-never-print"
    log = tmp_path / "bot-service.log"
    log.write_text(f"bad accidental value {secret}\n", encoding="utf-8")
    for name in scanner.credential_store.SUPPORTED_SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        scanner.credential_store,
        "read_credential",
        lambda name: secret if name == "DISCORD_TOKEN" else None,
    )

    assert scanner.main([str(log)]) == 1
    output = capsys.readouterr()
    assert "DISCORD_TOKEN" in output.err
    assert secret not in output.out + output.err


def test_log_scanner_includes_stable_env_fallback_and_fails_closed(tmp_path, monkeypatch, capsys):
    scanner = load_script("scan_service_logs.py")
    secret = "fallback-secret-never-print"
    env_path = tmp_path / "lokithesungod.env"
    env_path.write_text("DISCORD_" + f"TOKEN={secret}\n", encoding="utf-8")
    log = tmp_path / "dashboard-service.log"
    log.write_text(f"leaked {secret}\n", encoding="utf-8")
    for name in scanner.credential_store.SUPPORTED_SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(scanner.credential_store, "read_credential", lambda _name: None)

    assert scanner.main(["--env-path", str(env_path), str(log)]) == 1
    output = capsys.readouterr()
    assert "DISCORD_TOKEN" in output.err
    assert secret not in output.out + output.err

    monkeypatch.setattr(
        scanner.credential_store,
        "read_credential",
        lambda _name: (_ for _ in ()).throw(OSError("sensitive provider failure")),
    )
    with pytest.raises(SystemExit) as error:
        scanner.main(["--env-path", str(env_path), str(log)])
    assert error.value.code == 2
    output = capsys.readouterr()
    assert secret not in output.out + output.err
