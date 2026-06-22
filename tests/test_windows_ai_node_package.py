from __future__ import annotations

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parents[1] / "installer" / "windows-ai-node"


def test_windows_ai_node_package_contains_one_click_entrypoint_and_core_assets():
    required = [
        "Install-LokiHermesNode.cmd",
        "Install-LokiHermesNode.ps1",
        "README.md",
        "templates/hermes-config.yaml.template",
        "templates/hermes-env.template",
        "templates/loki-node.env.template",
        "templates/obsidian-loki-home.md",
        "prompts/install-aide-1bit.md",
        "scripts/loki_hermes_bridge.py",
        "scripts/Start-LokiHermesNode.cmd",
    ]

    missing = [relative for relative in required if not (PACKAGE_DIR / relative).exists()]

    assert missing == []


def test_windows_ai_node_installer_mentions_required_integrations_and_safe_defaults():
    installer = (PACKAGE_DIR / "Install-LokiHermesNode.ps1").read_text(encoding="utf-8")
    readme = (PACKAGE_DIR / "README.md").read_text(encoding="utf-8")
    bridge = (PACKAGE_DIR / "scripts" / "loki_hermes_bridge.py").read_text(encoding="utf-8")

    for token in ["Hermes", "Ollama", "Tailscale", "Obsidian", "FAUST_AGI_BASE_URL", "OpenAI", "gpt-5.5"]:
        assert token in installer or token in readme

    assert "FAUST_AGI_ADMIN_EXECUTE_ENABLED=true" in installer
    assert "LokiBot" in installer
    assert "python -m scripts.loki_guardian" in (PACKAGE_DIR / "scripts" / "Start-LokiHermesNode.cmd").read_text(encoding="utf-8")
    assert "BOT_ADMIN_USER_IDS" in installer
    assert "HERMES_HOME" in installer
    assert "profiles" in installer
    assert "memory" in installer.lower()
    assert "127.0.0.1" in installer
    assert "--provider openai-codex" in bridge
    assert "ollama" in bridge.lower()
    assert "/api/faust/run" in bridge


def test_windows_ai_node_templates_do_not_contain_real_secrets():
    combined = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PACKAGE_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in {".md", ".ps1", ".cmd", ".template", ".py"}
    )

    forbidden_secret_shapes = ["sk-", "ghp_", "discord.com/api/webhooks/"]
    for token in forbidden_secret_shapes:
        assert token not in combined

    for placeholder in ["REPLACE_WITH_DISCORD_BOT_TOKEN", "REPLACE_WITH_OPENAI_API_KEY"]:
        assert placeholder in combined
