"""
Kyro Discord Bot - Autoplay Command (Lavalink V4)
Toggles the Smart Autoplay AI Radio Engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import wavelink

from src.cogs.music._player import KyroPlayer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.context import CustomContext
    from src.cogs.music._controller import MusicController


async def handle_autoplay(ctx: CustomContext, controller: MusicController, action: Optional[str] = None) -> None:
    """Toggle Smart Autoplay AI radio mode or view current status."""
    e_reg = ctx.bot.custom_emojis
    dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))
    autoplay_icon = e_reg.get("icons_loop", e_reg.get("music_playing", ""))
    prefix_icon = f"{autoplay_icon} " if autoplay_icon else ""

    player: KyroPlayer = ctx.guild.voice_client if ctx.guild else None  # type: ignore
    current_state = bool(player and player.smart_autoplay)

    # 1. If no argument provided, show clean usage guide
    if not action:
        container = KyroContainer(accent_color=None)
        status_text = "Enabled" if current_state else "Disabled"
        container.add_section(
            content=(
                f"**{prefix_icon}Smart Autoplay AI Radio**\n"
                f"> **Status:** `{status_text}`\n"
                f"> **Usage:** `{ctx.prefix}autoplay <on / off>`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Description:** Automatically curates and pre-fetches similar studio tracks using Spotify-grade genre clustering when the playlist ends."
        )
        container.add_separator(divider=True)
        container.add_text("-# Kyro Studio Engine • Lavalink V4")
        await send_container_response(ctx, container)
        return

    act = action.lower().strip()

    if not player or not player.connected:
        await ctx.send_warning("I am not connected to a voice channel. Play a song first!")
        return

    if act in ("on", "enable", "1", "true"):
        player.smart_autoplay = True
        if player.current:
            player.record_track_start(player.current)
        await ctx.send_success(
            f"{prefix_icon}Smart Autoplay has been **Enabled**. Similar songs will play automatically with zero gap when the queue ends.",
            title="Autoplay Enabled",
        )
    elif act in ("off", "disable", "0", "false"):
        player.smart_autoplay = False
        player.prefetched_autoplay_track = None
        await ctx.send_success(
            f"{prefix_icon}Smart Autoplay has been **Disabled**.",
            title="Autoplay Disabled",
        )
    else:
        # Toggle
        player.smart_autoplay = not player.smart_autoplay
        state_str = "Enabled" if player.smart_autoplay else "Disabled"
        if player.smart_autoplay and player.current:
            player.record_track_start(player.current)
        elif not player.smart_autoplay:
            player.prefetched_autoplay_track = None

        await ctx.send_success(
            f"{prefix_icon}Smart Autoplay is now **{state_str}**.",
            title=f"Autoplay {state_str}",
        )
