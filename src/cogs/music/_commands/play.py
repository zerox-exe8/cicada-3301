"""
Cicada 3301 Discord Bot - Play Command Handler
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.cogs.music._types import FFMPEG_OPTIONS
from src.cogs.music._resolver import MusicResolver
from src.core.context import CustomContext

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController

logger = logging.getLogger("cicada.music.cmd.play")


async def handle_play(ctx: CustomContext, controller: MusicController, query: str) -> None:
    """Execute the play command."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("You must be in a Voice Channel to play music.")
        return

    user_channel = ctx.author.voice.channel
    voice_client: discord.VoiceClient = ctx.guild.voice_client

    # 1. Connect or Move Voice Client with high connection timeout & auto-reconnect
    if not voice_client or not voice_client.is_connected():
        try:
            voice_client = await user_channel.connect(self_deaf=True, timeout=20.0, reconnect=True)
        except Exception as e:
            await ctx.send(f"Could not connect to voice channel: `{e}`")
            return
    elif voice_client.channel != user_channel:
        await voice_client.move_to(user_channel)

    status_msg = await ctx.send(f"Searching for **{query}**...")

    # 2. Resolve Track with Hyper-Fast Multi-Tier Engine
    track = await MusicResolver.resolve(query)
    if not track or not track.stream_url:
        await status_msg.edit(content=f"No results found for **{query}**.")
        return

    track.requester = ctx.author.display_name
    guild_id = ctx.guild.id
    queue = controller.get_queue(guild_id)

    # 3. Play or Queue Track with Ultra-Armor Buffer
    if not voice_client.is_playing() and not voice_client.is_paused():
        controller.current_tracks[guild_id] = track
        try:
            source = discord.FFmpegOpusAudio(track.stream_url, **FFMPEG_OPTIONS)
            voice_client.play(source, after=lambda e: controller._handle_track_finish(ctx, e))
            embed = discord.Embed(
                title="Now Playing",
                description=f"**[{track.title}]({track.url})**\nArtist: `{track.author}`",
                color=0x2B2D31
            )
            if track.thumbnail:
                embed.set_thumbnail(url=track.thumbnail)
            embed.set_footer(text=f"Requested by {track.requester} | Ultra-Armor HD Lossless Audio")
            await status_msg.edit(content=None, embed=embed)
        except Exception as e:
            logger.error(f"Error starting playback: {e}")
            await status_msg.edit(content=f"Error playing track: `{e}`")
    else:
        queue.append(track)
        embed = discord.Embed(
            title="Track Queued",
            description=f"**[{track.title}]({track.url})**\nPosition #{len(queue)}",
            color=0x2B2D31
        )
        await status_msg.edit(content=None, embed=embed)
