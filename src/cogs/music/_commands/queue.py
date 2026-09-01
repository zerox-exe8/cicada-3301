"""
Kyro Discord Bot - Queue Command Handler (Lavalink V4)
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import wavelink

from src.cogs.music._player import KyroPlayer, shorten_artist
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext


async def handle_queue(ctx: CustomContext, controller: MusicController) -> None:
    """Display current song queue with interactive pagination."""
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore

    if not player or (not player.current and player.queue.is_empty):
        await ctx.send_warning("The music queue is currently empty.")
        return

    e_reg = ctx.bot.custom_emojis
    q_icon = e_reg.get("queue", "")
    q_prefix = f"{q_icon} " if q_icon else ""
    music_icon = e_reg.get("music_playing", "")
    music_prefix = f"{music_icon} " if music_icon else ""

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**{q_prefix}Server Music Queue**\n"
            f"> Listing upcoming tracks for **{ctx.guild.name}**."
        )
    )
    container.add_separator(divider=True)

    current = player.current
    if current:
        dur_s = (current.length // 1000) if current.length else 0
        dur_str = f"{dur_s // 60:02d}:{dur_s % 60:02d}" if dur_s > 0 else "Live"
        short_artist_name = shorten_artist(current.author or "Official Artist")
        container.add_text(
            f"**Now Playing:**\n"
            f"> {music_prefix}**[{current.title}]({current.uri})**\n"
            f"> Artist: `{short_artist_name}`\n"
            f"> Duration: `{dur_str}`"
        )
        container.add_separator(divider=True)

    if not player.queue.is_empty:
        lines = []
        # player.queue is iterable in Wavelink 3
        for i, t in enumerate(list(player.queue)[:10], 1):
            dur_s = (t.length // 1000) if t.length else 0
            dur_str = f"{dur_s // 60:02d}:{dur_s % 60:02d}" if dur_s > 0 else "Live"
            lines.append(f"`{i}.` **[{t.title}]({t.uri})** — `{dur_str}`")

        if len(player.queue) > 10:
            lines.append(f"-# ...and {len(player.queue) - 10} more track(s) in queue.")

        container.add_text("**Up Next:**\n" + "\n".join(lines))
        container.add_separator(divider=True)

    loop_mode = player.get_loop_mode().upper()
    ap_mode = "ON" if player.autoplay == wavelink.AutoPlayMode.enabled else "OFF"
    total_tracks = len(player.queue) + (1 if current else 0)
    container.add_text(f"-# Loop: {loop_mode} • Autoplay: {ap_mode} • Total Tracks: {total_tracks}")

    await send_container_response(ctx, container)
