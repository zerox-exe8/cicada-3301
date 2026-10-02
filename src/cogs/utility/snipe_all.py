"""
Kyro Discord Bot - Server-Wide Snipe All Suite
Clean, simple overview of recently deleted messages across all server channels.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response
from src.cogs.utility.snipe import SnipeEntry

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class SnipeAllCog(commands.Cog, name="Utility-SnipeAll"):
    """Server-wide message retention auditor across all channels."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        if not hasattr(self.bot, "snipe_cache"):
            self.bot.snipe_cache = {}
        if not hasattr(self.bot, "guild_snipe_cache"):
            self.bot.guild_snipe_cache = {}

    @commands.hybrid_command(
        name="snipeall",
        aliases=["sall", "globalsnipe", "serversnipe"],
        description="Show recent deleted messages across all channels in the server.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def snipeall(self, ctx: CustomContext) -> None:
        """
        Show recent deleted messages across all channels in the server.
        Requires Manage Messages permission.
        """
        guild_id = ctx.guild.id
        all_entries: deque[SnipeEntry] = getattr(self.bot, "guild_snipe_cache", {}).get(guild_id, deque())
        deleted_entries = [e for e in all_entries if e.type == "delete"]

        if not deleted_entries:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**No Deleted Messages**\n"
                    f"> No recently deleted messages tracked in **{ctx.guild.name}**."
                )
            )
            await send_container_response(ctx, container)
            return

        recent_entries = deleted_entries[:6]

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Recent Deleted Messages**\n"
                f"> Showing the last `{len(recent_entries)}` deleted message(s) across **{ctx.guild.name}**."
            )
        )
        container.add_separator(divider=True)

        lines = []
        for entry in recent_entries:
            rel_ts = int(entry.action_at.timestamp())
            channel_ref = f"<#{entry.channel_id}>" if entry.channel_id else f"#{entry.channel_name}"
            raw = entry.content.replace("\n", " ").strip() if entry.content else "*[Media / Attachment]*"
            if len(raw) > 100:
                raw = raw[:97] + "..."
            lines.append(f"• **{entry.author_name}** in {channel_ref} (<t:{rel_ts}:R>)\n  {raw}")

        container.add_text("\n\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Use `{ctx.clean_prefix}snipe` in any channel to view full details")
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="clearsnipeall",
        aliases=["csnipeall", "wipesnipeall"],
        description="Wipe the server-wide deleted message cache.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def clearsnipeall(self, ctx: CustomContext) -> None:
        """Wipe the server-wide deleted message cache."""
        guild_id = ctx.guild.id
        count = len(getattr(self.bot, "guild_snipe_cache", {}).get(guild_id, []))
        if guild_id in getattr(self.bot, "guild_snipe_cache", {}):
            self.bot.guild_snipe_cache[guild_id].clear()

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Server Snipe Cache Cleared**\n"
                f"> Successfully wiped `{count}` tracked server message(s) in **{ctx.guild.name}**."
            )
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load SnipeAllCog into KyroBot."""
    await bot.add_cog(SnipeAllCog(bot))
