import discord
from discord.ext import commands


class Utility(commands.Cog):
    """Info commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(aliases=["ui"])
    async def userinfo(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        e = discord.Embed(title=str(member), color=member.color)
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="ID", value=member.id)
        e.add_field(name="Created", value=f"<t:{int(member.created_at.timestamp())}:R>")
        e.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>")
        e.add_field(name="Top role", value=member.top_role.mention)
        e.add_field(name="Roles", value=len(member.roles) - 1)
        e.add_field(name="Bot", value=member.bot)
        await ctx.send(embed=e)

    @commands.hybrid_command(aliases=["si"])
    async def serverinfo(self, ctx):
        g = ctx.guild
        e = discord.Embed(title=g.name, color=0x5865F2)
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        e.add_field(name="ID", value=g.id)
        e.add_field(name="Owner", value=str(g.owner))
        e.add_field(name="Members", value=g.member_count)
        e.add_field(name="Channels", value=len(g.channels))
        e.add_field(name="Roles", value=len(g.roles))
        e.add_field(name="Created", value=f"<t:{int(g.created_at.timestamp())}:R>")
        e.add_field(name="Boosts", value=g.premium_subscription_count)
        await ctx.send(embed=e)

    @commands.hybrid_command()
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        e = discord.Embed(title=f"{member}'s avatar", color=0x5865F2)
        e.set_image(url=member.display_avatar.url)
        await ctx.send(embed=e)

    @commands.hybrid_command()
    async def ping(self, ctx):
        await ctx.send(f"🏓 {round(self.bot.latency * 1000)}ms")

    @commands.command()
    async def roles(self, ctx):
        roles = [r.mention for r in reversed(ctx.guild.roles) if r.name != "@everyone"]
        e = discord.Embed(title=f"Roles ({len(roles)})", description=" ".join(roles)[:4000], color=0x5865F2)
        await ctx.send(embed=e)

    @commands.command(aliases=["i"])
    async def info(self, ctx, member: discord.Member = None):
        await ctx.invoke(self.userinfo, member=member)

    @commands.command()
    async def youngest(self, ctx, count: int = 10):
        members = sorted([m for m in ctx.guild.members if m.joined_at], key=lambda m: m.created_at, reverse=True)[
            :count
        ]
        lines = [f"{i + 1}. {m} — <t:{int(m.created_at.timestamp())}:R>" for i, m in enumerate(members)]
        e = discord.Embed(title="Youngest accounts", description="\n".join(lines), color=0x5865F2)
        await ctx.send(embed=e)

    @commands.command()
    async def oldest(self, ctx, count: int = 10):
        members = sorted([m for m in ctx.guild.members if m.joined_at], key=lambda m: m.created_at)[:count]
        lines = [f"{i + 1}. {m} — <t:{int(m.created_at.timestamp())}:R>" for i, m in enumerate(members)]
        e = discord.Embed(title="Oldest accounts", description="\n".join(lines), color=0x5865F2)
        await ctx.send(embed=e)

    @commands.command(aliases=["newusers"])
    async def newmembers(self, ctx, count: int = 10):
        members = sorted([m for m in ctx.guild.members if m.joined_at], key=lambda m: m.joined_at, reverse=True)[:count]
        lines = [f"{i + 1}. {m} — <t:{int(m.joined_at.timestamp())}:R>" for i, m in enumerate(members)]
        e = discord.Embed(title="Newest members", description="\n".join(lines), color=0x5865F2)
        await ctx.send(embed=e)

    @commands.command(aliases=["oldusers"])
    async def oldmembers(self, ctx, count: int = 10):
        members = sorted([m for m in ctx.guild.members if m.joined_at], key=lambda m: m.joined_at)[:count]
        lines = [f"{i + 1}. {m} — <t:{int(m.joined_at.timestamp())}:R>" for i, m in enumerate(members)]
        e = discord.Embed(title="Oldest members", description="\n".join(lines), color=0x5865F2)
        await ctx.send(embed=e)


async def setup(bot):
    await bot.add_cog(Utility(bot))
