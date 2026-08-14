from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_service_ci_contract():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    windows_job = workflow.split("  windows-services:", 1)[1]
    assert "runs-on: windows-latest" in windows_job
    assert 'python-version: "3.12"' in windows_job
    for required in (
        "requirements.txt",
        "requirements-dev.txt",
        "compileall",
        "secret_scan.py",
        "test_windows_service_host.py",
        "test_service_stop_runtime.py",
        "test_credential_store.py",
        "test_local_runtime.py",
        "test_installer_archive_trust.py",
        "test_service_install_transaction.py",
        "test_loki_service_bootstrap.py",
    ):
        assert required in windows_job
    for forbidden in ("install_loki_services.ps1", "Start-Service", "sc.exe"):
        assert forbidden not in windows_job


def test_windows_service_commissioning_docs_contract():
    guide_path = ROOT / "docs" / "WINDOWS_SERVICE_DEPLOYMENT.md"
    guide = guide_path.read_text(encoding="utf-8")
    for required in (
        "LokiTHESunGodBot",
        "LokiTHESunGodDashboard",
        r"C:\ProgramData\Loki\config\lokithesungod.env",
        r"LOKI\Administrator",
        "Credential Manager > process environment > `.env`",
        "MESSAGE_CONTENT",
        "GUILD_MEMBERS",
        "LOKI_LOCAL_ALLOW_FULL=true",
        "RELAY_ENABLED=false",
        "LOKI_ENABLE_SLASH_SYNC=false",
        "DASHBOARD_HOST=127.0.0.1",
        "DASHBOARD_PORT=5000",
        r"C:\Windows\py.exe",
        "all-users launcher",
        r"C:\Program Files\Python312\python.exe",
        "machine-wide Python 3.12",
        r"C:\Program Files\Git\cmd\git.exe",
        "machine-wide Git for Windows",
        "-ExpectedArchiveSha256",
        "test guild",
        "rollback",
        "/healthz",
    ):
        assert required.lower() in guide.lower()

    trusted_bootstrap = guide.index(r"C:\ProgramData\Loki\bootstrap\bootstrap_loki_services.ps1")
    seed_credentials = guide.index("set_loki_credentials.py")
    start_services = guide.index("Start-Service LokiTHESunGodBot")
    assert trusted_bootstrap < seed_credentials < start_services
    assert r'& "$releaseRoot\scripts\install_loki_local.ps1"' not in guide
    assert r'& "$releaseRoot\scripts\install_loki_services.ps1"' not in guide
    assert r'$credentialPython = "$venvPath\Scripts\python.exe"' in guide
    assert "& $credentialPython -I -B" in guide
    assert "WindowsApps alias" in guide
    assert "used only for non-executing runtime inventory" in guide
    assert "[Diagnostics.Process]::GetCurrentProcess().MainModule.FileName" in guide
    assert r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" in guide
    assert '$PSVersionTable.PSEdition -cne "Desktop"' in guide
    assert guide.count("$expectedPowerShell -NoProfile -ExecutionPolicy Bypass -File") >= 3
    assert "& C:\\ProgramData\\Loki\\bootstrap\\bootstrap_loki_services.ps1" not in guide
    assert "$buildPowerShell -NoProfile -ExecutionPolicy Bypass -File" in guide
    assert guide.count("$expectedPowerShell -NoProfile -ExecutionPolicy Bypass -File") >= 7
    assert r'& "$releaseRoot\scripts\verify_loki_services.ps1"' not in guide
    assert "-ReuseExistingVenv" in guide
    assert "unsupported legacy" in guide.lower()
    assert " /T /C" not in guide
    assert guide.index("[IO.Directory]::CreateDirectory($lokiRoot") < guide.index(
        "[IO.File]::WriteAllText($configPath"
    )
    assert guide.index("Assert-LokiExactAcl -Path $lokiRoot -Directory") < guide.index(
        "[IO.Directory]::CreateDirectory($configRoot"
    )
    assert "[IO.Directory]::SetAccessControl($Path, $acl)" in guide
    assert "Set-Acl -LiteralPath" not in guide
    module_sanitization = guide.index(
        '$env:PSModulePath = [IO.Path]::Combine($expectedPsHome, "Modules")'
    )
    first_provisioning = guide.index('$lokiRoot = "C:\\ProgramData\\Loki"')
    assert module_sanitization < first_provisioning
    assert (
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe "
        r'-NoProfile -Command "[void][IO.Directory]::CreateDirectory('
    ) in guide
    assert "'powershell -NoProfile -Command" not in guide

    for path in (
        ROOT / "docs" / "DEPLOYMENT.md",
        ROOT / "docs" / "LOCAL_HEARTBEAT_RUNTIME.md",
        ROOT / "docs" / "testing" / "test-plan.md",
    ):
        assert "WINDOWS_SERVICE_DEPLOYMENT.md" in path.read_text(encoding="utf-8")
    heartbeat = (ROOT / "docs" / "LOCAL_HEARTBEAT_RUNTIME.md").read_text(
        encoding="utf-8"
    )
    assert "powershell.exe" in heartbeat
    assert "-NoProfile -ExecutionPolicy Bypass -File" in heartbeat
