"""
Kyro Discord Bot - Native Autoplay Command
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from discord.ext import commands

from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music


async def execute_autoplay(cog: Music, ctx: commands.Context, state: str = "") -> None:
    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyroContainer(accent_color=None)
        container.add_text("**No active player found in this server.** Play a song first with `?play <song>`.")
        await send_container_response(ctx, container)
        return

    st = state.lower().strip()
    if st in ("on", "enable", "true", "1"):
        player.smart_autoplay = True
    elif st in ("off", "disable", "false", "0"):
        player.smart_autoplay = False
    else:
        player.smart_autoplay = not player.smart_autoplay

    status_str = "ENABLED" if player.smart_autoplay else "DISABLED"
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Smart Autoplay is now:** `{status_str}`")
    await send_container_response(ctx, container)
