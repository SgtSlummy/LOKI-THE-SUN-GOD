import asyncio

import discord
from discord.ext import commands, tasks

from utils import db
from utils.helpers import fmt_duration, now, parse_duration


class Roles(commands.Cog):
    """Autoroles, joinable ranks, bulk role ops, temproles."""

    def __init__(self, bot):
        self.bot = bot
        self.temprole_loop.start()

    def cog_unload(self):
        self.temprole_loop.cancel()

    # ---------- autorole ----------
    @commands.hybrid_group(invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def autorole(self, ctx):
        async with db.get() as c:
            cur = await c.execute("SELECT role_id FROM autoroles WHERE guild_id=?", (ctx.guild.id,))
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send("No autoroles. Use `autorole add <role>`.")
        names = ", ".join(ctx.guild.get_role(r[0]).mention for r in rows if ctx.guild.get_role(r[0]))
        await ctx.send(f"Autoroles: {names}")

    @autorole.command(name="add")
    @commands.has_permissions(manage_roles=True)
    async def autorole_add(self, ctx, role: discord.Role):
        async with db.get() as c:
            await c.execute("INSERT OR IGNORE INTO autoroles(guild_id,role_id) VALUES(?,?)", (ctx.guild.id, role.id))
            await c.commit()
        await ctx.send(f"Added autorole {role.mention}")

    @autorole.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    async def autorole_remove(self, ctx, role: discord.Role):
        async with db.get() as c:
            await c.execute("DELETE FROM autoroles WHERE guild_id=? AND role_id=?", (ctx.guild.id, role.id))
            await c.commit()
        await ctx.send(f"Removed {role.mention}")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        async with db.get() as c:
            cur = await c.execute("SELECT role_id FROM autoroles WHERE guild_id=?", (member.guild.id,))
            rows = await cur.fetchall()
        for (rid,) in rows:
            role = member.guild.get_role(rid)
            if role:
                try:
                    await member.add_roles(role, reason="Autorole")
                except discord.Forbidden:
                    pass

    # ---------- joinable ranks ----------
    @commands.hybrid_command()
    @commands.has_permissions(manage_roles=True)
    async def addrank(self, ctx, role: discord.Role):
        async with db.get() as c:
            await c.execute(
                "INSERT OR IGNORE INTO joinable_ranks(guild_id,role_id) VALUES(?,?)", (ctx.guild.id, role.id)
            )
            await c.commit()
        await ctx.send(f"{role.mention} joinable.")

    @commands.hybrid_command()
    @commands.has_permissions(manage_roles=True)
    async def removerank(self, ctx, role: discord.Role):
        async with db.get() as c:
            await c.execute("DELETE FROM joinable_ranks WHERE guild_id=? AND role_id=?", (ctx.guild.id, role.id))
            await c.commit()
        await ctx.send("Removed.")

    @commands.hybrid_command()
    async def ranks(self, ctx):
        async with db.get() as c:
            cur = await c.execute("SELECT role_id FROM joinable_ranks WHERE guild_id=?", (ctx.guild.id,))
            rows = await cur.fetchall()
        if not rows:
            return await ctx.send("None.")
        names = "\n".join(ctx.guild.get_role(r[0]).mention for r in rows if ctx.guild.get_role(r[0]))
        await ctx.send(embed=discord.Embed(title="Joinable ranks", description=names, color=0x5865F2))

    @commands.hybrid_command(name="iam", aliases=["joinrank"])
    async def iam(self, ctx, *, role_name: str):
        """Toggle a self-assignable rank role (Carl-bot convention)."""
        role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), ctx.guild.roles)
        if not role:
            return await ctx.send("Role not found.")
        async with db.get() as c:
            cur = await c.execute(
                "SELECT 1 FROM joinable_ranks WHERE guild_id=? AND role_id=?", (ctx.guild.id, role.id)
            )
            row = await cur.fetchone()
        if not row:
            return await ctx.send("Not a joinable rank.")
        if role in ctx.author.roles:
            await ctx.author.remove_roles(role, reason="Self-leave rank")
            await ctx.send(f"Left {role.mention}")
        else:
            await ctx.author.add_roles(role, reason="Self-join rank")
            await ctx.send(f"Joined {role.mention}")

    # ---------- role mgmt ----------
    @commands.hybrid_group(invoke_without_command=True)
    @commands.has_permissions(manage_roles=True)
    async def role(self, ctx, member: discord.Member, *, role: discord.Role):
        if role in member.roles:
            await member.remove_roles(role)
            await ctx.send(f"Removed {role.mention} from {member}")
        else:
            await member.add_roles(role)
            await ctx.send(f"Added {role.mention} to {member}")

    @role.command(name="add")
    @commands.has_permissions(manage_roles=True)
    async def role_add(self, ctx, member: discord.Member, *, role: discord.Role):
        await member.add_roles(role)
        await ctx.send(f"Added {role.mention} to {member}")

    @role.command(name="remove")
    @commands.has_permissions(manage_roles=True)
    async def role_remove(self, ctx, member: discord.Member, *, role: discord.Role):
        await member.remove_roles(role)
        await ctx.send(f"Removed {role.mention} from {member}")

    @role.command(name="info")
    async def role_info(self, ctx, *, role: discord.Role):
        e = discord.Embed(title=role.name, color=role.color)
        e.add_field(name="ID", value=role.id)
        e.add_field(name="Members", value=len(role.members))
        e.add_field(name="Hoist", value=role.hoist)
        e.add_field(name="Mention", value=role.mentionable)
        e.add_field(name="Position", value=role.position)
        e.add_field(name="Color", value=str(role.color))
        await ctx.send(embed=e)

    @role.command(name="all")
    @commands.has_permissions(manage_roles=True)
    async def role_all(self, ctx, *, role: discord.Role):
        n = 0
        for m in ctx.guild.members:
            if not m.bot and role not in m.roles:
                try:
                    await m.add_roles(role, reason=f"role all by {ctx.author}")
                    n += 1
                except discord.Forbidden:
                    pass
                await asyncio.sleep(0.5)
        await ctx.send(f"Gave {role.mention} to {n} humans.")

    @role.command(name="bots")
    @commands.has_permissions(manage_roles=True)
    async def role_bots(self, ctx, *, role: discord.Role):
        n = 0
        for m in ctx.guild.members:
            if m.bot and role not in m.roles:
                try:
                    await m.add_roles(role)
                    n += 1
                except discord.Forbidden:
                    pass
        await ctx.send(f"Gave {role.mention} to {n} bots.")

    @role.command(name="rall")
    @commands.has_permissions(manage_roles=True)
    async def role_rall(self, ctx, *, role: discord.Role):
        n = 0
        for m in list(role.members):
            try:
                await m.remove_roles(role)
                n += 1
            except discord.Forbidden:
                pass
            await asyncio.sleep(0.5)
        await ctx.send(f"Removed {role.mention} from {n} members.")

    @role.command(name="in")
    @commands.has_permissions(manage_roles=True)
    async def role_in(self, ctx, source: discord.Role, target: discord.Role):
        n = 0
        for m in source.members:
            if target not in m.roles:
                try:
                    await m.add_roles(target)
                    n += 1
                except discord.Forbidden:
                    pass
        await ctx.send(f"Gave {target.mention} to {n} members of {source.mention}")

    @role.command(name="create")
    @commands.has_permissions(manage_roles=True)
    async def role_create(self, ctx, *, name: str):
        r = await ctx.guild.create_role(name=name, reason=f"by {ctx.author}")
        await ctx.send(f"Created {r.mention}")

    @role.command(name="color")
    @commands.has_permissions(manage_roles=True)
    async def role_color(self, ctx, role: discord.Role, color: discord.Color):
        await role.edit(color=color)
        await ctx.send(f"{role.mention} color = {color}")

    # ---------- temprole ----------
    @commands.command()
    @commands.has_permissions(manage_roles=True)
    async def temprole(self, ctx, member: discord.Member, duration: str, *, role: discord.Role):
        secs = parse_duration(duration)
        if not secs:
            return await ctx.send("Bad duration.")
        until = now() + secs
        await member.add_roles(role, reason=f"temprole by {ctx.author}")
        async with db.get() as c:
            await c.execute(
                "INSERT INTO temproles(guild_id,user_id,role_id,until) VALUES(?,?,?,?)",
                (ctx.guild.id, member.id, role.id, until),
            )
            await c.commit()
        await ctx.send(f"{role.mention} on {member} for {fmt_duration(secs)}")

    @tasks.loop(seconds=60)
    async def temprole_loop(self):
        async with db.get() as c:
            cur = await c.execute("SELECT id, guild_id, user_id, role_id FROM temproles WHERE until<=?", (now(),))
            rows = await cur.fetchall()
            for tid, gid, uid, rid in rows:
                guild = self.bot.get_guild(gid)
                if guild:
                    member = guild.get_member(uid)
                    role = guild.get_role(rid)
                    if member and role:
                        try:
                            await member.remove_roles(role, reason="Temprole expired")
                        except discord.Forbidden:
                            pass
                await c.execute("DELETE FROM temproles WHERE id=?", (tid,))
            await c.commit()

    @temprole_loop.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Roles(bot))
