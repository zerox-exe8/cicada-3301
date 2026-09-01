"""
Kyro Discord Bot - Native Skip Command
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from discord.ext import commands

from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music


async def execute_skip(cog: Music, ctx: commands.Context) -> None:
    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or not player.current:
        container = KyroContainer(accent_color=None)
        container.add_text("**Nothing is currently playing to skip.**")
        await send_container_response(ctx, container)
        return

    old_title = player.current.title
    await player.skip()
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Skipped:** `{old_title}`")
    await send_container_response(ctx, container)
