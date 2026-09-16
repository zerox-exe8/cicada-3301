"""
Kyro Discord Bot - Mimic Impersonation Command
Sends messages via webhooks copying a member's display name and avatar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class MimicCog(commands.Cog, name="Games-Mimic"):
    """Server member webhook impersonation suite."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="mimic",
        aliases=["clone", "impersonate"],
        description="Send a message disguised as another user using channel webhooks.",
    )
    @commands.guild_only()
    async def mimic(self, ctx: CustomContext, member: discord.Member, *, message: str) -> None:
        """Send a message disguised as another server member."""
        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send_error("This command can only be executed in server text channels.")
            return

        me = ctx.guild.me
        if not ctx.channel.permissions_for(me).manage_webhooks:
            await ctx.send_error("I need `Manage Webhooks` permission in this channel to mimic members.")
            return

        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        clean_content = message.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
        if not clean_content.strip():
            return

        try:
            webhooks = await ctx.channel.webhooks()
            webhook = next((w for w in webhooks if w.user == self.bot.user), None)
            if not webhook:
                webhook = await ctx.channel.create_webhook(name="Kyro-Mimic")

            await webhook.send(
                content=clean_content,
                username=member.display_name,
                avatar_url=member.display_avatar.url,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as err:
            await ctx.send_error(f"Failed to execute mimic: {err}")


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(MimicCog(bot))
