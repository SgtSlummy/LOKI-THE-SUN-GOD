import pytest
from aiohttp import web

from bot.plugins.llm_chat.plugin import LLMChatCog, LLMChatPlugin, chunk_discord_text
from bot.services.faust_agi import FaustAGIClient, FaustAGIError
from bot.settings import Settings


class FakeFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, content, **kwargs):
        self.messages.append((content, kwargs))


class FakeResponse:
    def __init__(self):
        self.deferred = []

    async def defer(self, **kwargs):
        self.deferred.append(kwargs)


class FakeUser:
    id = 123


class FakeInteraction:
    def __init__(self):
        self.guild_id = 456
        self.channel_id = 789
        self.user = FakeUser()
        self.response = FakeResponse()
        self.followup = FakeFollowup()


class FakeBot:
    def __init__(self):
        self.cogs = []

    async def add_cog(self, cog):
        self.cogs.append(cog)


class FakeFaustClient:
    available = True

    async def run_council(self, **kwargs):
        self.kwargs = kwargs
        return {"text": "Council answer", "run_id": "run-1", "fallback_used": True}


class FakeUnavailableFaustClient:
    available = False


@pytest.mark.asyncio
async def test_faust_client_posts_council_request(unused_tcp_port):
    captured = {}

    async def handle_run(request):
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = await request.json()
        return web.json_response({"run_id": "run-123", "output": "Faust says hi", "fallback_used": False})

    app = web.Application()
    app.router.add_post("/api/faust/run", handle_run)
    runner = web.AppRunner(app)
    await runner.setup()
    port = unused_tcp_port
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        settings = Settings(
            faust_agi_enabled=True,
            faust_agi_base_url=f"http://127.0.0.1:{port}",
            faust_agi_api_key="secret",
            faust_agi_execute=True,
            faust_agi_provider="localai",
        )
        client = FaustAGIClient(settings)
        result = await client.run_council(
            prompt="hello",
            user_id=1,
            guild_id=2,
            channel_id=3,
        )
    finally:
        await runner.cleanup()

    assert captured["auth"] == "Bearer secret"
    assert captured["body"] == {
        "prompt": "hello",
        "context": {"source": "discord", "user_id": 1, "guild_id": 2, "channel_id": 3},
        "selected_mode": "chat",
        "active_workspace": "",
        "target_component": "discord",
        "provider": "localai",
        "route_mode": "local_first",
        "execute": True,
    }
    assert result == {"text": "Faust says hi", "run_id": "run-123", "fallback_used": False}


@pytest.mark.asyncio
async def test_faust_client_reports_http_errors(unused_tcp_port):
    async def handle_run(request):
        return web.json_response({"error": "boom"}, status=503)

    app = web.Application()
    app.router.add_post("/api/faust/run", handle_run)
    runner = web.AppRunner(app)
    await runner.setup()
    port = unused_tcp_port
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        client = FaustAGIClient(Settings(faust_agi_enabled=True, faust_agi_base_url=f"http://127.0.0.1:{port}"))
        with pytest.raises(FaustAGIError, match="Faust AGI request failed with status 503"):
            await client.run_council(prompt="hello", user_id=1, guild_id=2, channel_id=3)
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_faust_client_reports_non_json_response(unused_tcp_port):
    async def handle_run(request):
        return web.Response(text="not json", content_type="text/plain")

    app = web.Application()
    app.router.add_post("/api/faust/run", handle_run)
    runner = web.AppRunner(app)
    await runner.setup()
    port = unused_tcp_port
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        client = FaustAGIClient(Settings(faust_agi_enabled=True, faust_agi_base_url=f"http://127.0.0.1:{port}"))
        with pytest.raises(FaustAGIError, match="non-JSON"):
            await client.run_council(prompt="hello", user_id=1, guild_id=2, channel_id=3)
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_faust_client_reports_unexpected_json_shape(unused_tcp_port):
    async def handle_run(request):
        return web.json_response(["not", "an", "object"])

    app = web.Application()
    app.router.add_post("/api/faust/run", handle_run)
    runner = web.AppRunner(app)
    await runner.setup()
    port = unused_tcp_port
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        client = FaustAGIClient(Settings(faust_agi_enabled=True, faust_agi_base_url=f"http://127.0.0.1:{port}"))
        with pytest.raises(FaustAGIError, match="unexpected response shape"):
            await client.run_council(prompt="hello", user_id=1, guild_id=2, channel_id=3)
    finally:
        await runner.cleanup()


def test_faust_client_is_available_only_when_enabled_and_configured():
    assert not FaustAGIClient(Settings(faust_agi_enabled=False, faust_agi_base_url="http://faust")).available
    assert not FaustAGIClient(Settings(faust_agi_enabled=True, faust_agi_base_url="")).available
    assert FaustAGIClient(Settings(faust_agi_enabled=True, faust_agi_base_url="http://faust")).available


def test_settings_enables_llm_chat_when_faust_enabled(monkeypatch):
    monkeypatch.setenv("FAUST_AGI_ENABLED", "true")
    monkeypatch.setenv("FAUST_AGI_BASE_URL", "http://faust.local")
    monkeypatch.setenv("FAUST_AGI_API_KEY", "do-not-log")

    settings = Settings.from_env()

    assert "llm_chat" in settings.enabled_plugin_names
    assert settings.faust_agi_base_url == "http://faust.local"
    assert settings.safe_log_dict()["faust_agi"] == {
        "enabled": True,
        "configured": True,
        "route_mode": "local_first",
        "provider": "",
        "execute": True,
    }
    assert "do-not-log" not in str(settings.safe_log_dict())


def test_chunk_discord_text_keeps_messages_below_limit():
    chunks = chunk_discord_text("x" * 4500, limit=1900)

    assert "".join(chunks) == "x" * 4500
    assert all(len(chunk) <= 1900 for chunk in chunks)


@pytest.mark.asyncio
async def test_agent_council_command_defers_and_sends_faust_response():
    faust_client = FakeFaustClient()
    cog = LLMChatCog(bot=object(), services={"faust_agi_client": faust_client})
    interaction = FakeInteraction()

    await cog.handle_council(interaction, prompt="What should we build?")

    assert interaction.response.deferred == [{"thinking": True}]
    assert faust_client.kwargs == {
        "prompt": "What should we build?",
        "user_id": 123,
        "guild_id": 456,
        "channel_id": 789,
    }
    assert interaction.followup.messages[0][0] == "Faust AGI council (run run-1, fallback used):\nCouncil answer"
    assert interaction.followup.messages[0][1]["allowed_mentions"].everyone is False


@pytest.mark.asyncio
async def test_agent_council_command_handles_unconfigured_faust():
    cog = LLMChatCog(bot=object(), services={"faust_agi_client": FakeUnavailableFaustClient()})
    interaction = FakeInteraction()

    await cog.handle_council(interaction, prompt="hello")

    assert interaction.followup.messages[0][0] == "Faust AGI is not configured. Set FAUST_AGI_BASE_URL and enable FAUST_AGI_ENABLED=true."
    assert "ephemeral" not in interaction.followup.messages[0][1]


@pytest.mark.asyncio
async def test_llm_chat_plugin_registers_agent_council_only_when_faust_enabled():
    disabled_bot = FakeBot()
    disabled_plugin = LLMChatPlugin()
    await disabled_plugin.setup(disabled_bot, {"settings": Settings(faust_agi_enabled=False)})

    assert disabled_bot.cogs == []
    assert disabled_plugin.cog is None

    enabled_bot = FakeBot()
    enabled_plugin = LLMChatPlugin()
    await enabled_plugin.setup(enabled_bot, {"settings": Settings(faust_agi_enabled=True)})

    assert len(enabled_bot.cogs) == 1
    assert isinstance(enabled_plugin.cog, LLMChatCog)
