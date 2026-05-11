"""
Embed factories and reusable Views for consistent bot output.

Usage:
    from utils.embeds import ok, err, info, ConfirmView, ToggleView, AdminConsole

    await ctx.send(embed=ok("Saved."))
    await ctx.send(embed=info("Levels", "Current XP: 1234"))

    view = ConfirmView(author_id=ctx.author.id)
    msg = await ctx.send(embed=info("Delete?", "Type yes/no."), view=view)
    await view.wait()
    if view.value: ...
"""

from __future__ import annotations

from typing import Awaitable, Callable

import discord

COLOR_OK = 0x22C55E
COLOR_ERR = 0xEF4444
COLOR_INFO = 0x5865F2
COLOR_WARN = 0xF59E0B
COLOR_NEUTRAL = 0x2B2D31


def _embed(title: str, desc: str, color: int) -> discord.Embed:
    return discord.Embed(title=title, description=desc, color=color)


def ok(msg: str, title: str = "Success") -> discord.Embed:
    return _embed(title, msg, COLOR_OK)


def err(msg: str, title: str = "Error") -> discord.Embed:
    return _embed(title, msg, COLOR_ERR)


def warn(msg: str, title: str = "Warning") -> discord.Embed:
    return _embed(title, msg, COLOR_WARN)


def info(title: str, msg: str = "") -> discord.Embed:
    return _embed(title, msg, COLOR_INFO)


def neutral(title: str, msg: str = "") -> discord.Embed:
    return _embed(title, msg, COLOR_NEUTRAL)


class ConfirmView(discord.ui.View):
    """Yes/No confirm. .value is True/False/None after await wait()."""

    def __init__(self, *, author_id: int, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your prompt.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.value = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.value = False
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class ToggleView(discord.ui.View):
    """
    Generic toggle row. Pass {label: bool} dict + on_change callback.
    on_change(interaction, key, new_value) -> coroutine.
    """

    def __init__(
        self,
        states: dict[str, bool],
        on_change: Callable[[discord.Interaction, str, bool], Awaitable[None]],
        *,
        author_id: int | None = None,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.states = dict(states)
        self.on_change = on_change
        self.author_id = author_id
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        for label, enabled in self.states.items():
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary,
                custom_id=f"toggle:{label}",
            )
            button.callback = self._make_cb(label)
            self.add_item(button)

    def _make_cb(self, key: str):
        async def cb(interaction: discord.Interaction):
            if self.author_id and interaction.user.id != self.author_id:
                return await interaction.response.send_message("Not for you.", ephemeral=True)
            self.states[key] = not self.states[key]
            await self.on_change(interaction, key, self.states[key])
            self._rebuild()
            await interaction.response.edit_message(view=self)

        return cb


class Paginator(discord.ui.View):
    """Paginate a list of embeds with Prev/Next/Stop."""

    def __init__(self, embeds: list[discord.Embed], *, author_id: int, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.idx = 0
        self.author_id = author_id
        self._update_state()

    def _update_state(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label == "<":
                    child.disabled = self.idx == 0
                elif child.label == ">":
                    child.disabled = self.idx >= len(self.embeds) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Not your paginator.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="<", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.idx = max(0, self.idx - 1)
        self._update_state()
        await interaction.response.edit_message(embed=self.embeds[self.idx], view=self)

    @discord.ui.button(label=">", style=discord.ButtonStyle.secondary)
    async def nxt(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.idx = min(len(self.embeds) - 1, self.idx + 1)
        self._update_state()
        await interaction.response.edit_message(embed=self.embeds[self.idx], view=self)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def stop_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()


class AdminConsole(discord.ui.View):
    """
    Admin-only embed with a row of named action buttons.
    Pass actions: dict[label] = coroutine(interaction).
    """

    def __init__(
        self,
        actions: dict[str, Callable[[discord.Interaction], Awaitable[None]]],
        *,
        permission: str = "manage_guild",
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.permission = permission
        for label, coro in actions.items():
            button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
            button.callback = self._wrap(coro)
            self.add_item(button)

    def _wrap(self, coro):
        async def cb(interaction: discord.Interaction):
            perms = interaction.user.guild_permissions
            if not getattr(perms, self.permission, False) and not perms.administrator:
                return await interaction.response.send_message(
                    f"Need `{self.permission}` permission.",
                    ephemeral=True,
                )
            await coro(interaction)

        return cb
