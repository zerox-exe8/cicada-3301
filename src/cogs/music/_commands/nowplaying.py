from __future__ import annotations

from typing import TYPE_CHECKING
from discord.ext import commands

from src.cogs.music._views import MusicControlView
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music


async def execute_nowplaying(cog: Music, ctx: commands.Context) -> None:
    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or not player.current:
        container = KyroContainer(accent_color=None)
        container.add_text("**Nothing is currently playing.**")
        await send_container_response(ctx, container)
        return

    container = player.build_now_playing_container(player.current)
    view = MusicControlView(cog.bot, player, ctx.guild.id)
    e_reg = getattr(cog.bot, "custom_emojis", None)
    music_emoji = e_reg.get("music", "🎵") if e_reg else "🎵"
    await send_container_response(
        ctx, container, view=view, content=f"### {music_emoji} Now Playing {music_emoji}"
    )
