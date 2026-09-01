"""
Kyro Discord Bot - Now Playing Command Handler (Lavalink V4)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import wavelink

from src.cogs.music._player import KyroPlayer
from src.cogs.music._views import MusicControlView
from src.utils.containers import send_container_response

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext


async def handle_nowplaying(ctx: CustomContext, controller: MusicController) -> None:
    """Show details of the currently playing track."""
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore

    if not player or not player.current:
        await ctx.send_warning("No track is currently playing.")
        return

    req = None
    if hasattr(player.current, "extras") and hasattr(player.current.extras, "requester"):
        req = player.current.extras.requester

    container = player.build_now_playing_container(player.current, requester=req)
    view = MusicControlView(ctx.bot, player, ctx.guild.id)
    await send_container_response(ctx, container, view=view)
