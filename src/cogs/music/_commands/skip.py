from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from discord.ext import commands

from src.cogs.music._commands.controls import check_voice_channel
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music

logger = logging.getLogger("Kyro.Music.Skip")


async def execute_skip(cog: Music, ctx: commands.Context) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or not player.current:
        container = KyroContainer(accent_color=None)
        container.add_text("**Nothing is currently playing to skip.**")
        await send_container_response(ctx, container)
        return

    old_title = player.current.title
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Skipped:** `{old_title}`")
    # Send instant confirmation without blocking user turn
    await send_container_response(ctx, container)

    asyncio.create_task(player.skip())
