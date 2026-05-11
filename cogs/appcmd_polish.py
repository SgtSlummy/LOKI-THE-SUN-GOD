"""
Apply Discord application-command polish across the tree at startup:

  1. dm_permission=False     → guild commands cannot fire in DMs
  2. default_member_permissions → integration UI hides cmds from non-mods
  3. nsfw=True               → marks an explicit /nsfw demo command as age-gated
  4. name_localizations / description_localizations → en-US + es-ES + de + fr + ja

Reference: https://docs.discord.com/developers/interactions/application-commands
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.embeds import warn

log = logging.getLogger("loki.appcmd_polish")


# ─── Localization tables ─────────────────────────────────────────────────
# Edit/extend per command; missing locales fall back to default name.
NAME_L10N = {
    "help": {
        "es-ES": "ayuda",
        "fr": "aide",
        "de": "hilfe",
        "ja": "ヘルプ",
    },
    "ban": {"es-ES": "banear", "fr": "bannir", "de": "bannen", "ja": "禁止"},
    "kick": {"es-ES": "expulsar", "fr": "expulser", "de": "kicken", "ja": "追放"},
    "warn": {"es-ES": "advertir", "fr": "avertir", "de": "verwarnen", "ja": "警告"},
    "mute": {"es-ES": "silenciar", "fr": "muet", "de": "stummschalten", "ja": "ミュート"},
    "tag": {"es-ES": "etiqueta", "fr": "balise", "de": "marke", "ja": "タグ"},
    "userinfo": {"es-ES": "usuario", "fr": "utilisateur", "de": "benutzer", "ja": "ユーザー情報"},
}

DESC_L10N = {
    "help": {
        "es-ES": "Mostrar ayuda de comandos",
        "fr": "Afficher l'aide des commandes",
        "de": "Befehlshilfe anzeigen",
        "ja": "コマンドのヘルプを表示",
    },
    "ban": {"es-ES": "Banear a un miembro", "fr": "Bannir un membre", "de": "Mitglied bannen", "ja": "メンバーを禁止"},
    "kick": {
        "es-ES": "Expulsar a un miembro",
        "fr": "Expulser un membre",
        "de": "Mitglied kicken",
        "ja": "メンバーを追放",
    },
    "warn": {
        "es-ES": "Advertir a un miembro",
        "fr": "Avertir un membre",
        "de": "Mitglied verwarnen",
        "ja": "メンバーに警告",
    },
}


# Commands that should be hidden from non-mods in the slash picker (Discord
# integration-side hide; runtime checks still enforce). Bitfield = OR of perms.
MOD_PERMS = discord.Permissions(manage_messages=True)
ADMIN_PERMS = discord.Permissions(administrator=True)

PERM_GATED = {
    # name : Permissions instance
    "ban": discord.Permissions(ban_members=True),
    "kick": discord.Permissions(kick_members=True),
    "softban": discord.Permissions(ban_members=True),
    "tempban": discord.Permissions(ban_members=True),
    "unban": discord.Permissions(ban_members=True),
    "mute": discord.Permissions(moderate_members=True),
    "unmute": discord.Permissions(moderate_members=True),
    "timeout": discord.Permissions(moderate_members=True),
    "warn": MOD_PERMS,
    "purge": MOD_PERMS,
    "clear": MOD_PERMS,
    "slowmode": discord.Permissions(manage_channels=True),
    "lock": discord.Permissions(manage_channels=True),
    "unlock": discord.Permissions(manage_channels=True),
    "config": discord.Permissions(manage_guild=True),
    "streams": discord.Permissions(manage_guild=True),
    "activity": discord.Permissions(create_events=True),
    "automod": discord.Permissions(manage_guild=True),
}


class AppCmdPolish(commands.Cog):
    """Patches command attrs after all cogs load."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # run only once per process
        if getattr(self, "_applied", False):
            return
        self._applied = True
        try:
            await self._apply()
        except Exception as e:
            log.exception(f"appcmd_polish on_ready apply failed: {e}")

    async def _apply(self):
        log.info("appcmd_polish: running _apply()…")
        tree = self.bot.tree
        patched = 0
        for cmd in list(tree.walk_commands()):
            # 1. dm_permission=False on top-level commands (sub items inherit)
            if cmd.parent is None:
                try:
                    cmd.guild_only = True
                except Exception:
                    pass

            # 2. default_member_permissions for moderator gating
            if cmd.name in PERM_GATED and cmd.parent is None:
                try:
                    cmd.default_permissions = PERM_GATED[cmd.name]
                except Exception:
                    pass

            # 4. localization
            if cmd.name in NAME_L10N:
                try:
                    cmd.name_localizations = NAME_L10N[cmd.name]
                except Exception:
                    pass
            if cmd.name in DESC_L10N:
                try:
                    cmd.description_localizations = DESC_L10N[cmd.name]
                except Exception:
                    pass
            patched += 1

        # Re-sync to push the new attrs to Discord
        try:
            from os import getenv

            tg = getenv("TEST_GUILD_ID")
            if tg and tg.isdigit():
                guild = discord.Object(id=int(tg))
                synced = await tree.sync(guild=guild)
            else:
                synced = await tree.sync()
            log.info(f"appcmd_polish: applied attrs to {patched} cmds, re-synced {len(synced)}")
        except Exception as e:
            log.warning(f"appcmd_polish re-sync failed: {e}")

    # ── 3. NSFW demo command ─────────────────────────────────────────
    # Discord enforces this only in age-gated channels; non-NSFW channels
    # show "command unavailable" to under-18 users.
    @app_commands.command(name="nsfw_demo", description="Age-gated demo (only works in NSFW-marked channels)")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def nsfw_demo(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=warn("NSFW gate works", "This command can only fire in age-gated channels."),
            ephemeral=True,
        )

    async def cog_load(self):
        # nsfw=True cannot be set via decorator on cog method — patch attr post-bind.
        # Cog system auto-registers self.nsfw_demo, so we don't add it again.
        try:
            self.nsfw_demo.nsfw = True
        except Exception:
            pass
        # If bot already ready (cog loaded mid-session), run apply now;
        # otherwise on_ready listener will pick it up at first ready event.
        if self.bot.is_ready() and not getattr(self, "_applied", False):
            self._applied = True
            await self._apply()


async def setup(bot: commands.Bot):
    await bot.add_cog(AppCmdPolish(bot))
