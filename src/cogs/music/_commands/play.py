"""
Kyro Discord Bot - Native Play Command
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.cogs.music._extractor import NativeExtractor
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music

logger = logging.getLogger("Kyro.Music.Play")


async def execute_play(cog: Music, ctx: commands.Context, query: Optional[str] = None) -> None:
    """Execute native play command."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        container = KyroContainer(accent_color=None)
        container.add_text("**You must be in a voice channel to play music.**")
        await send_container_response(ctx, container)
        return

    voice_channel = ctx.author.voice.channel
    player = cog.controller.get_or_create_player(ctx.guild)
    player.home_channel = ctx.channel

    # Connect to voice
    try:
        await player.connect_voice(voice_channel)
    except Exception as e:
        logger.error(f"Voice connect error: {e}")
        container = KyroContainer(accent_color=None)
        container.add_text(f"**Failed to connect to voice channel:** `{e}`")
        await send_container_response(ctx, container)
        return

    # Handle empty query
    if not query or not query.strip():
        if player.is_paused:
            player.resume()
            container = KyroContainer(accent_color=None)
            container.add_text("**Resumed playback.**")
            await send_container_response(ctx, container)
            return
        elif player.queue and not player.is_playing:
            next_track = player.queue.pop(0)
            await player.play_track(next_track)
            return
        else:
            container = KyroContainer(accent_color=None)
            container.add_text("**Please provide a song title or URL.**\n> Usage: `?play <song title or URL>`")
            await send_container_response(ctx, container)
            return

    # 1. Send Searching Track card first
    search_container = KyroContainer(accent_color=None)
    search_container.add_text(f"**Searching track:** `{query}`...")
    search_msg = await send_container_response(ctx, search_container)

    # 2. Extract track in background
    track = await NativeExtractor.extract(query, requester=ctx.author.display_name)
    if track:
        track.requester_id = ctx.author.id

    if not track:
        err_container = KyroContainer(accent_color=None)
        err_container.add_text(f"**No results found for:** `{query}`")
        if search_msg and isinstance(search_msg, discord.Message):
            try:
                await search_msg.edit(embed=err_container.to_embed())
                return
            except Exception:
                pass
        await send_container_response(ctx, err_container)
        return

    # 3. If nothing is currently playing, start playback
    if not player.is_playing and not player.is_paused:
        await player.play_track(track, message_to_edit=search_msg)
    else:
        # Add to queue
        player.queue.append(track)
        pos = len(player.queue)
        queue_container = KyroContainer(accent_color=None)
        queue_container.add_section(
            content=(
                f"**Added to Queue [Position #{pos}]**\n"
                f"> **Track:** [{track.title}]({track.url})\n"
                f"> **Artist:** `{track.author}`\n"
                f"> **Duration:** `{track.formatted_duration}`\n"
                f"> **Requested By:** `{track.requester}`"
            ),
            accessory={"type": 11, "media": {"url": track.thumbnail}} if track.thumbnail else None,
        )
        await send_container_response(ctx, queue_container)
