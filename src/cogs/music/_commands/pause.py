"""
Kyro Discord Bot - Pause & Resume Command Handlers (Lavalink V4)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import wavelink

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.cogs.music._player import KyroPlayer
    from src.core.context import CustomContext


async def handle_pause(ctx: CustomContext, controller: MusicController) -> None:
    """Pause playback."""
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore
    if not player or not player.playing:
        await ctx.send_warning("No music is currently playing.")
        return

    await player.pause(True)
    e_reg = ctx.bot.custom_emojis
    pause_icon = e_reg.get("paused", "")
    prefix = f"{pause_icon} " if pause_icon else ""
    await ctx.send_success(f"{prefix}Playback paused. Use `{ctx.prefix}resume` to continue.", title="Paused")


async def handle_resume(ctx: CustomContext, controller: MusicController) -> None:
    """Resume playback."""
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore
    if not player or not player.paused:
        await ctx.send_warning("Music is not paused.")
        return

    await player.pause(False)
    e_reg = ctx.bot.custom_emojis
    play_icon = e_reg.get("music_playing", "")
    prefix = f"{play_icon} " if play_icon else ""
    await ctx.send_success(f"{prefix}Resumed audio stream playback.", title="Resumed")
