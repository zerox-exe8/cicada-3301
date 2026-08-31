"""
Cicada 3301 Discord Bot - Stop & Disconnect Command Handler
"""

from __future__ import annotations

import discord
from src.core.context import CustomContext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController


async def handle_stop(ctx: CustomContext, controller: MusicController) -> None:
    """Stop music, clear queue and leave voice."""
    voice_client: discord.VoiceClient = ctx.guild.voice_client
    if not voice_client:
        await ctx.send("I am not connected to a voice channel.")
        return
    controller.clear_guild(ctx.guild.id)
    await voice_client.disconnect()
    await ctx.send("Stopped playback and disconnected.")
