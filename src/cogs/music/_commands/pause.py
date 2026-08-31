"""
Cicada 3301 Discord Bot - Pause & Resume Command Handlers
"""

from __future__ import annotations

import discord
from src.core.context import CustomContext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController


async def handle_pause(ctx: CustomContext, controller: MusicController) -> None:
    """Pause playback."""
    voice_client: discord.VoiceClient = ctx.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        await ctx.send("No music is currently playing.")
        return
    voice_client.pause()
    await ctx.send("Playback paused.")


async def handle_resume(ctx: CustomContext, controller: MusicController) -> None:
    """Resume playback."""
    voice_client: discord.VoiceClient = ctx.guild.voice_client
    if not voice_client or not voice_client.is_paused():
        await ctx.send("Music is not paused.")
        return
    voice_client.resume()
    await ctx.send("Playback resumed.")
