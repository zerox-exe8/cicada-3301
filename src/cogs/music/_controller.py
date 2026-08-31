"""
Cicada 3301 Discord Bot - Central Music Controller & State Manager
Manages playback state, queues, voice client connections, and ultra-armor streaming.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, List, Optional

import discord

from src.cogs.music._types import TrackItem, FFMPEG_OPTIONS
from src.core.context import CustomContext

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("cicada.music.controller")


class MusicController:
    """Central Controller managing all music queues and playback state."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot
        self.queues: Dict[int, List[TrackItem]] = {}
        self.current_tracks: Dict[int, TrackItem] = {}

    def get_queue(self, guild_id: int) -> List[TrackItem]:
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def get_current(self, guild_id: int) -> Optional[TrackItem]:
        return self.current_tracks.get(guild_id)

    def clear_guild(self, guild_id: int) -> None:
        self.queues.pop(guild_id, None)
        self.current_tracks.pop(guild_id, None)

    def _handle_track_finish(self, ctx: CustomContext, error: Optional[Exception]) -> None:
        """Safe track finish handler to advance queue."""
        if error:
            logger.warning(f"Audio stream noticed transition: {error}")
        self.play_next(ctx)

    def play_next(self, ctx: CustomContext) -> None:
        """Play the next track in the queue."""
        guild_id = ctx.guild.id
        voice_client: discord.VoiceClient = ctx.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return

        queue = self.get_queue(guild_id)
        if queue:
            next_track = queue.pop(0)
            self.current_tracks[guild_id] = next_track
            try:
                source = discord.FFmpegOpusAudio(next_track.stream_url, **FFMPEG_OPTIONS)
                voice_client.play(source, after=lambda e: self._handle_track_finish(ctx, e))
                embed = discord.Embed(
                    title="Now Playing",
                    description=f"**[{next_track.title}]({next_track.url})**\nArtist: `{next_track.author}`",
                    color=0x2B2D31
                )
                if next_track.thumbnail:
                    embed.set_thumbnail(url=next_track.thumbnail)
                embed.set_footer(text=f"Requested by {next_track.requester} | Ultra-Armor HD Lossless Audio")
                asyncio.run_coroutine_threadsafe(ctx.send(embed=embed), self.bot.loop)
            except Exception as ex:
                logger.error(f"Error starting next track: {ex}")
                self.play_next(ctx)
        else:
            self.current_tracks.pop(guild_id, None)
