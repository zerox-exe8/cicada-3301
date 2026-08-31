"""
Cicada 3301 Discord Bot - Skip Command Handler
"""

from __future__ import annotations

import discord
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext


async def handle_skip(ctx: CustomContext, controller: MusicController) -> None:
    """Skip currently playing track."""
    voice_client: discord.VoiceClient = ctx.guild.voice_client
    if not voice_client or (not voice_client.is_playing() and not voice_client.is_paused()):
        await ctx.send_warning("No track is currently playing.")
        return

    current = controller.get_current(ctx.guild.id)
    current_title = current.title if current else "current track"

    voice_client.stop()
    e_reg = ctx.bot.custom_emojis
    skip_icon = e_reg.get("skip", "")
    prefix = f"{skip_icon} " if skip_icon else ""
    await ctx.send_success(f"{prefix}Skipped **{current_title}** to next track in queue.", title="Track Skipped")
