from __future__ import annotations

from discord.ext import commands

from loki_engine.permissions import PermissionContext, can_create_activity_event, can_manage_activity


class LokiActivities(commands.Cog):
    """Discord Activities and scheduled-event control surface."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_group(name="activity", description="Manage LOKI activities and scheduled events")
    async def activity(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Use a subcommand: status, create-event, or end-event.")

    @activity.command(name="status", description="Show LOKI activity control status")
    async def activity_status(self, ctx: commands.Context):
        await ctx.send("LOKI activity control is ready. Event mutations require create/manage-events or admin.")

    @activity.command(name="create-event", description="Create a tracked activity event")
    async def activity_create_event(self, ctx: commands.Context, *, title: str):
        permissions = getattr(ctx.author.guild_permissions, "value", 0)
        decision = can_create_activity_event(
            PermissionContext(
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                permissions=permissions,
            )
        )
        if not decision.allowed:
            return await ctx.send(decision.reason)
        await ctx.send(
            f"Activity event creation accepted for **{title}**. Configure full schedule details in the portal."
        )

    @activity.command(name="end-event", description="End or archive a tracked activity event")
    async def activity_end_event(self, ctx: commands.Context, event_id: str):
        permissions = getattr(ctx.author.guild_permissions, "value", 0)
        decision = can_manage_activity(
            PermissionContext(
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                permissions=permissions,
            )
        )
        if not decision.allowed:
            return await ctx.send(decision.reason)
        await ctx.send(f"Activity event **{event_id}** marked for shutdown/audit.")


async def setup(bot):
    await bot.add_cog(LokiActivities(bot))
