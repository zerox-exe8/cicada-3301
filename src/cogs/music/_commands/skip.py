"""
Cicada 3301 Discord Bot - Skip Command Handler
"""

from __future__ import annotations

import discord
from src.core.context import CustomContext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController


async def handle_skip(ctx: CustomContext, controller: MusicController) -> None:
    """Skip currently playing track."""
    voice_client: discord.VoiceClient = ctx.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        await ctx.send("No track is currently playing.")
        return
    voice_client.stop()
    await ctx.send("Skipped to next track.")
