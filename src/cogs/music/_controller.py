"""
Cicada 3301 Discord Bot - Music Controller & State Manager
Manages playback state, queues, loop modes, volume, and Type 17 Containers.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from typing import TYPE_CHECKING, Dict, List, Optional

import discord

from src.cogs.music._types import TrackItem, FFMPEG_OPTIONS, BufferedAudioSource
from src.cogs.music._views import MusicControlView
from src.utils.containers import CicadaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import CicadaBot
    from src.core.context import CustomContext

logger = logging.getLogger("Cicada.Music.Controller")


class MusicController:
    """Central Controller managing all music queues, playback state, and Components V2 cards."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot
        self.queues: Dict[int, List[TrackItem]] = {}
        self.current_tracks: Dict[int, TrackItem] = {}
        self.loops: Dict[int, str] = {}  # "off", "track", "queue"
        self.volumes: Dict[int, float] = {}
        self.active_contexts: Dict[int, CustomContext] = {}

    def get_queue(self, guild_id: int) -> List[TrackItem]:
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def get_current(self, guild_id: int) -> Optional[TrackItem]:
        return self.current_tracks.get(guild_id)

    def get_loop(self, guild_id: int) -> str:
        return self.loops.get(guild_id, "off")

    def set_loop(self, guild_id: int, mode: str) -> None:
        self.loops[guild_id] = mode

    def get_volume(self, guild_id: int) -> float:
        return self.volumes.get(guild_id, 1.0)

    def set_volume(self, guild_id: int, vol: float) -> None:
        self.volumes[guild_id] = max(0.0, min(vol, 2.0))

    def clear_guild(self, guild_id: int) -> None:
        self.queues.pop(guild_id, None)
        self.current_tracks.pop(guild_id, None)
        self.loops.pop(guild_id, None)
        self.volumes.pop(guild_id, None)
        self.active_contexts.pop(guild_id, None)

    def build_now_playing_container(self, track: TrackItem, guild_id: int) -> CicadaContainer:
        """Create a signature Cicada Components V2 Container for the playing track."""
        e_reg = self.bot.custom_emojis
        music_icon = e_reg.get("Music_Playing", e_reg.get("music_music", "🎶"))
        note_icon = e_reg.get("a_musical_notes", "")
        loop_icon = e_reg.get("icons_loop", "🔁")
        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))

        dur_m = track.duration // 60
        dur_s = track.duration % 60
        dur_str = f"{dur_m}:{dur_s:02d}" if track.duration > 0 else "Live / Unknown"
        loop_mode = self.get_loop(guild_id)

        container = CicadaContainer(accent_color=None)
        prefix_icon = f"{music_icon} " if music_icon else ""
        note_suffix = f" {note_icon}" if note_icon else ""

        container.add_section(
            content=(
                f"**{prefix_icon}Now Playing{note_suffix}**\n"
                f"> **[{track.title}]({track.url})**\n"
                f"> Artist: `{track.author}`"
            ),
            accessory={"type": 11, "media": {"url": track.thumbnail}} if track.thumbnail else None,
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Duration:** `{dur_str}`\n"
            f"{dot} **Loop Mode:** `{loop_mode.upper()}`\n"
            f"{dot} **Requested By:** `{track.requester or 'User'}`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Cicada 3301 High-Fidelity Audio Engine")
        return container

    def _handle_track_finish(self, ctx: CustomContext, error: Optional[Exception]) -> None:
        """Safe track finish callback to advance the queue."""
        if error:
            logger.warning(f"Audio stream notice: {error}")

        guild_id = ctx.guild.id
        loop_mode = self.get_loop(guild_id)
        current = self.current_tracks.get(guild_id)

        # Handle loop modes
        if loop_mode == "track" and current:
            self._play_stream(ctx, current)
            return
        elif loop_mode == "queue" and current:
            queue = self.get_queue(guild_id)
            queue.append(current)

        self.play_next(ctx)

    def _play_stream(self, ctx: CustomContext, track: TrackItem) -> None:
        """Internal helper to start audio stream with in-memory jitter buffer."""
        voice_client: discord.VoiceClient = ctx.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return
        try:
            ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"
            raw_source = discord.FFmpegPCMAudio(track.stream_url, executable=ffmpeg_exe, **FFMPEG_OPTIONS)
            buffered_source = BufferedAudioSource(raw_source, buffer_size=200)
            vol = self.get_volume(ctx.guild.id)
            source = discord.PCMVolumeTransformer(buffered_source, volume=vol)
            voice_client.play(source, after=lambda e: self._handle_track_finish(ctx, e))
        except Exception as ex:
            logger.error(f"Error streaming track '{track.title}': {ex}", exc_info=ex)
            self.play_next(ctx)

    def play_next(self, ctx: CustomContext) -> None:
        """Play the next track in the queue and publish the Now Playing card."""
        guild_id = ctx.guild.id
        voice_client: discord.VoiceClient = ctx.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return

        queue = self.get_queue(guild_id)
        if queue:
            next_track = queue.pop(0)
            self.current_tracks[guild_id] = next_track
            try:
                ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"
                raw_source = discord.FFmpegPCMAudio(next_track.stream_url, executable=ffmpeg_exe, **FFMPEG_OPTIONS)
                buffered_source = BufferedAudioSource(raw_source, buffer_size=200)
                vol = self.get_volume(guild_id)
                source = discord.PCMVolumeTransformer(buffered_source, volume=vol)
                voice_client.play(source, after=lambda e: self._handle_track_finish(ctx, e))

                container = self.build_now_playing_container(next_track, guild_id)
                view = MusicControlView(self.bot, self, guild_id)
                asyncio.run_coroutine_threadsafe(
                    send_container_response(ctx, container, view=view),
                    self.bot.loop,
                )
            except Exception as ex:
                logger.error(f"Error starting next track: {ex}", exc_info=ex)
                self.play_next(ctx)
        else:
            self.current_tracks.pop(guild_id, None)
