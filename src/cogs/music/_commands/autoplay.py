"""
Cicada 3301 Discord Bot - Autoplay Command
Toggles AI Autoplay and displays listener music taste intelligence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord

from src.utils.containers import CicadaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.context import CustomContext
    from src.cogs.music._controller import MusicController


async def handle_autoplay(ctx: CustomContext, controller: MusicController, action: Optional[str] = None) -> None:
    """Handle the autoplay command and taste insights."""
    e_reg = ctx.bot.custom_emojis
    dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))
    autoplay_icon = e_reg.get("icons_loop", e_reg.get("music_playing", ""))
    prefix_icon = f"{autoplay_icon} " if autoplay_icon else ""

    guild_id = ctx.guild.id
    current_state = controller.get_autoplay(guild_id)

    # 1. Determine new state
    if action:
        act = action.lower().strip()
        if act in ("on", "enable", "true", "yes", "1"):
            new_state = True
        elif act in ("off", "disable", "false", "no", "0"):
            new_state = False
        elif act in ("status", "taste", "info"):
            new_state = current_state
        else:
            new_state = not current_state
    else:
        new_state = not current_state

    controller.set_autoplay(guild_id, new_state)

    # 2. Gather active VC listener taste profiles
    vc = ctx.guild.voice_client
    top_artists = []
    if vc and vc.channel:
        listeners = [m.id for m in vc.channel.members if not m.bot]
        top_artists = await controller.analytics.get_top_artists(listeners, limit=5)

    status_str = "ENABLED (AI Smart Radio)" if new_state else "DISABLED"
    status_desc = (
        "AI will automatically queue personalized tracks matching current listeners' taste when queue ends."
        if new_state
        else "Playback will stop once the current queue finishes."
    )

    container = CicadaContainer(accent_color=None)
    container.add_section(
        content=(
            f"**{prefix_icon}AI Autoplay Radio**\n"
            f"> **Status:** `{status_str}`\n"
            f"> {status_desc}"
        )
    )
    container.add_separator(divider=True)

    if top_artists:
        artists_formatted = ", ".join(f"`{a}`" for a in top_artists)
        container.add_text(
            f"{dot} **Active Listener Tastes:** {artists_formatted}\n"
            f"{dot} **Audio Engine:** `JioSaavn 320kbps CD Master + YouTube`"
        )
    else:
        container.add_text(
            f"{dot} **Audio Engine:** `JioSaavn 320kbps CD Master + YouTube`\n"
            f"-# Listen on Spotify or play songs to enrich your AI profile!"
        )

    await send_container_response(ctx, container)
