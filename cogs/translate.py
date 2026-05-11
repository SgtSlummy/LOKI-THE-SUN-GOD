import urllib.parse

import aiohttp
import discord
from discord.ext import commands


class Translate(commands.Cog):
    """Translate via free MyMemory API (no key). Context menu + command."""

    def __init__(self, bot):
        self.bot = bot
        self.ctx_menu = discord.app_commands.ContextMenu(
            name="Translate to English",
            callback=self.translate_msg,
        )
        bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def _translate(self, text: str, target: str = "en") -> str:
        url = f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(text[:500])}&langpair=auto|{target}"
        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                data = await r.json()
        return data.get("responseData", {}).get("translatedText", "[translation failed]")

    @commands.command()
    async def translate(self, ctx, lang: str, *, text: str):
        out = await self._translate(text, lang)
        e = discord.Embed(title=f"→ {lang}", description=out, color=0x5865F2)
        await ctx.send(embed=e)

    async def translate_msg(self, interaction: discord.Interaction, message: discord.Message):
        if not message.content:
            return await interaction.response.send_message("No text.", ephemeral=True)
        out = await self._translate(message.content, "en")
        await interaction.response.send_message(f"**→ EN:** {out}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Translate(bot))
