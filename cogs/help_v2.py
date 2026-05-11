"""
Rich help with autocomplete. Replaces the default DefaultHelpCommand.

`/help` opens a paginated category browser.
`/help <command>` shows full info: description, aliases, usage, slash signature.
Typing `/help command:<partial>` autocompletes against all loaded commands.
"""

from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.command_descriptions import option_description_for
from utils.embeds import Paginator, err, info


def _cmd_signature(cmd: commands.Command) -> str:
    parent = cmd.full_parent_name
    name = f"{parent} {cmd.name}".strip()
    return f"{name} {cmd.signature}".strip()


def _cmd_doc(cmd: commands.Command) -> str:
    return cmd.help or cmd.short_doc or "*No description.*"


class Help(commands.Cog):
    """Help with autocomplete and category browsing."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.help_command = None

    async def cmd_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        current = (current or "").lower()
        names = []
        for cmd in self.bot.walk_commands():
            if cmd.hidden:
                continue
            full = (cmd.full_parent_name + " " + cmd.name).strip()
            if not current or current in full.lower():
                names.append(full)
        names = sorted(set(names))[:25]
        return [app_commands.Choice(name=name, value=name) for name in names]

    @commands.hybrid_command(name="help", aliases=["h"], description="Show command help")
    @app_commands.describe(command="Specific command (optional)")
    async def help_cmd(self, ctx: commands.Context, *, command: Optional[str] = None):
        if command:
            cmd = self.bot.get_command(command)
            if not cmd:
                return await ctx.send(embed=err(f"No command `{command}`."), ephemeral=True)
            return await ctx.send(embed=self._cmd_embed(cmd, ctx))

        cogs: dict[str, list[commands.Command]] = {}
        for cmd in self.bot.walk_commands():
            if cmd.hidden or cmd.parent is not None:
                continue
            cogs.setdefault(cmd.cog_name or "Misc", []).append(cmd)

        embeds: list[discord.Embed] = []
        for cog_name in sorted(cogs):
            cmds = sorted(cogs[cog_name], key=lambda c: c.name)
            lines = []
            for cmd in cmds:
                short = cmd.short_doc or "-"
                lines.append(f"**`{cmd.name}`** - {short}")
            chunks = [lines[index : index + 12] for index in range(0, len(lines), 12)]
            for number, chunk in enumerate(chunks, 1):
                embed = info(
                    f"{cog_name}" + (f" ({number}/{len(chunks)})" if len(chunks) > 1 else ""),
                    "\n".join(chunk),
                )
                embed.set_footer(text=f"Use /help <command> for details - {len(self.bot.commands)} top-level commands")
                embeds.append(embed)

        if not embeds:
            return await ctx.send(embed=err("No commands available."))

        view = Paginator(embeds, author_id=ctx.author.id)
        await ctx.send(embed=embeds[0], view=view)

    @help_cmd.autocomplete("command")
    async def _help_ac(self, interaction, current):
        return await self.cmd_autocomplete(interaction, current)

    def _cmd_embed(self, cmd: commands.Command, ctx: commands.Context) -> discord.Embed:
        prefix = ctx.clean_prefix if ctx.prefix else "!"
        embed = info(f"`{prefix}{_cmd_signature(cmd)}`", _cmd_doc(cmd))
        if cmd.aliases:
            embed.add_field(name="Aliases", value=", ".join(f"`{alias}`" for alias in cmd.aliases), inline=False)
        if isinstance(cmd, commands.Group):
            subcommands = [f"`{subcommand.name}` - {subcommand.short_doc or '-'}" for subcommand in cmd.commands]
            if subcommands:
                embed.add_field(name="Subcommands", value="\n".join(subcommands), inline=False)

        option_rows = self._slash_option_rows(cmd)
        if option_rows:
            preview = option_rows[:8]
            if len(option_rows) > 8:
                preview.append(f"...and {len(option_rows) - 8} more")
            embed.add_field(name="Slash options", value="\n".join(preview), inline=False)

        slash = "Available as `/`" if isinstance(cmd, (commands.HybridCommand, commands.HybridGroup)) else "Prefix only"
        embed.add_field(name="Slash", value=slash, inline=True)
        embed.add_field(name="Cog", value=cmd.cog_name or "-", inline=True)
        return embed

    def _slash_option_rows(self, cmd: commands.Command) -> list[str]:
        app_command = getattr(cmd, "app_command", None)
        if app_command is None:
            return []

        rows = []
        for param in getattr(app_command, "parameters", []):
            type_name = getattr(getattr(param, "type", None), "name", "text").lower()
            choices = [
                str(getattr(choice, "name", None) or getattr(choice, "value", ""))
                for choice in getattr(param, "choices", []) or []
            ]
            choices = [choice for choice in choices if choice]
            description = option_description_for(
                getattr(cmd, "qualified_name", cmd.name),
                getattr(param, "name", ""),
                type_name,
                getattr(param, "description", None),
                choices,
            )
            badges = [type_name or "text", "required" if getattr(param, "required", False) else "optional"]
            if getattr(param, "autocomplete", False):
                badges.append("autocomplete")
            row = f"`{param.name}` ({', '.join(badges)}) - {description}"
            if choices:
                row += f" Choices: {', '.join(choices[:5])}"
            rows.append(row)
        return rows


async def setup(bot):
    await bot.add_cog(Help(bot))
