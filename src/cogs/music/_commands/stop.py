from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

from src.cogs.music._commands.controls import check_voice_channel
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music

logger = logging.getLogger("Kyro.Music.Cmd.Stop")


async def execute_stop(cog: Music, ctx: commands.Context) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        # Self-healing fallback: If bot is physically sitting in a voice channel, force disconnect it!
        if ctx.guild.me and ctx.guild.me.voice and ctx.guild.me.voice.channel:
            try:
                if player:
                    player.queue.clear()
                    player.current = None
                    player.voice_client = None
                await ctx.guild.change_voice_state(channel=None)
                container = KyroContainer(accent_color=None)
                container.add_text("**Cleaned orphaned voice connection and disconnected.**")
                await send_container_response(ctx, container)
                return
            except Exception as v_err:
                logger.debug(f"Orphaned voice disconnect notice: {v_err}")
        container = KyroContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    player._disconnect_announced = True
    await player.stop()
    e_reg = getattr(cog.bot, "custom_emojis", None)
    stop_e = (e_reg.get("icons_stop_button", "") or e_reg.get("stop", "")) if e_reg else ""
    prefix = f"{stop_e} " if stop_e else ""
    container = KyroContainer(accent_color=None)
    container.add_text(f"{prefix}**Player stopped, queue cleared and disconnected from voice.**")
    await send_container_response(ctx, container)
