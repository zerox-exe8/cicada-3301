"""
Cicada 3301 Discord Bot - Queue Command Handler
"""

from __future__ import annotations

import discord
from typing import TYPE_CHECKING

from src.utils.containers import CicadaContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext


async def handle_queue(ctx: CustomContext, controller: MusicController) -> None:
    """Show current song queue."""
    guild_id = ctx.guild.id
    current = controller.get_current(guild_id)
    queue = controller.get_queue(guild_id)

    if not current and not queue:
        await ctx.send_warning("The music queue is currently empty. Play songs with `?play <song>`.")
        return

    e_reg = ctx.bot.custom_emojis
    q_icon = e_reg.get("queue", "📜")
    music_icon = e_reg.get("Music_Playing", "🎶")
    dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))

    container = CicadaContainer(accent_color=None)
    container.add_section(
        content=(
            f"**{q_icon} Server Music Queue**\n"
            f"> Listing upcoming tracks for **{ctx.guild.name}**."
        )
    )
    container.add_separator(divider=True)

    if current:
        dur_m = current.duration // 60
        dur_s = current.duration % 60
        dur_str = f"{dur_m}:{dur_s:02d}" if current.duration > 0 else "Live"
        container.add_text(
            f"**Now Playing:**\n"
            f"{music_icon} **[{current.title}]({current.url})** (`{dur_str}`)\n"
            f"> Requested by: `{current.requester or 'User'}`"
        )
        container.add_separator(divider=True)

    if queue:
        lines = []
        for i, t in enumerate(queue[:12], 1):
            dur_m = t.duration // 60
            dur_s = t.duration % 60
            dur_str = f"{dur_m}:{dur_s:02d}" if t.duration > 0 else "Live"
            lines.append(f"`{i}.` **[{t.title}]({t.url})** — `{dur_str}` (Req: `{t.requester or 'User'}`)")

        if len(queue) > 12:
            lines.append(f"\n*...and {len(queue) - 12} more track(s) in queue.*")

        container.add_text("**Up Next:**\n" + "\n".join(lines))
        container.add_separator(divider=True)

    loop_mode = controller.get_loop(guild_id)
    total_tracks = len(queue) + (1 if current else 0)
    container.add_text(f"-# Loop: {loop_mode.upper()} • Total Tracks: {total_tracks} • Requested by {ctx.author.display_name}")

    await send_container_response(ctx, container)
