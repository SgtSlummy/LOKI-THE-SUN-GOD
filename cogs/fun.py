import random
import urllib.parse

import aiohttp
import discord
from discord.ext import commands

CHARMAP_FANCY = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩",
)
CHARMAP_FRAKTUR = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ",
)
CHARMAP_BOLDFRAKTUR = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "𝖆𝖇𝖈𝖉𝖊𝖋𝖌𝖍𝖎𝖏𝖐𝖑𝖒𝖓𝖔𝖕𝖖𝖗𝖘𝖙𝖚𝖛𝖜𝖝𝖞𝖟𝕬𝕭𝕮𝕯𝕰𝕱𝕲𝕳𝕴𝕵𝕶𝕷𝕸𝕹𝕺𝕻𝕼𝕽𝕾𝕿𝖀𝖁𝖂𝖃𝖄𝖅",
)
CHARMAP_SC = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ")


class Fun(commands.Cog):
    """Fun text + image commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def echo(self, ctx, *, text: str):
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass
        await ctx.send(text)

    @commands.command(aliases=["choice", "select"])
    async def pick(self, ctx, *options):
        if len(options) < 2:
            return await ctx.send("Need 2+ options.")
        await ctx.send(f"🎯 {random.choice(options)}")

    @commands.hybrid_command()
    async def roll(self, ctx, dice: str = "1d6"):
        try:
            n, sides = map(int, dice.lower().split("d"))
        except ValueError:
            return await ctx.send("Format: NdM, e.g. `2d20`")
        if n > 100 or sides > 1000:
            return await ctx.send("Too big.")
        rolls = [random.randint(1, sides) for _ in range(n)]
        await ctx.send(f"🎲 {rolls} = **{sum(rolls)}**")

    @commands.hybrid_command(aliases=["coin", "flip"])
    async def coinflip(self, ctx):
        await ctx.send(f"🪙 **{random.choice(['Heads', 'Tails'])}**")

    @commands.hybrid_command(name="8ball")
    async def eight_ball(self, ctx, *, question: str):
        responses = [
            "Yes",
            "No",
            "Maybe",
            "Definitely",
            "Absolutely not",
            "Ask later",
            "Without a doubt",
            "Outlook not so good",
        ]
        await ctx.send(f"🎱 {random.choice(responses)}")

    @commands.command()
    async def shake(self, ctx):
        await ctx.send(f"🎱 *shake shake* — {random.choice(['Yes', 'No', 'Maybe'])}")

    @commands.command(aliases=["urbandictionary"])
    async def ud(self, ctx, *, term: str):
        url = f"https://api.urbandictionary.com/v0/define?term={urllib.parse.quote(term)}"
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                data = await r.json()
        if not data.get("list"):
            return await ctx.send("No results.")
        d = data["list"][0]
        e = discord.Embed(title=d["word"], url=d["permalink"], description=d["definition"][:1024], color=0xEFFF00)
        if d.get("example"):
            e.add_field(name="Example", value=d["example"][:512])
        e.set_footer(text=f"👍 {d['thumbs_up']} | 👎 {d['thumbs_down']}")
        await ctx.send(embed=e)

    @commands.command()
    async def cat(self, ctx):
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.thecatapi.com/v1/images/search") as r:
                data = await r.json()
        e = discord.Embed(color=0x5865F2)
        e.set_image(url=data[0]["url"])
        await ctx.send(embed=e)

    @commands.command()
    async def dog(self, ctx):
        async with aiohttp.ClientSession() as s:
            async with s.get("https://dog.ceo/api/breeds/image/random") as r:
                data = await r.json()
        e = discord.Embed(color=0x5865F2)
        e.set_image(url=data["message"])
        await ctx.send(embed=e)

    @commands.command(aliases=["ff"])
    async def fancy(self, ctx, *, text: str):
        await ctx.send(text.translate(CHARMAP_FANCY))

    @commands.command()
    async def fraktur(self, ctx, *, text: str):
        await ctx.send(text.translate(CHARMAP_FRAKTUR))

    @commands.command(aliases=["bf"])
    async def boldfraktur(self, ctx, *, text: str):
        await ctx.send(text.translate(CHARMAP_BOLDFRAKTUR))

    @commands.command(aliases=["sc"])
    async def smallcaps(self, ctx, *, text: str):
        await ctx.send(text.lower().translate(CHARMAP_SC))

    @commands.command(aliases=["ae"])
    async def aesthetics(self, ctx, *, text: str):
        out = "".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in text)
        await ctx.send(out)

    @commands.command()
    async def clap(self, ctx, *, text: str):
        await ctx.send(" 👏 ".join(text.split()))

    @commands.command()
    async def emojify(self, ctx, *, text: str):
        out = []
        for c in text.lower():
            if c.isalpha():
                out.append(f":regional_indicator_{c}:")
            elif c.isdigit():
                names = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
                out.append(f":{names[int(c)]}:")
            else:
                out.append(c)
        await ctx.send(" ".join(out)[:2000])

    @commands.command(aliases=["ds"])
    async def double(self, ctx, *, text: str):
        await ctx.send("".join(c * 2 for c in text))

    @commands.command()
    async def space(self, ctx, *, text: str):
        await ctx.send(" ".join(text))

    @commands.command()
    async def owofy(self, ctx, *, text: str):
        out = text.replace("r", "w").replace("l", "w").replace("R", "W").replace("L", "W")
        out += " " + random.choice(["uwu", "owo", "><", ":3"])
        await ctx.send(out)

    @commands.command(aliases=["steal"])
    @commands.has_permissions(manage_emojis=True)
    async def addemoji(self, ctx, name: str, url: str):
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                if r.status != 200:
                    return await ctx.send("Bad URL.")
                img = await r.read()
        emoji = await ctx.guild.create_custom_emoji(name=name, image=img)
        await ctx.send(f"Added {emoji}")


async def setup(bot):
    await bot.add_cog(Fun(bot))
