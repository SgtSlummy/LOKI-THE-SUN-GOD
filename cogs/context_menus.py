"""
Discord application command extensions: user + message context menus.

These appear in Discord's right-click → Apps menu, separate from /slash commands.
They don't count against the 100 slash-command cap (5 user + 5 message limits per app).

Reference: https://docs.discord.com/developers/interactions/application-commands

User context menus (right-click member → Apps):
  - User Info
  - Add Note
  - Quick Mute (10m)
  - Show Avatar
  - Warn

Message context menus (right-click message → Apps):
  - Star to Starboard
  - Translate to English
  - Save as Tag
  - Quote to Channel
  - Delete + Warn Author
"""

from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import err, info, ok
from utils.helpers import safe_send


# ─── Helper: write modal-style note ──────────────────────────────────────
class NoteModal(discord.ui.Modal, title="Add staff note"):
    note = discord.ui.TextInput(label="Note", style=discord.TextStyle.paragraph, max_length=1024, required=True)

    def __init__(self, target: discord.Member):
        super().__init__()
        self.target = target

    async def on_submit(self, interaction: discord.Interaction):
        async with db.get() as c:
            await c.execute(
                "INSERT INTO notes(guild_id,user_id,mod_id,content,created_at) VALUES(?,?,?,?,?)",
                (interaction.guild_id, self.target.id, interaction.user.id, str(self.note), int(time.time())),
            )
            await c.commit()
        await interaction.response.send_message(
            embed=ok(f"Note added for {self.target.mention}", "Note saved"),
            ephemeral=True,
        )


class WarnModal(discord.ui.Modal, title="Warn user"):
    reason = discord.ui.TextInput(label="Reason", max_length=400, required=True)

    def __init__(self, target: discord.Member):
        super().__init__()
        self.target = target

    async def on_submit(self, interaction: discord.Interaction):
        async with db.get() as c:
            await c.execute(
                "INSERT INTO warnings(guild_id,user_id,mod_id,reason,created_at) VALUES(?,?,?,?,?)",
                (interaction.guild_id, self.target.id, interaction.user.id, str(self.reason), int(time.time())),
            )
            await c.commit()
            cur = await c.execute(
                "SELECT COUNT(*) FROM warnings WHERE guild_id=? AND user_id=?",
                (interaction.guild_id, self.target.id),
            )
            count = (await cur.fetchone())[0]
        try:
            await self.target.send(f"You were warned in {interaction.guild.name}: {self.reason}")
        except discord.Forbidden:
            pass
        await interaction.response.send_message(
            embed=ok(f"Warned {self.target.mention} (total: {count})"),
            ephemeral=True,
        )


class SaveTagModal(discord.ui.Modal, title="Save as tag"):
    name = discord.ui.TextInput(label="Tag name", max_length=40, required=True, placeholder="lowercase, no spaces")

    def __init__(self, content: str):
        super().__init__()
        self.content = content[:1900]

    async def on_submit(self, interaction: discord.Interaction):
        slug = str(self.name).strip().lower().replace(" ", "_")
        async with db.get() as c:
            try:
                await c.execute(
                    "INSERT INTO tags(guild_id,name,content,owner_id,uses,created_at) VALUES(?,?,?,?,0,?)",
                    (interaction.guild_id, slug, self.content, interaction.user.id, int(time.time())),
                )
                await c.commit()
            except Exception as e:
                return await interaction.response.send_message(
                    embed=err(f"Tag exists or DB error: {e}"), ephemeral=True
                )
        await interaction.response.send_message(
            embed=ok(f"Saved as `{slug}`. Use `/tag {slug}` to recall."), ephemeral=True
        )


class QuoteChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, source_msg: discord.Message):
        super().__init__(
            channel_types=[discord.ChannelType.text, discord.ChannelType.news], placeholder="Pick target channel…"
        )
        self.source = source_msg

    async def callback(self, interaction: discord.Interaction):
        target = interaction.guild.get_channel(self.values[0].id)
        if not target:
            return await interaction.response.send_message(embed=err("Channel not found."), ephemeral=True)
        e = discord.Embed(
            description=self.source.content or "*(no text)*",
            color=0x5865F2,
            timestamp=self.source.created_at,
        )
        e.set_author(name=str(self.source.author), icon_url=self.source.author.display_avatar.url)
        e.add_field(name="Source", value=f"[Jump]({self.source.jump_url})", inline=True)
        if self.source.attachments:
            e.set_image(url=self.source.attachments[0].url)
        try:
            await safe_send(target, embed=e, dedupe_key=f"quote:{self.source.id}:{target.id}", dedupe_window=30)
            await interaction.response.send_message(embed=ok(f"Quoted to {target.mention}"), ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(embed=err("Missing perms in target channel."), ephemeral=True)


class QuoteView(discord.ui.View):
    def __init__(self, source_msg: discord.Message):
        super().__init__(timeout=120)
        self.add_item(QuoteChannelSelect(source_msg))


# ─── Cog ──────────────────────────────────────────────────────────────────
class ContextMenus(commands.Cog):
    """User + message context-menu commands (Discord right-click menu)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register context-menu commands programmatically (decorators only work
        # on module-level functions, not cog methods).
        self.user_info_ctx = app_commands.ContextMenu(name="User Info", callback=self.user_info_cb)
        self.add_note_ctx = app_commands.ContextMenu(name="Add Note", callback=self.add_note_cb)
        self.quick_mute_ctx = app_commands.ContextMenu(name="Quick Mute (10m)", callback=self.quick_mute_cb)
        self.show_avatar_ctx = app_commands.ContextMenu(name="Show Avatar", callback=self.show_avatar_cb)
        self.warn_user_ctx = app_commands.ContextMenu(name="Warn", callback=self.warn_user_cb)

        self.star_msg_ctx = app_commands.ContextMenu(name="Star to Starboard", callback=self.star_msg_cb)
        # NOTE: cogs/translate.py owns "Translate" message context menu — do not add a duplicate here.
        self.save_tag_ctx = app_commands.ContextMenu(name="Save as Tag", callback=self.save_tag_cb)
        self.quote_ch_ctx = app_commands.ContextMenu(name="Quote to Channel", callback=self.quote_ch_cb)
        self.del_warn_ctx = app_commands.ContextMenu(name="Delete + Warn", callback=self.del_warn_cb)

        for cmd in (
            self.user_info_ctx,
            self.add_note_ctx,
            self.quick_mute_ctx,
            self.show_avatar_ctx,
            self.warn_user_ctx,
            self.star_msg_ctx,
            self.save_tag_ctx,
            self.quote_ch_ctx,
            self.del_warn_ctx,
        ):
            self.bot.tree.add_command(cmd)

    def cog_unload(self):
        for cmd in (
            self.user_info_ctx,
            self.add_note_ctx,
            self.quick_mute_ctx,
            self.show_avatar_ctx,
            self.warn_user_ctx,
            self.star_msg_ctx,
            self.save_tag_ctx,
            self.quote_ch_ctx,
            self.del_warn_ctx,
        ):
            self.bot.tree.remove_command(cmd.name, type=cmd.type)

    # ── User context callbacks ────────────────────────────────────────
    async def user_info_cb(self, interaction: discord.Interaction, member: discord.Member):
        e = info(f"{member}", member.mention)
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="ID", value=str(member.id), inline=True)
        e.add_field(
            name="Joined",
            value=discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "—",
            inline=True,
        )
        e.add_field(name="Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
        roles = [r.mention for r in member.roles[1:]][:20]
        if roles:
            e.add_field(name=f"Roles ({len(member.roles) - 1})", value=" ".join(roles), inline=False)
        async with db.get() as c:
            cur = await c.execute(
                "SELECT COUNT(*) FROM warnings WHERE guild_id=? AND user_id=?", (interaction.guild_id, member.id)
            )
            warn_count = (await cur.fetchone())[0]
            cur = await c.execute(
                "SELECT COUNT(*) FROM notes WHERE guild_id=? AND user_id=?", (interaction.guild_id, member.id)
            )
            note_count = (await cur.fetchone())[0]
        e.add_field(name="Warnings", value=str(warn_count), inline=True)
        e.add_field(name="Staff notes", value=str(note_count), inline=True)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.checks.has_permissions(manage_messages=True)
    async def add_note_cb(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_modal(NoteModal(member))

    @app_commands.checks.has_permissions(moderate_members=True)
    async def quick_mute_cb(self, interaction: discord.Interaction, member: discord.Member):
        try:
            await member.timeout(
                discord.utils.utcnow() + discord.utils.timedelta(minutes=10)
                if hasattr(discord.utils, "timedelta")
                else __import__("datetime").timedelta(minutes=10),
                reason=f"Quick mute by {interaction.user}",
            )
            await interaction.response.send_message(embed=ok(f"Muted {member.mention} for 10m"), ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(embed=err("Missing perms or role hierarchy."), ephemeral=True)

    async def show_avatar_cb(self, interaction: discord.Interaction, member: discord.Member):
        e = info(f"{member}'s avatar")
        e.set_image(url=member.display_avatar.with_size(1024).url)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.checks.has_permissions(manage_messages=True)
    async def warn_user_cb(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_modal(WarnModal(member))

    # ── Message context callbacks ─────────────────────────────────────
    @app_commands.checks.has_permissions(manage_messages=True)
    async def star_msg_cb(self, interaction: discord.Interaction, message: discord.Message):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT starboard_channel FROM guild_config WHERE guild_id=?", (interaction.guild_id,)
            )
            row = await cur.fetchone()
        if not row or not row[0]:
            return await interaction.response.send_message(
                embed=err("No starboard channel set. Configure in dashboard → General."), ephemeral=True
            )
        ch = interaction.guild.get_channel(row[0])
        if not ch:
            return await interaction.response.send_message(embed=err("Starboard channel missing."), ephemeral=True)
        e = info(f"⭐ {message.author}", message.content or "*(no text)*")
        e.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        e.add_field(name="Source", value=f"[Jump]({message.jump_url})", inline=False)
        if message.attachments:
            e.set_image(url=message.attachments[0].url)
        try:
            async with db.get() as c:
                cur = await c.execute("SELECT star_message_id FROM starboard WHERE message_id=?", (message.id,))
                existing = await cur.fetchone()
            if existing:
                try:
                    star_msg = await ch.fetch_message(existing[0])
                    await star_msg.edit(content="⭐ Manual starboard", embed=e)
                except discord.NotFound:
                    star_msg = await ch.send(content="⭐ Manual starboard", embed=e)
                    async with db.get() as c:
                        await c.execute(
                            "INSERT OR REPLACE INTO starboard"
                            "(message_id,star_message_id,guild_id,stars) VALUES(?,?,?,?)",
                            (message.id, star_msg.id, interaction.guild_id, 1),
                        )
                        await c.commit()
            else:
                star_msg = await ch.send(content="⭐ Manual starboard", embed=e)
                async with db.get() as c:
                    await c.execute(
                        "INSERT INTO starboard(message_id,star_message_id,guild_id,stars) VALUES(?,?,?,?)",
                        (message.id, star_msg.id, interaction.guild_id, 1),
                    )
                    await c.commit()
            await interaction.response.send_message(embed=ok("Sent to starboard."), ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(embed=err("Missing perms in starboard channel."), ephemeral=True)

    async def translate_msg_cb(self, interaction: discord.Interaction, message: discord.Message):
        text = message.content
        if not text:
            return await interaction.response.send_message(embed=err("No text content."), ephemeral=True)
        # Use existing translate cog if loaded
        translate_cog = self.bot.get_cog("Translate") or self.bot.get_cog("Translator")
        if translate_cog and hasattr(translate_cog, "_translate"):
            try:
                out = await translate_cog._translate(text, "en")
                e = info("Translation", out)
            except Exception as ex:
                e = err(f"Translate failed: {ex}")
        else:
            # Fallback — just echo in code block, no real translation
            e = info("Original (translate cog missing)", f"```\n{text[:1900]}\n```")
        e.set_footer(text=f"Source: {message.author}")
        await interaction.response.send_message(embed=e, ephemeral=True)

    @app_commands.checks.has_permissions(manage_messages=True)
    async def save_tag_cb(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_modal(SaveTagModal(message.content or "*(no text)*"))

    @app_commands.checks.has_permissions(manage_messages=True)
    async def quote_ch_cb(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_message(
            embed=info("Pick target channel", "Quote will be posted as embed."),
            view=QuoteView(message),
            ephemeral=True,
        )

    @app_commands.checks.has_permissions(manage_messages=True)
    async def del_warn_cb(self, interaction: discord.Interaction, message: discord.Message):
        author = message.author if isinstance(message.author, discord.Member) else None
        try:
            await message.delete()
        except discord.Forbidden:
            return await interaction.response.send_message(embed=err("Cannot delete that message."), ephemeral=True)
        if not author:
            return await interaction.response.send_message(
                embed=ok("Deleted (author not in guild — no warn)."), ephemeral=True
            )
        async with db.get() as c:
            await c.execute(
                "INSERT INTO warnings(guild_id,user_id,mod_id,reason,created_at) VALUES(?,?,?,?,?)",
                (
                    interaction.guild_id,
                    author.id,
                    interaction.user.id,
                    "Deleted message via context menu",
                    int(time.time()),
                ),
            )
            await c.commit()
        try:
            await author.send(f"Your message in {interaction.guild.name} was removed and you received a warning.")
        except discord.Forbidden:
            pass
        await interaction.response.send_message(embed=ok(f"Deleted message + warned {author.mention}"), ephemeral=True)


async def setup(bot):
    await bot.add_cog(ContextMenus(bot))
