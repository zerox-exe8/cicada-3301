"""
Kyro Discord Bot - Native Stop Command
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from discord.ext import commands

from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music


async def execute_stop(cog: Music, ctx: commands.Context) -> None:
    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyroContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    await player.stop()
    container = KyroContainer(accent_color=None)
    container.add_text("**Player stopped, queue cleared and disconnected from voice.**")
    await send_container_response(ctx, container)
