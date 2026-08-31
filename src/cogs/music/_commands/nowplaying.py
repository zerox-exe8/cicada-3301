"""
Cicada 3301 Discord Bot - Now Playing Command Handler
"""

from __future__ import annotations

import discord
from typing import TYPE_CHECKING

from src.cogs.music._views import MusicControlView
from src.utils.containers import send_container_response

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext


async def handle_nowplaying(ctx: CustomContext, controller: MusicController) -> None:
    """Show details of the currently playing track."""
    guild_id = ctx.guild.id
    current = controller.get_current(guild_id)

    if not current:
        await ctx.send_warning("No track is currently playing.")
        return

    container = controller.build_now_playing_container(current, guild_id)
    view = MusicControlView(ctx.bot, controller, guild_id)
    await send_container_response(ctx, container, view=view)
