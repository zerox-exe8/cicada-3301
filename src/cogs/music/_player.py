"""
Kyro Discord Bot - Custom Lavalink V4 Player
Subclasses wavelink.Player to provide Components V2 UI, gapless streaming,
Smart Autoplay background pre-fetching, and race-condition protected queue controls.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import TYPE_CHECKING, Optional, Set

import discord
import wavelink

from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Music.Player")


def shorten_artist(raw_artist: str, max_chars: int = 32) -> str:
    """Shorten multi-artist strings to prevent card layout breaking."""
    if not raw_artist:
        return "Official Artist"
    clean = html.unescape(raw_artist).strip()
    parts = re.split(r"[,/|]|\s+(?:feat\.?|ft\.?|and|&)\s+", clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) > 2:
        clean = f"{parts[0]}, {parts[1]} & others"
    elif len(parts) == 2:
        clean = f"{parts[0]} & {parts[1]}"
    if len(clean) > max_chars:
        clean = clean[: max_chars - 3].rstrip() + "..."
    return clean


class KyroPlayer(wavelink.Player):
    """Production-grade Lavalink V4 player for Kyro with Smart Autoplay."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.home_channel: Optional[discord.abc.Messageable] = None
        self.now_playing_message: Optional[discord.Message] = None
        
        # AutoPlayMode.partial allows Wavelink to cleanly auto-advance player.queue without double-play race conditions
        self.autoplay: wavelink.AutoPlayMode = wavelink.AutoPlayMode.partial
        self.smart_autoplay: bool = False
        self._loop_state: str = "off"  # "off", "track", "queue"
        
        # Smart Autoplay Session Memory & Pre-fetch Cache
        self.played_history: Set[str] = set()
        self.prefetched_autoplay_track: Optional[wavelink.Playable] = None
        self.consecutive_same_artist: int = 0
        self.last_artist: str = ""
        self._prefetch_lock = asyncio.Lock()
        self._prefetch_task: Optional[asyncio.Task] = None

    async def on_voice_server_update(self, data: dict, /) -> None:
        """Handle Discord voice server update and dispatch to Lavalink."""
        logger.debug(f"KyroPlayer {self.guild.id} on_voice_server_update: {data.get('endpoint')}")
        await super().on_voice_server_update(data)
        # Ensure dispatch runs if session_id is already available
        voice_data = self._voice_state.get("voice", {})
        if voice_data.get("session_id") and voice_data.get("token") and voice_data.get("endpoint"):
            await self._dispatch_voice_update()

    async def on_voice_state_update(self, data: dict, /) -> None:
        """Handle Discord voice state update and guarantee Lavalink voice connection."""
        logger.debug(f"KyroPlayer {self.guild.id} on_voice_state_update: channel={data.get('channel_id')}")
        await super().on_voice_state_update(data)
        # Fix race condition: If VOICE_SERVER_UPDATE arrived before VOICE_STATE_UPDATE, dispatch now!
        voice_data = self._voice_state.get("voice", {})
        if voice_data.get("session_id") and voice_data.get("token") and voice_data.get("endpoint"):
            await self._dispatch_voice_update()

    def set_loop_mode(self, mode: str) -> str:
        """Set loop mode: 'off', 'track' (single song), 'queue' (all songs)."""
        mode = mode.lower().strip()
        if mode in ("track", "song", "1"):
            self.queue.mode = wavelink.QueueMode.loop
            self._loop_state = "track"
        elif mode in ("queue", "all"):
            self.queue.mode = wavelink.QueueMode.loop_all
            self._loop_state = "queue"
        else:
            self.queue.mode = wavelink.QueueMode.normal
            self._loop_state = "off"
        return self._loop_state

    def get_loop_mode(self) -> str:
        """Get current loop state."""
        if self.queue.mode == wavelink.QueueMode.loop:
            return "track"
        elif self.queue.mode == wavelink.QueueMode.loop_all:
            return "queue"
        return "off"

    def record_track_start(self, track: wavelink.Playable) -> None:
        """Record track in session history and trigger background Autoplay pre-fetch."""
        if not track:
            return

        # Record title & URI in history set
        if track.title:
            self.played_history.add(track.title.lower().strip())
        if track.uri:
            self.played_history.add(track.uri.lower().strip())

        # Track consecutive artist counter for anti-fatigue
        author_clean = (track.author or "").lower().strip()
        if author_clean and author_clean == self.last_artist:
            self.consecutive_same_artist += 1
        else:
            self.consecutive_same_artist = 1
            self.last_artist = author_clean

        # Trigger background pre-fetch for 0ms gapless Autoplay transition
        if self.smart_autoplay:
            if self._prefetch_task and not self._prefetch_task.done():
                self._prefetch_task.cancel()
            self._prefetch_task = asyncio.create_task(self._async_prefetch(track))

    async def _async_prefetch(self, track: wavelink.Playable) -> None:
        """Background coroutine to pre-resolve next recommended track in RAM."""
        async with self._prefetch_lock:
            try:
                from src.cogs.music._autoplay import SmartAutoplayEngine
                next_track = await SmartAutoplayEngine.get_next_track(
                    current_track=track,
                    played_history=self.played_history,
                    consecutive_same_artist=self.consecutive_same_artist,
                )
                if next_track:
                    self.prefetched_autoplay_track = next_track
                    logger.info(f"Autoplay Pre-fetched in RAM: '{next_track.title}' for guild {self.guild.id}")
            except Exception as e:
                logger.debug(f"Autoplay pre-fetch notice: {e}")

    def build_now_playing_container(
        self,
        track: wavelink.Playable,
        requester: Optional[str] = None,
    ) -> KyroContainer:
        """Build signature Discord Components V2 Type 17 cyber container for active track."""
        bot: KyroBot = self.client  # type: ignore
        e_reg = bot.custom_emojis
        music_icon = e_reg.get("music_playing", "")
        play_prefix = f"{music_icon} " if music_icon else ""
        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))

        # Calculate duration
        duration_ms = track.length if track.length else 0
        duration_sec = duration_ms // 1000
        dur_m = duration_sec // 60
        dur_s = duration_sec % 60
        dur_str = f"{dur_m:02d}:{dur_s:02d}" if duration_sec > 0 else "Live Stream"

        short_artist = shorten_artist(track.author or "Official Artist")
        track_url = track.uri or "https://discord.com"
        thumbnail_url = track.artwork

        # Extract requester from track extras or argument
        req_name = requester
        if not req_name and hasattr(track, "extras") and hasattr(track.extras, "requester"):
            req_name = track.extras.requester
        if not req_name:
            req_name = "DJ / AutoPlay"

        is_autoplay = "autoplay" in str(req_name).lower() or "smart autoplay" in str(req_name).lower()
        title_prefix = f"**{play_prefix}Now Playing `[⚡ Smart Autoplay Radio]`**" if is_autoplay else f"**{play_prefix}Now Playing Studio Master**"

        channel_name = self.channel.name if self.channel else "Voice Channel"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"{title_prefix}\n"
                f"> **Title:** [{track.title}]({track_url})\n"
                f"> **Artist:** `{short_artist}`\n"
                f"> **Duration:** `{dur_str}`"
            ),
            accessory={"type": 11, "media": {"url": thumbnail_url}} if thumbnail_url else None,
        )

        container.add_separator(divider=True)

        loop_mode = self.get_loop_mode().upper()
        ap_mode = "ON" if self.smart_autoplay else "OFF"
        vol_pct = int(self.volume)

        container.add_text(
            f"{dot} **Channel:** `{channel_name}` • **Bitrate:** `320kbps CD Master`\n"
            f"{dot} **Requested By:** {req_name}\n"
            f"{dot} **Loop:** `{loop_mode}` • **AutoPlay:** `{ap_mode}` • **Volume:** `{vol_pct}%`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Kyro Studio Engine • Lavalink V4 Zero-Lag Stream")

        return container

    async def update_now_playing(self, track: wavelink.Playable) -> None:
        """Send or update now playing card with interactive view."""
        if not self.home_channel:
            return

        from src.cogs.music._views import MusicControlView

        container = self.build_now_playing_container(track)
        view = MusicControlView(self.client, self, self.guild.id)  # type: ignore

        try:
            self.now_playing_message = await send_container_response(
                self.home_channel,
                container,
                view=view,
            )
        except Exception as e:
            logger.debug(f"Could not send now playing container: {e}")
