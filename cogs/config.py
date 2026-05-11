import discord
from discord import app_commands
from discord.ext import commands

from utils import db


class Config(commands.Cog):
    """Server configuration."""

    def __init__(self, bot):
        self.bot = bot

    async def _ensure(self, guild_id):
        async with db.get() as c:
            await c.execute("INSERT OR IGNORE INTO guild_config(guild_id) VALUES(?)", (guild_id,))
            await c.commit()

    @staticmethod
    def _display(value):
        return "Not set" if value in (None, "", 0) else str(value)

    @commands.hybrid_group(
        name="config",
        invoke_without_command=True,
        description="Review and update this server's core bot configuration",
    )
    @commands.has_permissions(manage_guild=True)
    async def config(self, ctx):
        async with db.get() as c:
            cur = await c.execute("SELECT * FROM guild_config WHERE guild_id=?", (ctx.guild.id,))
            row = await cur.fetchone()
        if not row:
            await self._ensure(ctx.guild.id)
            return await ctx.send(
                "Server config was initialized. Run the command again to review the current settings."
            )
        cols = [d[0] for d in cur.description]
        embed = discord.Embed(title=f"Config for {ctx.guild.name}", color=0x5865F2)
        for k, v in zip(cols, row):
            embed.add_field(name=k, value=self._display(v), inline=True)
        await ctx.send(embed=embed)

    @config.command(description="Change the server command prefix")
    @app_commands.describe(new_prefix="New prefix members should use for message commands")
    @commands.has_permissions(manage_guild=True)
    async def prefix(self, ctx, new_prefix: str):
        new_prefix = new_prefix.strip()
        if not new_prefix:
            return await ctx.send("Provide a non-empty prefix.")
        await self._ensure(ctx.guild.id)
        async with db.get() as c:
            await c.execute("UPDATE guild_config SET prefix=? WHERE guild_id=?", (new_prefix, ctx.guild.id))
            await c.commit()
        await ctx.send(f"Command prefix updated to `{new_prefix}`.")

    @config.command(description="Set the moderation log channel")
    @app_commands.describe(channel="Channel where moderation and audit events should be logged")
    @commands.has_permissions(manage_guild=True)
    async def logchannel(self, ctx, channel: discord.TextChannel):
        await self._ensure(ctx.guild.id)
        async with db.get() as c:
            await c.execute("UPDATE guild_config SET log_channel=? WHERE guild_id=?", (channel.id, ctx.guild.id))
            await c.commit()
        await ctx.send(f"Moderation log channel set to {channel.mention}.")

    @config.command(description="Set the mute role used by moderation tools")
    @app_commands.describe(role="Role the bot should use for manual mute workflows")
    @commands.has_permissions(manage_guild=True)
    async def muterole(self, ctx, role: discord.Role):
        await self._ensure(ctx.guild.id)
        async with db.get() as c:
            await c.execute("UPDATE guild_config SET mute_role=? WHERE guild_id=?", (role.id, ctx.guild.id))
            await c.commit()
        await ctx.send(f"Mute role set to {role.mention}.")

    @config.command(description="Configure the starboard channel and threshold")
    @app_commands.describe(
        channel="Channel where starred messages should be reposted",
        threshold="How many star reactions are required before reposting",
    )
    @commands.has_permissions(manage_guild=True)
    async def starboard(self, ctx, channel: discord.TextChannel, threshold: int = 3):
        if threshold < 1:
            return await ctx.send("Starboard threshold must be at least 1.")
        await self._ensure(ctx.guild.id)
        async with db.get() as c:
            await c.execute(
                "UPDATE guild_config SET starboard_channel=?, star_threshold=? WHERE guild_id=?",
                (channel.id, threshold, ctx.guild.id),
            )
            await c.commit()
        await ctx.send(f"Starboard posts will go to {channel.mention} with a threshold of {threshold}.")

    @commands.hybrid_command(name="disable", description="Disable a command for this server")
    @app_commands.describe(command="Qualified command name to disable for non-admins")
    @commands.has_permissions(manage_guild=True)
    async def disable(self, ctx, command: str):
        async with db.get() as c:
            await c.execute(
                "INSERT OR IGNORE INTO disabled_commands(guild_id,command) VALUES(?,?)", (ctx.guild.id, command)
            )
            await c.commit()
        await ctx.send(f"Disabled `{command}` for non-admins in this server.")

    @commands.hybrid_command(name="enable", description="Re-enable a previously disabled command")
    @app_commands.describe(command="Qualified command name to restore")
    @commands.has_permissions(manage_guild=True)
    async def enable(self, ctx, command: str):
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM disabled_commands WHERE guild_id=? AND command=?", (ctx.guild.id, command)
            )
            await c.commit()
        if cur.rowcount:
            await ctx.send(f"Re-enabled `{command}`.")
        else:
            await ctx.send(f"`{command}` was not disabled.")

    @commands.hybrid_command(name="ignore", description="Ignore a channel for regular command use")
    @app_commands.describe(channel="Channel that should be ignored; defaults to the current channel")
    @commands.has_permissions(manage_guild=True)
    async def ignore(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        async with db.get() as c:
            await c.execute(
                "INSERT OR IGNORE INTO ignored_channels(guild_id,channel_id) VALUES(?,?)", (ctx.guild.id, ch.id)
            )
            await c.commit()
        await ctx.send(f"The bot will now ignore regular commands in {ch.mention}.")

    @commands.hybrid_command(name="unignore", description="Stop ignoring a channel")
    @app_commands.describe(channel="Ignored channel that should be restored; defaults to the current channel")
    @commands.has_permissions(manage_guild=True)
    async def unignore(self, ctx, channel: discord.TextChannel = None):
        ch = channel or ctx.channel
        async with db.get() as c:
            cur = await c.execute(
                "DELETE FROM ignored_channels WHERE guild_id=? AND channel_id=?", (ctx.guild.id, ch.id)
            )
            await c.commit()
        if cur.rowcount:
            await ctx.send(f"{ch.mention} is no longer ignored.")
        else:
            await ctx.send(f"{ch.mention} was not on the ignored-channel list.")

    @commands.hybrid_command(name="modrole", description="Add or review moderator roles")
    @app_commands.describe(role="Role that should count as a moderator role")
    @commands.has_permissions(manage_guild=True)
    async def modrole(self, ctx, role: discord.Role = None):
        if not role:
            async with db.get() as c:
                cur = await c.execute("SELECT role_id FROM mod_roles WHERE guild_id=?", (ctx.guild.id,))
                rows = await cur.fetchall()
            names = ", ".join(ctx.guild.get_role(r[0]).mention for r in rows if ctx.guild.get_role(r[0]))
            return await ctx.send(f"Moderator roles: {names or 'No moderator roles are configured.'}")
        async with db.get() as c:
            await c.execute("INSERT OR IGNORE INTO mod_roles(guild_id,role_id) VALUES(?,?)", (ctx.guild.id, role.id))
            await c.commit()
        await ctx.send(f"Added {role.mention} as a moderator role.")

    @commands.hybrid_command(name="unmodrole", description="Remove a moderator role")
    @app_commands.describe(role="Moderator role that should be removed")
    @commands.has_permissions(manage_guild=True)
    async def unmodrole(self, ctx, role: discord.Role):
        async with db.get() as c:
            cur = await c.execute("DELETE FROM mod_roles WHERE guild_id=? AND role_id=?", (ctx.guild.id, role.id))
            await c.commit()
        if cur.rowcount:
            await ctx.send(f"Removed {role.mention} from the moderator role list.")
        else:
            await ctx.send(f"{role.mention} was not on the moderator role list.")


async def _global_check(ctx):
    if not ctx.guild or not ctx.command:
        return True
    async with db.get() as c:
        cur = await c.execute(
            "SELECT 1 FROM disabled_commands WHERE guild_id=? AND command=?",
            (ctx.guild.id, ctx.command.qualified_name),
        )
        if await cur.fetchone() and not ctx.author.guild_permissions.administrator:
            return False
        cur = await c.execute(
            "SELECT 1 FROM ignored_channels WHERE guild_id=? AND channel_id=?",
            (ctx.guild.id, ctx.channel.id),
        )
        if await cur.fetchone() and not ctx.author.guild_permissions.manage_guild:
            return False
    return True


async def setup(bot):
    await bot.add_cog(Config(bot))
    bot.add_check(_global_check)
