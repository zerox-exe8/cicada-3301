"""
Kyro Discord Bot - Pause & Resume Command Handlers
"""

from __future__ import annotations

import discord
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext


async def handle_pause(ctx: CustomContext, controller: MusicController) -> None:
    """Pause playback."""
    voice_client: discord.VoiceClient = ctx.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        await ctx.send_warning("No music is currently playing.")
        return
    voice_client.pause()
    e_reg = ctx.bot.custom_emojis
    pause_icon = e_reg.get("paused", "")
    prefix = f"{pause_icon} " if pause_icon else ""
    await ctx.send_success(f"{prefix}Playback paused. Use `{ctx.prefix}resume` to continue.", title="Paused")


async def handle_resume(ctx: CustomContext, controller: MusicController) -> None:
    """Resume playback."""
    voice_client: discord.VoiceClient = ctx.guild.voice_client
    if not voice_client or not voice_client.is_paused():
        await ctx.send_warning("Music is not paused.")
        return
    voice_client.resume()
    e_reg = ctx.bot.custom_emojis
    play_icon = e_reg.get("music_playing", "")
    prefix = f"{play_icon} " if play_icon else ""
    await ctx.send_success(f"{prefix}Resumed audio stream playback.", title="Resumed")
