"""
Cicada 3301 Discord Bot - Now Playing Command Handler
"""

from __future__ import annotations

import discord
from src.core.context import CustomContext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController


async def handle_nowplaying(ctx: CustomContext, controller: MusicController) -> None:
    """Show details of the currently playing track."""
    guild_id = ctx.guild.id
    current = controller.get_current(guild_id)

    if not current:
        await ctx.send("No track is currently playing.")
        return

    embed = discord.Embed(
        title="Now Playing",
        description=f"**[{current.title}]({current.url})**\nArtist: `{current.author}`",
        color=0x2B2D31
    )
    if current.thumbnail:
        embed.set_thumbnail(url=current.thumbnail)
    embed.set_footer(text=f"Requested by {current.requester} | Ultra-Armor HD Lossless Audio")
    await ctx.send(embed=embed)
