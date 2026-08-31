"""
Cicada 3301 Discord Bot - Music Controller
High-Performance Audio Controller with Components V2 Player Cards, Gapless Autoplay Buffer, and Rock-Solid Stability.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import shutil
from typing import TYPE_CHECKING, Dict, List, Optional, Set

import discord

from src.core.context import CustomContext
from src.utils.containers import CicadaContainer, send_container_response
from src.cogs.music._types import TrackItem, FFMPEG_OPTIONS, BufferedAudioSource
from src.cogs.music._views import MusicControlView
from src.cogs.music._resolver import MusicResolver, clean_track_title
from src.cogs.music._analytics import MusicAnalytics

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("Cicada.Music.Controller")


def shorten_artist(raw_artist: str, max_chars: int = 32) -> str:
    """Shorten multi-artist strings to prevent card layout breaking."""
    if not raw_artist:
        return "Official Artist"
    clean = html.unescape(raw_artist).strip()
    # Split by common separators e.g. ",", "&", "feat.", "ft.", "Feat"
    parts = re.split(r"[,/|]|\s+(?:feat\.?|ft\.?|and|&)\s+", clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) > 2:
        clean = f"{parts[0]}, {parts[1]} & others"
    elif len(parts) == 2:
        clean = f"{parts[0]} & {parts[1]}"
    if len(clean) > max_chars:
        clean = clean[: max_chars - 3].rstrip() + "..."
    return clean


class MusicController:
    """Central Controller managing voice playback, queue, autoplay buffer, and component cards."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot
        self.analytics = MusicAnalytics(bot)
        self.queues: Dict[int, List[TrackItem]] = {}
        self.current_tracks: Dict[int, TrackItem] = {}
        self.loops: Dict[int, str] = {}  # "off", "track", "queue"
        self.volumes: Dict[int, float] = {}
        self.active_contexts: Dict[int, CustomContext] = {}
        self.autoplay_settings: Dict[int, bool] = {}
        self.played_history: Dict[int, Set[str]] = {}
        self.prefetched_autoplay: Dict[int, TrackItem] = {}

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
        self.volumes[guild_id] = max(0.0, min(vol, 1.0))

    def get_autoplay(self, guild_id: int) -> bool:
        return self.autoplay_settings.get(guild_id, False)

    def set_autoplay(self, guild_id: int, enabled: bool) -> None:
        self.autoplay_settings[guild_id] = enabled
        if guild_id not in self.played_history:
            self.played_history[guild_id] = set()
        if not enabled:
            self.prefetched_autoplay.pop(guild_id, None)

    def get_played_history(self, guild_id: int) -> Set[str]:
        if guild_id not in self.played_history:
            self.played_history[guild_id] = set()
        return self.played_history[guild_id]

    def clear_guild(self, guild_id: int) -> None:
        self.queues.pop(guild_id, None)
        self.current_tracks.pop(guild_id, None)
        self.loops.pop(guild_id, None)
        self.volumes.pop(guild_id, None)
        self.active_contexts.pop(guild_id, None)
        self.played_history.pop(guild_id, None)
        self.prefetched_autoplay.pop(guild_id, None)

    def build_now_playing_container(
        self,
        track: TrackItem,
        guild_id: int,
        channel_name: Optional[str] = None,
        requester: Optional[str] = None,
    ) -> CicadaContainer:
        """Create a compact, ultra-aesthetic Components V2 Container matching user requirements."""
        e_reg = self.bot.custom_emojis
        music_playing = e_reg.get("music_playing", "")
        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))

        dur_m = track.duration // 60
        dur_s = track.duration % 60
        dur_str = f"{dur_m:02d}:{dur_s:02d}" if track.duration > 0 else "Live"

        raw_req = requester or track.requester or "User"
        if isinstance(raw_req, str) and raw_req.startswith("<@") and raw_req.endswith(">"):
            raw_req = "User"
        req_str = str(raw_req)
        ch_str = f"`# {channel_name}`" if channel_name else "`Voice Channel`"
        short_artist = shorten_artist(track.author)

        container = CicadaContainer(accent_color=None)
        prefix_icon = f"{music_playing} " if music_playing else ""
        header_tag = " `[Autoplay]`" if "Autoplay" in str(track.requester) else ""

        # Section with Thumbnail Accessory on the Right (Music_Playing in front, no trailing emoji)
        container.add_section(
            content=(
                f"**{prefix_icon}Now Playing{header_tag}**\n"
                f"> **Title:** [{track.title}]({track.url})\n"
                f"> **Artist:** `{short_artist}`\n"
                f"> **Duration:** `{dur_str}`"
            ),
            accessory={"type": 11, "media": {"url": track.thumbnail}} if track.thumbnail else None,
        )
        container.add_separator(divider=True)

        # Meta Info (Channel, Requester - Bitrate removed)
        container.add_text(
            f"{dot} **Channel:** {ch_str}\n"
            f"{dot} **Requested By:** {req_str}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Cicada 3301 Music Engine")
        return container

    def _handle_track_finish(self, ctx: CustomContext, error: Optional[Exception]) -> None:
        """Safe track finish callback to advance the queue or trigger Autoplay."""
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
        """Internal helper to start audio stream with in-memory jitter buffer and background pre-fetching."""
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

            # Record to played history to prevent Autoplay repetition
            played = self.get_played_history(ctx.guild.id)
            if track.stream_url:
                played.add(track.stream_url)
            if track.url:
                played.add(track.url)

            # Trigger background pre-fetch for instant Autoplay transition
            if self.get_autoplay(ctx.guild.id):
                asyncio.run_coroutine_threadsafe(
                    self._prefetch_autoplay(ctx, track),
                    self.bot.loop,
                )

            # Record listener analytics
            if ctx.author and not ctx.author.bot:
                asyncio.run_coroutine_threadsafe(
                    self.analytics.record_play(
                        user_id=ctx.author.id,
                        guild_id=ctx.guild.id,
                        track_title=track.title,
                        artist=track.author,
                        source="bot",
                    ),
                    self.bot.loop,
                )
        except Exception as ex:
            logger.error(f"Error streaming track '{track.title}': {ex}", exc_info=ex)
            self.play_next(ctx)

    async def _prefetch_autoplay(self, ctx: CustomContext, track: TrackItem) -> None:
        """Pre-fetch next related track into RAM for 0ms gapless Autoplay transition."""
        guild_id = ctx.guild.id
        try:
            played = self.get_played_history(guild_id)
            next_track = await MusicResolver.recommend_next_track(
                current_track=track,
                played_urls=played,
            )
            if next_track:
                self.prefetched_autoplay[guild_id] = next_track
                logger.info(f"Autoplay pre-fetched '{next_track.title}' for guild {guild_id}")
        except Exception as e:
            logger.debug(f"Autoplay prefetch notice: {e}")

    def play_next(self, ctx: CustomContext) -> None:
        """Play next track in queue or trigger seamless Autoplay."""
        guild_id = ctx.guild.id
        voice_client: discord.VoiceClient = ctx.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return

        queue = self.get_queue(guild_id)
        if queue:
            next_track = queue.pop(0)
            self.current_tracks[guild_id] = next_track
            try:
                self._play_stream(ctx, next_track)

                ch_name = voice_client.channel.name if voice_client.channel else None
                container = self.build_now_playing_container(
                    next_track,
                    guild_id,
                    channel_name=ch_name,
                    requester=next_track.requester,
                )
                view = MusicControlView(self.bot, self, guild_id)
                asyncio.run_coroutine_threadsafe(
                    send_container_response(ctx, container, view=view),
                    self.bot.loop,
                )
            except Exception as ex:
                logger.error(f"Error starting next track: {ex}", exc_info=ex)
                self.play_next(ctx)
        elif self.get_autoplay(guild_id):
            prefetched = self.prefetched_autoplay.pop(guild_id, None)
            if prefetched:
                prefetched.requester = "Autoplay"
                self.current_tracks[guild_id] = prefetched
                self._play_stream(ctx, prefetched)

                ch_name = voice_client.channel.name if voice_client.channel else None
                container = self.build_now_playing_container(
                    prefetched,
                    guild_id,
                    channel_name=ch_name,
                    requester="Autoplay",
                )
                view = MusicControlView(self.bot, self, guild_id)
                asyncio.run_coroutine_threadsafe(
                    send_container_response(ctx, container, view=view),
                    self.bot.loop,
                )
            else:
                last_track = self.current_tracks.get(guild_id)
                if last_track:
                    asyncio.run_coroutine_threadsafe(
                        self._trigger_autoplay_recommendation(ctx, last_track),
                        self.bot.loop,
                    )
                else:
                    self.current_tracks.pop(guild_id, None)
        else:
            self.current_tracks.pop(guild_id, None)

    async def _trigger_autoplay_recommendation(self, ctx: CustomContext, last_track: TrackItem) -> None:
        """Fetch and stream next related track if prefetch was not available."""
        guild_id = ctx.guild.id
        voice_client: discord.VoiceClient = ctx.guild.voice_client
        if not voice_client or not voice_client.is_connected() or not voice_client.channel:
            return

        played = self.get_played_history(guild_id)
        next_track = await MusicResolver.recommend_next_track(
            current_track=last_track,
            played_urls=played,
        )

        if next_track and voice_client.is_connected():
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            next_track.requester = "Autoplay"
            self.current_tracks[guild_id] = next_track
            self._play_stream(ctx, next_track)

            ch_name = voice_client.channel.name if voice_client.channel else None
            container = self.build_now_playing_container(
                next_track,
                guild_id,
                channel_name=ch_name,
                requester="Autoplay",
            )
            view = MusicControlView(self.bot, self, guild_id)
            await send_container_response(ctx, container, view=view)
        elif not next_track:
            self.current_tracks.pop(guild_id, None)
