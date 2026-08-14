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
        "-ExpectedArchiveSha256",
        "test guild",
        "rollback",
        "/healthz",
    ):
        assert required.lower() in guide.lower()

    prepare_venv = guide.index("install_loki_local.ps1")
    seed_credentials = guide.index("set_loki_credentials.py set DISCORD_TOKEN")
    install_services = guide.index("install_loki_services.ps1")
    start_services = guide.index("Start-Service LokiTHESunGodBot")
    assert prepare_venv < seed_credentials < install_services < start_services

    for path in (
        ROOT / "docs" / "DEPLOYMENT.md",
        ROOT / "docs" / "LOCAL_HEARTBEAT_RUNTIME.md",
        ROOT / "docs" / "testing" / "test-plan.md",
    ):
        assert "WINDOWS_SERVICE_DEPLOYMENT.md" in path.read_text(encoding="utf-8")
