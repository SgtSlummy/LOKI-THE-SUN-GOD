from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any

import discord
from aiohttp import web
from discord.ext import commands

from bot.plugins.admin_config import AdminConfigPlugin
from bot.plugins.autonomous_curator import AutonomousCuratorPlugin
from bot.plugins.base import BasePlugin
from bot.plugins.llm_chat import LLMChatPlugin
from bot.plugins.media_resolver import MediaResolverPlugin
from bot.plugins.moderation_audit import ModerationAuditPlugin
from bot.plugins.music import MusicPlugin
from bot.plugins.registry import PluginRegistry
from bot.plugins.relay_core import RelayCorePlugin
from bot.plugins.server_search import ServerSearchPlugin
from bot.plugins.relay_core.formatting import safe_allowed_mentions
from bot.services.cache import MemoryCache
from bot.services.database import Database
from bot.services.llm import LLMClient
from bot.services.logging import configure_logging, log_safe_startup_config
from bot.services.media_resolver import MediaResolver
from bot.services.permissions import PermissionManager
from bot.services.scheduler import Scheduler
from bot.services.search_index import SearchIndex
from bot.settings import Settings


class LokiBot(commands.Bot):
    def __init__(self, *, settings: Settings, services: dict[str, Any], registry: PluginRegistry):
        intents = discord.Intents.default()
        intents.guilds = True
        intents.messages = True
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            allowed_mentions=safe_allowed_mentions(),
        )
        self.settings = settings
        self.services = services
        self.registry = registry
        self.logger = logging.getLogger("loki.discord")

    async def setup_hook(self) -> None:
        await self.registry.setup_plugins(self)
        if self.settings.discord_guild_id is not None:
            guild = discord.Object(id=self.settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            self.logger.info("Synced %s guild-scoped slash commands to %s", len(synced), self.settings.discord_guild_id)
        else:
            synced = await self.tree.sync()
            self.logger.info("Synced %s global slash commands", len(synced))

    async def on_ready(self) -> None:
        self.logger.info("Discord connected as %s in %s guild(s)", self.user, len(self.guilds))
        self.logger.warning(
            "Message Content intent must also be enabled in the Discord Developer Portal; "
            "the code requested it for gateway startup."
        )


def default_plugins() -> list[BasePlugin]:
    return [
        RelayCorePlugin(),
        MediaResolverPlugin(),
        LLMChatPlugin(),
        ServerSearchPlugin(),
        AutonomousCuratorPlugin(),
        MusicPlugin(),
        ModerationAuditPlugin(),
        AdminConfigPlugin(),
    ]


async def create_services(settings: Settings) -> dict[str, Any]:
    database = Database(settings.database_url)
    await database.connect()
    await database.migrate()
    media_resolver = MediaResolver(fetch_external_metadata=settings.bot_env == "production")
    return {
        "settings": settings,
        "database": database,
        "media_resolver": media_resolver,
        "llm_client": LLMClient(settings),
        "search_index": SearchIndex(enabled=settings.server_search_enabled),
        "permission_manager": PermissionManager(admin_user_ids=settings.bot_admin_user_ids),
        "scheduler": Scheduler(),
        "cache": MemoryCache(),
    }


async def apply_bootstrap_routes(settings: Settings, database: Database, logger: logging.Logger) -> None:
    routes = settings.relay_bootstrap_routes
    if not routes:
        return
    existing = await database.list_relay_routes(settings.discord_guild_id)
    existing_keys = {
        (route.guild_id, route.source_channel_id, route.destination_channel_id, route.direction)
        for route in existing
    }
    for route in routes:
        guild_id = int(route.get("guild_id") or settings.discord_guild_id or 0)
        source_channel_id = int(route["source_channel_id"])
        destination_channel_id = int(route["destination_channel_id"])
        direction = route.get("direction", "one_way")
        key = (guild_id, source_channel_id, destination_channel_id, direction)
        if key in existing_keys:
            continue
        await database.add_relay_route(
            guild_id=guild_id,
            source_channel_id=source_channel_id,
            destination_channel_id=destination_channel_id,
            direction=direction,
            created_by=None,
        )
        logger.info("Bootstrapped relay route for guild %s from %s to %s", guild_id, source_channel_id, destination_channel_id)


async def start_health_server(
    *,
    bot: LokiBot,
    services: dict[str, Any],
    registry: PluginRegistry,
    settings: Settings,
) -> web.AppRunner:
    async def healthz(request: web.Request) -> web.Response:
        database = services["database"]
        db_connected = await database.healthcheck()
        active_plugins = registry.active_plugin_names()
        plugin_health = await registry.healthcheck()
        payload = {
            "ok": db_connected and not bot.is_closed(),
            "discord_connected": bot.is_ready(),
            "db_connected": db_connected,
            "active_plugins": active_plugins,
            "plugin_health": plugin_health,
        }
        return web.json_response(payload, status=200 if payload["ok"] else 503)

    app = web.Application()
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/health", healthz)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", settings.health_port)
    await site.start()
    logging.getLogger("loki.health").info("Health server listening on port %s", settings.health_port)
    return runner


async def run() -> None:
    settings = Settings.from_env()
    settings.validate_for_startup()
    logger = configure_logging(settings.log_level)
    log_safe_startup_config(logger, settings.safe_log_dict())

    services = await create_services(settings)
    registry = PluginRegistry(settings=settings, services=services, plugins=default_plugins())
    services["plugin_registry"] = registry
    await apply_bootstrap_routes(settings, services["database"], logger)

    bot = LokiBot(settings=settings, services=services, registry=registry)
    health_runner = await start_health_server(bot=bot, services=services, registry=registry, settings=settings)

    try:
        await bot.start(settings.discord_token)
    finally:
        await registry.teardown_plugins()
        await services["scheduler"].shutdown()
        await health_runner.cleanup()
        await services["database"].close()


def main() -> None:
    with suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()

