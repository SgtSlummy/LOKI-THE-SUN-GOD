"""
Fillable Discord modal forms.

Admins create a form, configure fields, and post a button panel.
Members click the button, complete the modal, and the response is posted
to the configured destination channel.
"""

import json

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.helpers import now


class DynamicFormModal(discord.ui.Modal):
    def __init__(self, guild_id: int, form_name: str, title: str, fields: list, target_channel_id: int):
        super().__init__(title=title[:45])
        self.guild_id = guild_id
        self.form_name = form_name
        self.target_channel_id = target_channel_id
        self._field_specs = []
        for field in fields[:5]:
            label = str(field.get("label", "Field"))[:45]
            style = discord.TextStyle.paragraph if field.get("style") == "long" else discord.TextStyle.short
            kwargs = {
                "label": label,
                "style": style,
                "required": field.get("required", True),
                "placeholder": str(field.get("placeholder", ""))[:100] or None,
                "max_length": int(field.get("max_length", 1024)),
                "default": field.get("default") or None,
            }
            if field.get("min_length") not in (None, ""):
                try:
                    kwargs["min_length"] = int(field["min_length"])
                except (TypeError, ValueError):
                    pass
            self.add_item(discord.ui.TextInput(**kwargs))
            self._field_specs.append(field)

    async def on_submit(self, interaction: discord.Interaction):
        import re as _re

        for spec, item in zip(self._field_specs, self.children):
            pattern = spec.get("pattern")
            if pattern and item.value:
                try:
                    if not _re.fullmatch(pattern, item.value):
                        return await interaction.response.send_message(
                            f"Field `{item.label}` does not match the required format.",
                            ephemeral=True,
                        )
                except _re.error:
                    pass

        answers = {item.label: item.value for item in self.children}
        async with db.get() as c:
            await c.execute(
                "INSERT INTO form_responses(guild_id,form_name,user_id,responses,submitted_at) VALUES(?,?,?,?,?)",
                (
                    self.guild_id,
                    self.form_name,
                    interaction.user.id,
                    json.dumps(answers),
                    now(),
                ),
            )
            await c.commit()

        channel = interaction.client.get_channel(self.target_channel_id)
        if channel:
            embed = discord.Embed(
                title=f"Form response: {self.form_name}",
                color=0x5865F2,
                timestamp=discord.utils.utcnow(),
            )
            embed.set_author(
                name=str(interaction.user),
                icon_url=interaction.user.display_avatar.url,
            )
            for label, value in answers.items():
                embed.add_field(name=label, value=value[:1024] or "(empty)", inline=False)
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass

        await interaction.response.send_message("Form submitted.", ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(
            f"Unable to submit form: {error}",
            ephemeral=True,
        )


class FormPanelView(discord.ui.View):
    """Persistent view for saved form buttons."""

    def __init__(self, guild_id: int, form_name: str, button_label: str = "Fill Form"):
        super().__init__(timeout=None)
        button = discord.ui.Button(
            label=button_label[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"form::{guild_id}::{form_name}",
        )
        button.callback = self._callback
        self.add_item(button)
        self.guild_id = guild_id
        self.form_name = form_name

    async def _callback(self, interaction: discord.Interaction):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT title, fields, target_channel_id FROM forms WHERE guild_id=? AND name=?",
                (self.guild_id, self.form_name),
            )
            row = await cur.fetchone()
        if not row:
            return await interaction.response.send_message("That form no longer exists.", ephemeral=True)
        title, fields_json, target_channel_id = row
        try:
            fields = json.loads(fields_json or "[]")
        except json.JSONDecodeError:
            fields = []
        if not fields:
            return await interaction.response.send_message(
                "This form has no fields configured yet.",
                ephemeral=True,
            )
        modal = DynamicFormModal(self.guild_id, self.form_name, title, fields, target_channel_id)
        await interaction.response.send_modal(modal)


class Forms(commands.Cog):
    """Interactive fillable forms using Discord modals."""

    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        async with db.get() as c:
            cur = await c.execute("SELECT guild_id, name, button_label FROM forms")
            rows = await cur.fetchall()
        for guild_id, name, label in rows:
            self.bot.add_view(FormPanelView(guild_id, name, label or "Fill Form"))

    @commands.hybrid_group(
        name="form",
        invoke_without_command=True,
        description="Manage application and intake forms",
    )
    @commands.has_permissions(manage_guild=True)
    async def form(self, ctx):
        await ctx.send(
            "Form commands: `create`, `addfield`, `settarget`, `setlabel`, `panel`, "
            "`list`, `info`, `delete`, `responses`."
        )

    @form.command(name="create", description="Create a new form shell")
    @app_commands.describe(
        name="Internal form key used for later management",
        title="Public title shown to members",
    )
    @commands.has_permissions(manage_guild=True)
    async def form_create(self, ctx, name: str, *, title: str = None):
        title = title or name
        async with db.get() as c:
            try:
                await c.execute(
                    "INSERT INTO forms(guild_id,name,title,fields) VALUES(?,?,?,?)",
                    (ctx.guild.id, name.lower(), title, "[]"),
                )
                await c.commit()
            except Exception:
                return await ctx.send(f"A form named `{name}` already exists.")
        await ctx.send(
            f"Created form `{name}` with title **{title}**.\n"
            f"Next: `!form addfield {name} <label> [short|long] [yes|no] [placeholder]`\n"
            f"Then: `!form settarget {name} #channel`"
        )

    @form.command(name="addfield", description="Add a field to an existing form")
    @app_commands.describe(
        form_name="Saved form that should receive the field",
        label="Field label members will see",
        style="Use short for one-line input or long for paragraphs",
        required="Whether members must complete this field",
        placeholder="Optional helper text shown before typing",
    )
    @commands.has_permissions(manage_guild=True)
    async def form_addfield(
        self,
        ctx,
        form_name: str,
        label: str,
        style: str = "short",
        required: str = "yes",
        *,
        placeholder: str = "",
    ):
        style = "long" if style.lower() in ("long", "paragraph", "l") else "short"
        is_required = required.lower() not in ("no", "false", "n", "0")
        async with db.get() as c:
            cur = await c.execute(
                "SELECT fields FROM forms WHERE guild_id=? AND name=?",
                (ctx.guild.id, form_name.lower()),
            )
            row = await cur.fetchone()
        if not row:
            return await ctx.send(f"No form named `{form_name}` was found.")
        fields = json.loads(row[0] or "[]")
        if len(fields) >= 5:
            return await ctx.send("Forms can only have up to 5 fields because of Discord modal limits.")
        fields.append(
            {
                "label": label,
                "style": style,
                "required": is_required,
                "placeholder": placeholder,
            }
        )
        async with db.get() as c:
            await c.execute(
                "UPDATE forms SET fields=? WHERE guild_id=? AND name=?",
                (json.dumps(fields), ctx.guild.id, form_name.lower()),
            )
            await c.commit()
        required_text = "required" if is_required else "optional"
        await ctx.send(f"Added field **{label}** to `{form_name}` ({style}, {required_text}).")

    @form.command(name="settarget", description="Set the destination channel for form responses")
    @app_commands.describe(
        form_name="Saved form whose response destination should change",
        channel="Channel where submitted responses should be posted",
    )
    @commands.has_permissions(manage_guild=True)
    async def form_settarget(self, ctx, form_name: str, channel: discord.TextChannel):
        async with db.get() as c:
            cur = await c.execute(
                "UPDATE forms SET target_channel_id=? WHERE guild_id=? AND name=?",
                (channel.id, ctx.guild.id, form_name.lower()),
            )
            await c.commit()
        if not cur.rowcount:
            return await ctx.send(f"No form named `{form_name}` was found.")
        await ctx.send(f"Responses for `{form_name}` will now go to {channel.mention}.")

    @form.command(name="setlabel", description="Update the public button label for a form")
    @app_commands.describe(
        form_name="Saved form whose button text should change",
        label="Button text members will click",
    )
    @commands.has_permissions(manage_guild=True)
    async def form_setlabel(self, ctx, form_name: str, *, label: str):
        async with db.get() as c:
            cur = await c.execute(
                "UPDATE forms SET button_label=? WHERE guild_id=? AND name=?",
                (label[:80], ctx.guild.id, form_name.lower()),
            )
            await c.commit()
        if not cur.rowcount:
            return await ctx.send(f"No form named `{form_name}` was found.")
        await ctx.send(f"Updated the button label for `{form_name}` to `{label[:80]}`.")

    @form.command(name="panel", description="Post the public button panel for a form")
    @app_commands.describe(
        form_name="Saved form whose panel should be posted",
        channel="Optional channel where the panel should be posted",
        description="Supporting text shown above the form button",
    )
    @commands.has_permissions(manage_guild=True)
    async def form_panel(
        self,
        ctx,
        form_name: str,
        channel: discord.TextChannel = None,
        *,
        description: str = "Click the button below to fill out this form.",
    ):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT title, fields, target_channel_id, button_label FROM forms WHERE guild_id=? AND name=?",
                (ctx.guild.id, form_name.lower()),
            )
            row = await cur.fetchone()
        if not row:
            return await ctx.send(f"No form named `{form_name}` was found.")
        title, fields_json, target_channel_id, button_label = row
        fields = json.loads(fields_json or "[]")
        if not fields:
            return await ctx.send(f"Add at least one field before posting `{form_name}`.")
        if not target_channel_id:
            return await ctx.send(f"Set a response channel first with `!form settarget {form_name} #channel`.")
        target = channel or ctx.channel
        embed = discord.Embed(title=title, description=description, color=0x5865F2)
        embed.set_footer(text=f"Form key: {form_name}")
        view = FormPanelView(ctx.guild.id, form_name.lower(), button_label or "Fill Form")
        self.bot.add_view(view)
        await target.send(embed=embed, view=view)
        if target != ctx.channel:
            await ctx.send(f"Posted the `{form_name}` panel in {target.mention}.")

    @form.command(name="list", description="List forms configured for this server")
    @commands.has_permissions(manage_guild=True)
    async def form_list(self, ctx):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT name, title, target_channel_id FROM forms WHERE guild_id=? ORDER BY name",
                (ctx.guild.id,),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send("No forms are configured for this server.")
        embed = discord.Embed(title="Forms", color=0x5865F2)
        for name, title, channel_id in rows:
            channel = self.bot.get_channel(channel_id) if channel_id else None
            target_text = channel.mention if channel else "no target set"
            embed.add_field(
                name=f"`{name}` | {title}",
                value=f"Responses: {target_text}",
                inline=False,
            )
        await ctx.send(embed=embed)

    @form.command(name="info", description="Show details for a saved form")
    @app_commands.describe(form_name="Saved form you want to inspect")
    @commands.has_permissions(manage_guild=True)
    async def form_info(self, ctx, form_name: str):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT title, fields, target_channel_id, button_label FROM forms WHERE guild_id=? AND name=?",
                (ctx.guild.id, form_name.lower()),
            )
            row = await cur.fetchone()
        if not row:
            return await ctx.send(f"No form named `{form_name}` was found.")
        title, fields_json, channel_id, button_label = row
        fields = json.loads(fields_json or "[]")
        channel = self.bot.get_channel(channel_id) if channel_id else None
        embed = discord.Embed(title=f"Form: {title}", color=0x5865F2)
        embed.add_field(name="Key", value=form_name, inline=True)
        embed.add_field(name="Button label", value=button_label or "Fill Form", inline=True)
        embed.add_field(name="Response channel", value=channel.mention if channel else "not set", inline=False)
        field_lines = [
            f"{index + 1}. **{field['label']}** "
            f"[{field.get('style', 'short')}, {'required' if field.get('required') else 'optional'}]"
            for index, field in enumerate(fields)
        ]
        embed.add_field(
            name="Fields",
            value="\n".join(field_lines) if field_lines else "No fields configured.",
            inline=False,
        )
        await ctx.send(embed=embed)

    @form.command(name="delete", description="Delete a saved form")
    @app_commands.describe(form_name="Saved form that should be removed")
    @commands.has_permissions(manage_guild=True)
    async def form_delete(self, ctx, form_name: str):
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM forms WHERE guild_id=? AND name=?",
                (ctx.guild.id, form_name.lower()),
            )
            await c.commit()
        if cur.rowcount:
            await ctx.send(f"Deleted form `{form_name}`.")
        else:
            await ctx.send(f"No form named `{form_name}` was found.")

    @form.command(name="responses", description="Review recent submissions for a form")
    @app_commands.describe(
        form_name="Saved form whose responses you want to review",
        count="How many recent submissions should be shown",
    )
    @commands.has_permissions(manage_messages=True)
    async def form_responses(self, ctx, form_name: str, count: int = 5):
        async with db.get() as c:
            cur = await c.execute(
                "SELECT user_id, responses, submitted_at FROM form_responses "
                "WHERE guild_id=? AND form_name=? ORDER BY submitted_at DESC LIMIT ?",
                (ctx.guild.id, form_name.lower(), count),
            )
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send(f"No saved responses were found for `{form_name}`.")
        embed = discord.Embed(title=f"Recent responses: {form_name}", color=0x5865F2)
        for user_id, response_json, submitted_at in rows:
            member = ctx.guild.get_member(user_id)
            author_name = str(member) if member else str(user_id)
            try:
                answers = json.loads(response_json)
                preview = " | ".join(f"{key}: {str(value)[:30]}" for key, value in answers.items())
            except Exception:
                preview = response_json[:100]
            embed.add_field(
                name=f"{author_name} <t:{submitted_at}:R>",
                value=preview[:200],
                inline=False,
            )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Forms(bot))
