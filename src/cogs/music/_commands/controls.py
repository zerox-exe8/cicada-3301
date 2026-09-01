"""
Kyro Discord Bot - Native Music Control Commands (Volume, Loop, Shuffle, Clear)
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING
from discord.ext import commands

from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music


async def execute_volume(cog: Music, ctx: commands.Context, volume: int) -> None:
    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyroContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    new_vol = player.set_volume(volume)
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Volume adjusted to:** `{new_vol}%`")
    await send_container_response(ctx, container)


async def execute_loop(cog: Music, ctx: commands.Context, mode: str = "off") -> None:
    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyroContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    new_mode = player.set_loop_mode(mode)
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Loop mode set to:** `{new_mode.upper()}`")
    await send_container_response(ctx, container)


async def execute_shuffle(cog: Music, ctx: commands.Context) -> None:
    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or len(player.queue) < 2:
        container = KyroContainer(accent_color=None)
        container.add_text("**Queue needs at least 2 tracks to shuffle.**")
        await send_container_response(ctx, container)
        return

    random.shuffle(player.queue)
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Shuffled {len(player.queue)} tracks in queue.**")
    await send_container_response(ctx, container)


async def execute_clear(cog: Music, ctx: commands.Context) -> None:
    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyroContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    cleared_count = len(player.queue)
    player.queue.clear()
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Cleared {cleared_count} tracks from the queue.**")
    await send_container_response(ctx, container)
