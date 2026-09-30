"""
Kyro Discord Bot - Channel Information Module
Inspect channel metadata, type, topic, slowmode, and creation timestamp.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.General.ChannelInfo")


class ChannelInfo(commands.Cog, name="General-ChannelInfo"):
    """Channel inspection suite."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="channelinfo",
        aliases=["ci"],
        description="View details, category, topic, and creation date of a channel.",
    )
    @app_commands.describe(channel="Channel to inspect (defaults to current channel)")
    @commands.guild_only()
    async def channelinfo(
        self,
        ctx: CustomContext,
        channel: Optional[discord.abc.GuildChannel] = None,
    ) -> None:
        """Inspect a server channel."""
        target_ch = channel or ctx.channel
        if not target_ch:
            await ctx.send_warning("Channel not found.")
            return

        created_ts = int(target_ch.created_at.timestamp())
        ch_type = str(target_ch.type).replace("_", " ").title()
        category_name = target_ch.category.name if target_ch.category else "None"

        # Topic & Slowmode
        topic = getattr(target_ch, "topic", None) or "No topic set"
        slowmode = getattr(target_ch, "slowmode_delay", 0)
        slowmode_str = f"`{slowmode}s`" if slowmode > 0 else "`Disabled`"
        nsfw = getattr(target_ch, "nsfw", False)
        nsfw_str = "`Yes`" if nsfw else "`No`"

        # Voice bitrate
        bitrate = getattr(target_ch, "bitrate", None)
        bitrate_str = f"`{bitrate // 1000} kbps`" if bitrate else "N/A"

        container.add_section(
            content=(
                f"### #{target_ch.name}\n"
                f"ID: `{target_ch.id}` | Type: `{ch_type}`\n"
                f"Category: `{category_name}`\n"
                f"Created: <t:{created_ts}:F> (<t:{created_ts}:R>)\n\n"
                f"**Channel Settings**\n"
                f"Slowmode: {slowmode_str}\n"
                f"NSFW: {nsfw_str}\n"
                f"Voice Bitrate: {bitrate_str}\n"
                f"Topic: `{topic}`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ChannelInfo(bot))
