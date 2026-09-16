"""
Kyro Discord Bot - Native Pause & Resume Command
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from discord.ext import commands

from src.cogs.music._commands.controls import check_voice_channel
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music


async def execute_pause(cog: Music, ctx: commands.Context) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyroContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    if player.pause():
        await player.update_controller_message(force=True)
        container = KyroContainer(accent_color=None)
        container.add_text("**Playback paused.** Type `?resume` to continue.")
        await send_container_response(ctx, container)
    else:
        container = KyroContainer(accent_color=None)
        container.add_text("**Player is not playing or already paused.**")
        await send_container_response(ctx, container)


async def execute_resume(cog: Music, ctx: commands.Context) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyroContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    if player.resume():
        player._was_paused_for_empty_vc = False
        await player.update_controller_message(force=True)
        container = KyroContainer(accent_color=None)
        container.add_text("**Playback resumed.**")
        await send_container_response(ctx, container)
    else:
        container = KyroContainer(accent_color=None)
        container.add_text("**Player is not paused.**")
        await send_container_response(ctx, container)
