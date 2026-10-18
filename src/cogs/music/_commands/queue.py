from __future__ import annotations

from typing import TYPE_CHECKING
from discord.ext import commands

from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music


async def execute_queue(cog: Music, ctx: commands.Context, page: int = 1) -> None:
    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or (not player.current and not player.queue):
        container = KyroContainer(accent_color=None)
        container.add_text("**No active queue found in this server.**")
        await send_container_response(ctx, container)
        return

    container = KyroContainer(accent_color=None)
    if player.current:
        curr_title = player.current.title.replace("[", "(").replace("]", ")")
        curr_link = f"[{curr_title}]({player.current.url})" if player.current.url else f"**{curr_title}**"
        container.add_text(
            f"**Live Player Queue — {ctx.guild.name}**\n"
            f"**Now Playing:** {curr_link} `[{player.current.formatted_duration}]`"
        )
    else:
        container.add_text(f"**Live Player Queue — {ctx.guild.name}**")
    container.add_separator(divider=True)

    if not player.queue:
        ap_status = "ON" if player.smart_autoplay else "OFF"
        container.add_text(
            f"Queue is empty.\n"
            f"-# Autoplay: **{ap_status}** • Loop: **{player.loop_mode.upper()}**"
        )
    else:
        per_page = 10
        total_pages = (len(player.queue) + per_page - 1) // per_page
        clamped_page = max(1, min(page, total_pages))
        start_idx = (clamped_page - 1) * per_page
        end_idx = start_idx + per_page
        page_tracks = player.queue[start_idx:end_idx]

        lines = []
        for i, track in enumerate(page_tracks, start=start_idx + 1):
            safe_title = track.title.replace("[", "(").replace("]", ")")
            track_link = f"[{safe_title}]({track.url})" if track.url else f"**{safe_title}**"
            lines.append(f"`{i:02d}.` {track_link} `[{track.formatted_duration}]` — `{track.requester}`")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(
            f"-# Page {clamped_page}/{total_pages} • Total Songs: {len(player.queue)} • Autoplay: {'ON' if player.smart_autoplay else 'OFF'}"
        )

    await send_container_response(ctx, container)
