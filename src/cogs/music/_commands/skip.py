"""
Kyro Discord Bot - Skip Command Handler (Lavalink V4)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import wavelink

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.cogs.music._player import KyroPlayer
    from src.core.context import CustomContext


async def handle_skip(ctx: CustomContext, controller: MusicController) -> None:
    """Skip currently playing track."""
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore
    if not player or not player.current:
        await ctx.send_warning("No track is currently playing.")
        return

    current_title = player.current.title or "current track"
    await player.skip(force=True)

    e_reg = ctx.bot.custom_emojis
    skip_icon = e_reg.get("skip", "")
    prefix = f"{skip_icon} " if skip_icon else ""
    await ctx.send_success(f"{prefix}Skipped **{current_title}** to next track in queue.", title="Track Skipped")
