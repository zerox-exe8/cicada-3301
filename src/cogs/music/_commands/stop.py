"""
Kyro Discord Bot - Stop Command Handler (Lavalink V4)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import wavelink

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.cogs.music._player import KyroPlayer
    from src.core.context import CustomContext


async def handle_stop(ctx: CustomContext, controller: MusicController) -> None:
    """Stop music, clear queue and leave voice."""
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore
    if not player or not player.connected:
        await ctx.send_warning("I am not connected to a voice channel.")
        return

    player.queue.clear()
    await player.disconnect()

    e_reg = ctx.bot.custom_emojis
    stop_icon = e_reg.get("icons_stop_button", "")
    prefix = f"{stop_icon} " if stop_icon else ""
    await ctx.send_success(f"{prefix}Stopped playback, cleared the queue, and disconnected from voice.", title="Disconnected")
