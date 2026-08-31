"""
Cicada 3301 Discord Bot - Play Command Handler
"""

from __future__ import annotations

import logging
import shutil
from typing import TYPE_CHECKING
import discord

from src.cogs.music._types import FFMPEG_OPTIONS
from src.cogs.music._resolver import MusicResolver
from src.cogs.music._views import MusicControlView
from src.utils.containers import CicadaContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext

logger = logging.getLogger("Cicada.Music.Cmd.Play")


async def handle_play(ctx: CustomContext, controller: MusicController, query: str) -> None:
    """Execute the play command."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send_warning("You must be connected to a Voice Channel to play music.")
        return

    user_channel = ctx.author.voice.channel
    voice_client: discord.VoiceClient = ctx.guild.voice_client

    # 1. Connect or Move Voice Client
    if not voice_client or not voice_client.is_connected():
        try:
            voice_client = await user_channel.connect(self_deaf=True, timeout=20.0, reconnect=True)
        except Exception as e:
            await ctx.send_error(f"Could not connect to voice channel: `{e}`")
            return
    elif voice_client.channel != user_channel:
        await voice_client.move_to(user_channel)

    e_reg = ctx.bot.custom_emojis
    search_icon = e_reg.get("Music_Playing", e_reg.get("music_music", "🔎"))

    search_container = CicadaContainer(accent_color=None)
    search_container.add_text(f"{search_icon} **Searching for track:** `{query}`...")
    status_msg = await send_container_response(ctx, search_container)

    # 2. Resolve Track
    try:
        track = await MusicResolver.resolve(query)
    except Exception as ex:
        logger.error(f"Resolver error for '{query}': {ex}", exc_info=ex)
        await ctx.send_error(f"Failed to search for **{query}**: `{ex}`")
        return

    if not track or not track.stream_url:
        await ctx.send_warning(f"No results found for `{query}`.")
        return

    track.requester = ctx.author.display_name
    guild_id = ctx.guild.id
    queue = controller.get_queue(guild_id)
    controller.active_contexts[guild_id] = ctx

    # 3. Play or Queue Track
    if not voice_client.is_playing() and not voice_client.is_paused():
        controller.current_tracks[guild_id] = track
        try:
            controller._play_stream(ctx, track)

            card = controller.build_now_playing_container(track, guild_id)
            view = MusicControlView(ctx.bot, controller, guild_id)
            await send_container_response(ctx, card, view=view)
        except Exception as e:
            logger.error(f"Error starting playback: {e}", exc_info=e)
            await ctx.send_error(f"Error playing track: `{e}`")
    else:
        queue.append(track)
        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))
        queued_icon = e_reg.get("queue", "📜")

        dur_m = track.duration // 60
        dur_s = track.duration % 60
        dur_str = f"{dur_m}:{dur_s:02d}" if track.duration > 0 else "Live"

        queued_container = CicadaContainer(accent_color=None)
        queued_container.add_section(
            content=(
                f"**{queued_icon} Track Queued**\n"
                f"> **[{track.title}]({track.url})**\n"
                f"> Artist: `{track.author}`"
            ),
            accessory={"type": 11, "media": {"url": track.thumbnail}} if track.thumbnail else None,
        )
        queued_container.add_separator(divider=True)
        queued_container.add_text(
            f"{dot} **Position in Queue:** `#{len(queue)}`\n"
            f"{dot} **Duration:** `{dur_str}`\n"
            f"{dot} **Requested By:** `{track.requester}`"
        )
        queued_container.add_separator(divider=True)
        queued_container.add_text(f"-# Use ?queue to view the full upcoming playlist.")
        await send_container_response(ctx, queued_container)
