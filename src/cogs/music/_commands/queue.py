"""
Kyro Discord Bot - Queue Command Handler
"""

from __future__ import annotations

import discord
from typing import TYPE_CHECKING

from src.cogs.music._controller import shorten_artist
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext


async def handle_queue(ctx: CustomContext, controller: MusicController) -> None:
    """Display current song queue with interactive pagination."""
    guild_id = ctx.guild.id
    current = controller.get_current(guild_id)
    queue = controller.get_queue(guild_id)

    if not current and not queue:
        await ctx.send_warning("The music queue is currently empty.")
        return

    e_reg = ctx.bot.custom_emojis
    q_icon = e_reg.get("queue", "")
    q_prefix = f"{q_icon} " if q_icon else ""
    music_icon = e_reg.get("music_playing", "")
    music_prefix = f"{music_icon} " if music_icon else ""
    dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**{q_prefix}Server Music Queue**\n"
            f"> Listing upcoming tracks for **{ctx.guild.name}**."
        )
    )
    container.add_separator(divider=True)

    if current:
        dur_m = current.duration // 60
        dur_s = current.duration % 60
        dur_str = f"{dur_m:02d}:{dur_s:02d}" if current.duration > 0 else "Live"
        short_artist = shorten_artist(current.author)
        container.add_text(
            f"**Now Playing:**\n"
            f"> {music_prefix}**[{current.title}]({current.url})**\n"
            f"> Artist: `{short_artist}`\n"
            f"> Duration: `{dur_str}`"
        )
        container.add_separator(divider=True)

    if queue:
        lines = []
        for i, t in enumerate(queue[:10], 1):
            dur_m = t.duration // 60
            dur_s = t.duration % 60
            dur_str = f"{dur_m:02d}:{dur_s:02d}" if t.duration > 0 else "Live"
            lines.append(f"`{i}.` **[{t.title}]({t.url})** — `{dur_str}`")

        if len(queue) > 10:
            lines.append(f"-# ...and {len(queue) - 10} more track(s) in queue.")

        container.add_text("**Up Next:**\n" + "\n".join(lines))
        container.add_separator(divider=True)

    loop_mode = controller.get_loop(guild_id)
    ap_mode = "ON" if controller.get_autoplay(guild_id) else "OFF"
    total_tracks = len(queue) + (1 if current else 0)
    container.add_text(f"-# Loop: {loop_mode.upper()} • Autoplay: {ap_mode} • Total Tracks: {total_tracks}")

    await send_container_response(ctx, container)
