"""
Kyro Discord Bot - Native Play Command
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.music._extractor import NativeExtractor
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music

logger = logging.getLogger("Kyro.Music.Play")


async def execute_play(cog: Music, ctx: commands.Context, query: str) -> None:
    """Execute native play command."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        container = KyroContainer(accent_color=None)
        container.add_text("❌ **You must be in a voice channel to play music.**")
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
        container.add_text(f"❌ **Failed to connect to voice channel:** `{e}`")
        await send_container_response(ctx, container)
        return

    # Extract track
    async with ctx.typing():
        track = await NativeExtractor.extract(query, requester=ctx.author.display_name)

    if not track:
        container = KyroContainer(accent_color=None)
        container.add_text(f"❌ **No results found for:** `{query}`")
        await send_container_response(ctx, container)
        return

    # If nothing is currently playing, start immediately
    if not player.is_playing and not player.is_paused:
        await player.play_track(track)
    else:
        # Add to queue
        player.queue.append(track)
        pos = len(player.queue)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**📥 Added to Queue [Position #{pos}]**\n"
                f"> **Track:** [{track.title}]({track.url})\n"
                f"> **Artist:** `{track.author}`\n"
                f"> **Duration:** `{track.formatted_duration}`\n"
                f"> **Requested By:** `{track.requester}`"
            ),
            accessory={"type": 11, "media": {"url": track.thumbnail}} if track.thumbnail else None,
        )
        await send_container_response(ctx, container)
