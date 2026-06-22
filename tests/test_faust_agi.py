import discord
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


class FailingFollowup:
    def __init__(self):
        self.calls = 0

    async def send(self, content, **kwargs):
        self.calls += 1
        response = type("Response", (), {"status": 500, "reason": "send failed"})()
        raise discord.HTTPException(response, "boom")


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


class FakeBotUser:
    id = 999


class FakeBot:
    def __init__(self):
        self.cogs = []
        self.user = FakeBotUser()

    async def add_cog(self, cog):
        self.cogs.append(cog)


class FakeChannel:
    def __init__(self):
        self.messages = []

    async def send(self, content, **kwargs):
        self.messages.append((content, kwargs))


class FakeAuthor:
    id = 321
    bot = False


class FakeMessage:
    def __init__(self, content: str, *, guild_id: int | None = 456, channel_id: int = 789, raw_mentions: list[int] | None = None):
        self.content = content
        self.guild = None if guild_id is None else object()
        self.guild_id = guild_id
        self.channel = FakeChannel()
        self.channel.id = channel_id
        self.author = FakeAuthor()
        self.raw_mentions = raw_mentions or []


class FakeFaustClient:
    available = True

    async def run_council(self, **kwargs):
        self.kwargs = kwargs
        return {"text": "Council answer", "run_id": "run-1", "fallback_used": True}


class FakeUnavailableFaustClient:
    available = False


class FakeContinuingFaustClient:
    available = True

    def __init__(self, *, continuation_prompt: str = "Continue from run-1", continuation_requests_again: bool = False):
        self.continuation_prompt = continuation_prompt
        self.continuation_requests_again = continuation_requests_again
        self.council_kwargs = None
        self.continuation_kwargs = []

    async def run_council(self, **kwargs):
        self.council_kwargs = kwargs
        return {
            "text": "Initial council answer",
            "run_id": "run-1",
            "fallback_used": False,
            "continue_unprompted": True,
            "continuation_prompt": self.continuation_prompt,
            "continuation_delay_seconds": 0,
        }

    async def run_continuation(self, **kwargs):
        self.continuation_kwargs.append(kwargs)
        return {
            "text": "Autonomous follow-up",
            "run_id": f"run-{len(self.continuation_kwargs) + 1}",
            "fallback_used": False,
            "continue_unprompted": self.continuation_requests_again,
            "continuation_prompt": "Continue again" if self.continuation_requests_again else None,
            "continuation_delay_seconds": 0,
        }


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
    assert result == {
        "text": "Faust says hi",
        "run_id": "run-123",
        "fallback_used": False,
        "continue_unprompted": False,
        "continuation_prompt": None,
        "continuation_delay_seconds": 0,
    }


@pytest.mark.asyncio
async def test_faust_client_normalizes_unprompted_continuation_metadata(unused_tcp_port):
    async def handle_run(request):
        return web.json_response(
            {
                "run_id": "run-123",
                "output": "Initial council answer",
                "fallback_used": False,
                "continue_unprompted": True,
                "continuation_prompt": "Continue reasoning from the last council answer.",
                "continuation_delay_seconds": 0,
            }
        )

    app = web.Application()
    app.router.add_post("/api/faust/run", handle_run)
    runner = web.AppRunner(app)
    await runner.setup()
    port = unused_tcp_port
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        client = FaustAGIClient(Settings(faust_agi_enabled=True, faust_agi_base_url=f"http://127.0.0.1:{port}"))
        result = await client.run_council(prompt="hello", user_id=1, guild_id=2, channel_id=3)
    finally:
        await runner.cleanup()

    assert result == {
        "text": "Initial council answer",
        "run_id": "run-123",
        "fallback_used": False,
        "continue_unprompted": True,
        "continuation_prompt": "Continue reasoning from the last council answer.",
        "continuation_delay_seconds": 0,
    }


@pytest.mark.asyncio
async def test_faust_client_posts_unprompted_continuation_request(unused_tcp_port):
    captured = {}

    async def handle_run(request):
        captured["body"] = await request.json()
        return web.json_response({"run_id": "run-124", "output": "Unprompted continuation answer"})

    app = web.Application()
    app.router.add_post("/api/faust/run", handle_run)
    runner = web.AppRunner(app)
    await runner.setup()
    port = unused_tcp_port
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        client = FaustAGIClient(Settings(faust_agi_enabled=True, faust_agi_base_url=f"http://127.0.0.1:{port}"))
        result = await client.run_continuation(
            prompt="Continue reasoning from the last council answer.",
            parent_run_id="run-123",
            guild_id=2,
            channel_id=3,
        )
    finally:
        await runner.cleanup()

    assert captured["body"] == {
        "prompt": "Continue reasoning from the last council answer.",
        "context": {
            "source": "discord_unprompted",
            "user_id": None,
            "guild_id": 2,
            "channel_id": 3,
            "parent_run_id": "run-123",
        },
        "selected_mode": "chat",
        "active_workspace": "",
        "target_component": "discord",
        "provider": "",
        "route_mode": "local_first",
        "execute": False,
    }
    assert result == {
        "text": "Unprompted continuation answer",
        "run_id": "run-124",
        "fallback_used": False,
        "continue_unprompted": False,
        "continuation_prompt": None,
        "continuation_delay_seconds": 0,
    }


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
    monkeypatch.setenv("FAUST_AGI_PROVIDER", "")
    monkeypatch.setenv("FAUST_AGI_EXECUTE", "true")

    settings = Settings.from_env()

    assert "llm_chat" in settings.enabled_plugin_names
    assert settings.faust_agi_base_url == "http://faust.local"
    assert settings.safe_log_dict()["faust_agi"] == {
        "enabled": True,
        "configured": True,
        "route_mode": "local_first",
        "provider": "",
        "execute": True,
        "unprompted_continuations_enabled": False,
        "unprompted_max_turns": 1,
        "unprompted_max_delay_seconds": 30,
    }
    assert "do-not-log" not in str(settings.safe_log_dict())


def test_settings_reads_unprompted_faust_continuation_config(monkeypatch):
    monkeypatch.setenv("FAUST_AGI_UNPROMPTED_CONTINUATIONS_ENABLED", "true")
    monkeypatch.setenv("FAUST_AGI_UNPROMPTED_MAX_TURNS", "3")
    monkeypatch.setenv("FAUST_AGI_UNPROMPTED_MAX_DELAY_SECONDS", "45")

    settings = Settings.from_env()

    assert settings.faust_agi_unprompted_continuations_enabled is True
    assert settings.faust_agi_unprompted_max_turns == 3
    assert settings.faust_agi_unprompted_max_delay_seconds == 45
    assert settings.safe_log_dict()["faust_agi"]["unprompted_continuations_enabled"] is True
    assert settings.safe_log_dict()["faust_agi"]["unprompted_max_turns"] == 3
    assert settings.safe_log_dict()["faust_agi"]["unprompted_max_delay_seconds"] == 45


def test_chunk_discord_text_keeps_messages_below_limit():
    chunks = chunk_discord_text("x" * 4500, limit=1900)

    assert "".join(chunks) == "x" * 4500
    assert all(len(chunk) <= 1900 for chunk in chunks)


@pytest.mark.asyncio
async def test_faust_client_strictly_parses_continuation_metadata(unused_tcp_port):
    async def handle_run(request):
        return web.json_response(
            {
                "run_id": "run-123",
                "output": "No continuation",
                "continue_unprompted": "false",
                "continuation_prompt": "Should not run",
                "continuation_delay_seconds": "soon",
            }
        )

    app = web.Application()
    app.router.add_post("/api/faust/run", handle_run)
    runner = web.AppRunner(app)
    await runner.setup()
    port = unused_tcp_port
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    try:
        client = FaustAGIClient(Settings(faust_agi_enabled=True, faust_agi_base_url=f"http://127.0.0.1:{port}"))
        result = await client.run_council(prompt="hello", user_id=1, guild_id=2, channel_id=3)
    finally:
        await runner.cleanup()

    assert result["continue_unprompted"] is False
    assert result["continuation_delay_seconds"] == 0


@pytest.mark.asyncio
async def test_faust_client_clamps_continuation_delay(unused_tcp_port):
    async def handle_run(request):
        return web.json_response(
            {
                "run_id": "run-123",
                "output": "Delayed continuation",
                "continue_unprompted": True,
                "continuation_prompt": "Continue",
                "continuation_delay_seconds": 999999,
            }
        )

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
            faust_agi_unprompted_max_delay_seconds=30,
        )
        client = FaustAGIClient(settings)
        result = await client.run_council(prompt="hello", user_id=1, guild_id=2, channel_id=3)
    finally:
        await runner.cleanup()

    assert result["continuation_delay_seconds"] == 30


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
async def test_agent_council_sends_unprompted_continuation_when_enabled():
    faust_client = FakeContinuingFaustClient()
    settings = Settings(
        faust_agi_enabled=True,
        faust_agi_unprompted_continuations_enabled=True,
        faust_agi_unprompted_max_turns=1,
    )
    cog = LLMChatCog(bot=object(), services={"settings": settings, "faust_agi_client": faust_client})
    interaction = FakeInteraction()

    await cog.handle_council(interaction, prompt="What should we build?")

    assert faust_client.council_kwargs == {
        "prompt": "What should we build?",
        "user_id": 123,
        "guild_id": 456,
        "channel_id": 789,
    }
    assert faust_client.continuation_kwargs == [
        {
            "prompt": "Continue from run-1",
            "parent_run_id": "run-1",
            "guild_id": 456,
            "channel_id": 789,
        }
    ]
    assert interaction.followup.messages[0][0] == "Faust AGI council (run run-1):\nInitial council answer"
    assert interaction.followup.messages[1][0] == "Faust AGI continuation (run run-2):\nAutonomous follow-up"
    assert interaction.followup.messages[1][1]["allowed_mentions"].everyone is False


@pytest.mark.asyncio
async def test_agent_council_does_not_continue_unprompted_when_disabled():
    faust_client = FakeContinuingFaustClient()
    settings = Settings(faust_agi_enabled=True, faust_agi_unprompted_continuations_enabled=False)
    cog = LLMChatCog(bot=object(), services={"settings": settings, "faust_agi_client": faust_client})
    interaction = FakeInteraction()

    await cog.handle_council(interaction, prompt="What should we build?")

    assert faust_client.council_kwargs is not None
    assert faust_client.continuation_kwargs == []
    assert len(interaction.followup.messages) == 1


@pytest.mark.asyncio
async def test_agent_council_does_not_continue_without_continuation_prompt():
    faust_client = FakeContinuingFaustClient(continuation_prompt="")
    settings = Settings(
        faust_agi_enabled=True,
        faust_agi_unprompted_continuations_enabled=True,
        faust_agi_unprompted_max_turns=1,
    )
    cog = LLMChatCog(bot=object(), services={"settings": settings, "faust_agi_client": faust_client})
    interaction = FakeInteraction()

    await cog.handle_council(interaction, prompt="What should we build?")

    assert faust_client.continuation_kwargs == []
    assert len(interaction.followup.messages) == 1


@pytest.mark.asyncio
async def test_agent_council_limits_unprompted_continuations_to_configured_max_turns():
    faust_client = FakeContinuingFaustClient(continuation_requests_again=True)
    settings = Settings(
        faust_agi_enabled=True,
        faust_agi_unprompted_continuations_enabled=True,
        faust_agi_unprompted_max_turns=1,
    )
    cog = LLMChatCog(bot=object(), services={"settings": settings, "faust_agi_client": faust_client})
    interaction = FakeInteraction()

    await cog.handle_council(interaction, prompt="What should we build?")

    assert len(faust_client.continuation_kwargs) == 1
    assert len(interaction.followup.messages) == 2
    assert all("Continue again" not in message[0] for message in interaction.followup.messages)


@pytest.mark.asyncio
async def test_agent_council_stops_unprompted_continuation_when_initial_send_fails():
    faust_client = FakeContinuingFaustClient()
    settings = Settings(
        faust_agi_enabled=True,
        faust_agi_unprompted_continuations_enabled=True,
        faust_agi_unprompted_max_turns=1,
    )
    cog = LLMChatCog(bot=object(), services={"settings": settings, "faust_agi_client": faust_client})
    interaction = FakeInteraction()
    interaction.followup = FailingFollowup()

    await cog.handle_council(interaction, prompt="What should we build?")

    assert interaction.followup.calls == 1
    assert faust_client.continuation_kwargs == []


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


@pytest.mark.asyncio
async def test_llm_chat_mention_message_sends_faust_response_to_channel():
    faust_client = FakeFaustClient()
    bot = FakeBot()
    cog = LLMChatCog(bot=bot, services={"faust_agi_client": faust_client})
    message = FakeMessage("<@999> help me plan this", raw_mentions=[999])

    await cog.on_message(message)

    assert faust_client.kwargs == {
        "prompt": "help me plan this",
        "user_id": 321,
        "guild_id": 456,
        "channel_id": 789,
    }
    assert message.channel.messages[0][0] == "Faust AGI council (run run-1, fallback used):\nCouncil answer"
    assert message.channel.messages[0][1]["allowed_mentions"].everyone is False


@pytest.mark.asyncio
async def test_llm_chat_dm_message_sends_faust_response_to_channel_without_mention():
    faust_client = FakeFaustClient()
    bot = FakeBot()
    cog = LLMChatCog(bot=bot, services={"faust_agi_client": faust_client})
    message = FakeMessage("help me from a DM", guild_id=None)

    await cog.on_message(message)

    assert faust_client.kwargs == {
        "prompt": "help me from a DM",
        "user_id": 321,
        "guild_id": None,
        "channel_id": 789,
    }
    assert message.channel.messages[0][0] == "Faust AGI council (run run-1, fallback used):\nCouncil answer"


@pytest.mark.asyncio
async def test_llm_chat_ignores_guild_message_without_loki_mention():
    faust_client = FakeFaustClient()
    bot = FakeBot()
    cog = LLMChatCog(bot=bot, services={"faust_agi_client": faust_client})
    message = FakeMessage("hello everyone")

    await cog.on_message(message)

    assert not hasattr(faust_client, "kwargs")
    assert message.channel.messages == []
