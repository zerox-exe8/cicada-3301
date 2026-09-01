"""
Kyro Discord Bot - Stop Command Handler
"""

from __future__ import annotations

import discord
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext


async def handle_stop(ctx: CustomContext, controller: MusicController) -> None:
    """Stop music, clear queue and leave voice."""
    voice_client: discord.VoiceClient = ctx.guild.voice_client
    if not voice_client:
        await ctx.send_warning("I am not connected to a voice channel.")
        return

    controller.clear_guild(ctx.guild.id)
    await voice_client.disconnect()
    e_reg = ctx.bot.custom_emojis
    stop_icon = e_reg.get("icons_stop_button", "")
    prefix = f"{stop_icon} " if stop_icon else ""
    await ctx.send_success(f"{prefix}Stopped playback, cleared the queue, and disconnected from voice.", title="Disconnected")
