from __future__ import annotations

import logging
from typing import Any, Literal

import discord
from discord import app_commands
from discord.ext import commands

from bot.plugins.base import BasePlugin, PluginSlot
from bot.plugins.relay_core.formatting import safe_allowed_mentions
from bot.services.database import Database
from bot.services.permissions import PermissionManager


class AdminConfigCog(commands.Cog):
    control_group = app_commands.Group(name="bot", description="Bot administration")
    relay_group = app_commands.Group(name="relay", description="Relay administration")

    def __init__(
        self,
        bot: commands.Bot,
        *,
        services: dict[str, Any],
        logger: logging.Logger,
    ):
        self.bot = bot
        self.services = services
        self.logger = logger
        self.database: Database = services["database"]
        self.permission_manager: PermissionManager = services["permission_manager"]

    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        if self.permission_manager.is_admin_interaction(interaction):
            return True
        await interaction.response.send_message("You do not have permission to use this admin command.", ephemeral=True)
        return False

    @control_group.command(name="status", description="Show bot health.")
    async def bot_status(self, interaction: discord.Interaction) -> None:
        if not await self._require_admin(interaction):
            return
        registry = self.services["plugin_registry"]
        db_ok = await self.database.healthcheck()
        active = registry.active_plugin_names()
        await interaction.response.send_message(
            "\n".join(
                [
                    f"Discord connected: {self.bot.is_ready()}",
                    f"Database connected: {db_ok}",
                    f"Active plugins: {', '.join(active) if active else 'none'}",
                ]
            ),
            ephemeral=True,
            allowed_mentions=safe_allowed_mentions(),
        )

    @control_group.command(name="plugins", description="List active plugin slots.")
    async def bot_plugins(self, interaction: discord.Interaction) -> None:
        if not await self._require_admin(interaction):
            return
        registry = self.services["plugin_registry"]
        active = registry.active_plugins
        lines = [f"{plugin.slot.value}: {plugin.name} v{plugin.version}" for plugin in active]
        await interaction.response.send_message(
            "\n".join(lines) if lines else "No active plugins.",
            ephemeral=True,
            allowed_mentions=safe_allowed_mentions(),
        )

    @control_group.command(name="reload_plugin", description="Reload a plugin in development mode.")
    async def reload_plugin(self, interaction: discord.Interaction, plugin_name: str) -> None:
        if not await self._require_admin(interaction):
            return
        registry = self.services["plugin_registry"]
        result = await registry.reload_plugin(plugin_name, self.bot)
        await self.database.audit(
            event_type="plugin_reload",
            actor_id=interaction.user.id,
            guild_id=interaction.guild_id,
            details={"plugin_name": plugin_name, "result": result},
        )
        await interaction.response.send_message(result["message"], ephemeral=True, allowed_mentions=safe_allowed_mentions())

    @relay_group.command(name="routes", description="List active relay routes.")
    async def relay_routes(self, interaction: discord.Interaction) -> None:
        if not await self._require_admin(interaction):
            return
        routes = await self.database.list_relay_routes(interaction.guild_id)
        if not routes:
            await interaction.response.send_message("No active relay routes.", ephemeral=True)
            return
        lines = [
            f"{route.id}: <#{route.source_channel_id}> -> <#{route.destination_channel_id}> ({route.direction})"
            for route in routes
        ]
        await interaction.response.send_message(
            "\n".join(lines),
            ephemeral=True,
            allowed_mentions=safe_allowed_mentions(),
        )

    @relay_group.command(name="add", description="Add a relay route.")
    async def relay_add(
        self,
        interaction: discord.Interaction,
        source_channel: discord.TextChannel,
        destination_channel: discord.TextChannel,
        direction: Literal["one_way", "bidirectional"],
    ) -> None:
        if not await self._require_admin(interaction):
            return
        if interaction.guild_id is None:
            await interaction.response.send_message("Relay routes can only be configured in a guild.", ephemeral=True)
            return
        route = await self.database.add_relay_route(
            guild_id=interaction.guild_id,
            source_channel_id=source_channel.id,
            destination_channel_id=destination_channel.id,
            direction=direction,
            created_by=interaction.user.id,
        )
        await self.database.audit(
            event_type="relay_route_created",
            actor_id=interaction.user.id,
            guild_id=interaction.guild_id,
            details={
                "route_id": route.id,
                "source_channel_id": source_channel.id,
                "destination_channel_id": destination_channel.id,
                "direction": direction,
            },
        )
        await interaction.response.send_message(
            f"Added route {route.id}: #{source_channel.name} -> #{destination_channel.name} ({direction}).",
            ephemeral=True,
            allowed_mentions=safe_allowed_mentions(),
        )

    @relay_group.command(name="remove", description="Disable a relay route.")
    async def relay_remove(self, interaction: discord.Interaction, route_id: int) -> None:
        if not await self._require_admin(interaction):
            return
        removed = await self.database.remove_relay_route(route_id)
        await self.database.audit(
            event_type="relay_route_removed",
            actor_id=interaction.user.id,
            guild_id=interaction.guild_id,
            details={"route_id": route_id, "removed": removed},
        )
        await interaction.response.send_message(
            f"Route {route_id} {'removed' if removed else 'was not found'}.",
            ephemeral=True,
            allowed_mentions=safe_allowed_mentions(),
        )

    @relay_group.command(name="test", description="Send a test relay message for a route.")
    async def relay_test(self, interaction: discord.Interaction, route_id: int) -> None:
        if not await self._require_admin(interaction):
            return
        route = await self.database.get_route(route_id)
        if route is None or not route.enabled:
            await interaction.response.send_message("That route is not active.", ephemeral=True)
            return
        destination = self.bot.get_channel(route.destination_channel_id)
        if destination is None:
            destination = await self.bot.fetch_channel(route.destination_channel_id)
        if not isinstance(destination, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            await interaction.response.send_message("The destination channel is not messageable.", ephemeral=True)
            return
        sent = await destination.send(
            f"**Relay test** — from <#{route.source_channel_id}>",
            allowed_mentions=safe_allowed_mentions(),
            suppress_embeds=True,
        )
        await self.database.record_message_map(
            source_message_id=sent.id,
            source_channel_id=route.source_channel_id,
            destination_message_id=sent.id,
            destination_channel_id=route.destination_channel_id,
            route_id=route.id,
        )
        await self.database.audit(
            event_type="relay_route_tested",
            actor_id=interaction.user.id,
            guild_id=interaction.guild_id,
            channel_id=route.destination_channel_id,
            message_id=sent.id,
            details={"route_id": route_id},
        )
        await interaction.response.send_message("Test message sent.", ephemeral=True)


class AdminConfigPlugin(BasePlugin):
    name = "admin_config"
    slot = PluginSlot.ADMIN_CONFIG
    version = "0.1.0"
    enabled_by_default = True
    dependencies = ["relay_core"]
    config_schema = {"admin_only": {"type": "boolean", "default": True}}

    def __init__(self):
        self.cog: AdminConfigCog | None = None

    async def setup(self, bot: commands.Bot, services: dict[str, Any]) -> None:
        self.cog = AdminConfigCog(bot, services=services, logger=logging.getLogger("loki.admin"))
        await bot.add_cog(self.cog)

    async def teardown(self) -> None:
        self.cog = None

    async def healthcheck(self) -> dict[str, Any]:
        return {"ok": True, "plugin": self.name, "slot": self.slot.value}

    def commands(self) -> list[str]:
        return [
            "/bot status",
            "/bot plugins",
            "/bot reload_plugin",
            "/relay routes",
            "/relay add",
            "/relay remove",
            "/relay test",
        ]
