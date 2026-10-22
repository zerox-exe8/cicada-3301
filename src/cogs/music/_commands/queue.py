from __future__ import annotations

from typing import TYPE_CHECKING, Union
from discord.ext import commands

from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music


async def execute_queue(cog: Music, ctx: commands.Context, page: Union[int, str] = 1) -> None:
    if isinstance(page, str):
        cleaned = page.strip().lower()
        if cleaned in ("clear", "clean", "empty", "c", "cls"):
            from src.cogs.music._commands.controls import execute_clear
            await execute_clear(cog, ctx)
            return
        try:
            page = max(1, int(cleaned))
        except ValueError:
            page = 1

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

    async with player._queue_lock:
        queue_snapshot = list(player.queue)

    if not queue_snapshot:
        ap_status = "ON" if player.smart_autoplay else "OFF"
        container.add_text(
            f"Queue is empty.\n"
            f"-# Autoplay: **{ap_status}** • Loop: **{player.loop_mode.upper()}**"
        )
    else:
        per_page = 10
        total_pages = (len(queue_snapshot) + per_page - 1) // per_page
        clamped_page = max(1, min(page, total_pages))
        start_idx = (clamped_page - 1) * per_page
        end_idx = start_idx + per_page
        page_tracks = queue_snapshot[start_idx:end_idx]

        lines = []
        for i, track in enumerate(page_tracks, start=start_idx + 1):
            safe_title = track.title.replace("[", "(").replace("]", ")")
            track_link = f"[{safe_title}]({track.url})" if track.url else f"**{safe_title}**"
            lines.append(f"`{i:02d}.` {track_link} `[{track.formatted_duration}]` — `{track.requester}`")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(
            f"-# Page {clamped_page}/{total_pages} • Total Songs: {len(queue_snapshot)} • Autoplay: {'ON' if player.smart_autoplay else 'OFF'}"
        )

    await send_container_response(ctx, container)
