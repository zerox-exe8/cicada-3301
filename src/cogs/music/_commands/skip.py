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
    try:
        await player.skip()
    except Exception as e:
        # The skip itself is already fault tolerant inside GuildPlayer.skip();
        # this is the last line of defence so the user always gets feedback
        # instead of an unhandled command exception.
        logger.warning(f"Guild {ctx.guild.id}: skip failed: {type(e).__name__}: {e}")
        container = KyroContainer(accent_color=None)
        container.add_text(f"**Could not skip:** `{e}`\n> Please try again in a moment.")
        await send_container_response(ctx, container)
        return

    container = KyroContainer(accent_color=None)
    container.add_text(f"**Skipped:** `{old_title}`")
    await send_container_response(ctx, container)
