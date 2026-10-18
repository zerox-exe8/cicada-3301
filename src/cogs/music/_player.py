"""
Kyro Discord Bot - Lavalink Guild Audio Player
Streamlined, zero-lag, zero-stutter audio streaming powered by NexCloud Lavalink v4.
Offloads all heavy audio processing, buffering, and encoding from Render/PC to the Lavalink node.
Maintains full compatibility with Kyro Components V2 interactive cards and commands.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, List, Optional, Set
import discord
import wavelink

from src.cogs.music._models import Track
from src.cogs.music._autoplay import NativeSmartAutoplay
from src.cogs.music._extractor import NativeExtractor
from src.utils.containers import KyroContainer, send_container_response, edit_container_response
from src.cogs.music._views import MusicControlView

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Music.Player")


def shorten_artist(artist: str, max_len: int = 30) -> str:
    """Safely truncate artist string for embeds."""
    if not artist:
        return "Unknown"
    return artist if len(artist) <= max_len else artist[:max_len - 3] + "..."


class GuildPlayer:
    """
    High-Performance Lavalink Guild Player for Kyro Bot.
    Replaces local FFmpeg subprocesses with dedicated Lavalink node streaming.
    """

    def __init__(self, bot: KyroBot, guild: discord.Guild) -> None:
        self.bot = bot
        self.guild = guild
        self.voice_client: Optional[wavelink.Player] = None

        # Playback state
        self.queue: List[Track] = []
        self.current: Optional[Track] = None
        self.volume: float = 1.0  # Normalized (1.0 = 100%)
        self.loop_mode: str = "off"  # "off", "track", "queue"
        self.smart_autoplay: bool = False
        self.autoplay_history: Set[str] = set()

        # UI & Communication
        self.home_channel: Optional[discord.TextChannel | discord.Thread] = None
        self.controller_message: Optional[discord.Message] = None
        self._disconnect_announced: bool = False
        self._empty_vc_task: Optional[asyncio.Task] = None
        self._advance_lock: asyncio.Lock = asyncio.Lock()
        self._last_advance_time: float = 0.0

    # ── State Properties ──

    @property
    def is_connected(self) -> bool:
        """Check if connected to a valid Discord voice channel."""
        vc = self.guild.voice_client
        return vc is not None and getattr(vc, "connected", False)

    @property
    def is_playing(self) -> bool:
        """Check if actively playing audio."""
        vc = self.guild.voice_client
        if vc and isinstance(vc, wavelink.Player):
            return vc.playing and not vc.paused
        return False

    @property
    def is_paused(self) -> bool:
        """Check if playback is currently paused."""
        vc = self.guild.voice_client
        if vc and isinstance(vc, wavelink.Player):
            return vc.paused
        return False

    # ── Voice Connection ──

    async def connect_voice(self, channel: discord.VoiceChannel | discord.StageChannel) -> None:
        """Connect or move to the specified voice channel using Wavelink."""
        vc = self.guild.voice_client
        if vc and isinstance(vc, wavelink.Player):
            if vc.channel and vc.channel.id != channel.id:
                await vc.move_to(channel)
            self.voice_client = vc
            return

        # If connected to a non-wavelink player (e.g. leftover discord.VoiceClient), disconnect it first
        if vc and not isinstance(vc, wavelink.Player):
            try:
                await vc.disconnect(force=True)
            except Exception:
                pass

        # Ensure Wavelink node is connected before connecting player
        try:
            wavelink.Pool.get_node()
        except Exception:
            from src.core.config import Config
            try:
                node = wavelink.Node(
                    uri=Config.LAVALINK_URI,
                    password=Config.LAVALINK_PASSWORD,
                    inactive_player_timeout=300,
                )
                await wavelink.Pool.connect(nodes=[node], client=self.bot)
                for _ in range(10):
                    if node.status == wavelink.NodeStatus.CONNECTED:
                        break
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"On-demand Lavalink node connect error: {e}")

        # Connect as Wavelink Player
        try:
            self.voice_client = await channel.connect(cls=wavelink.Player, self_deaf=True)
            if self.voice_client:
                self.voice_client.autoplay = wavelink.AutoPlayMode.disabled
        except Exception as e:
            logger.error(f"Guild {self.guild.id}: Wavelink connect error: {e}")
            raise

    # ── Playback Engine ──

    async def play_track(self, track: Track, message_to_edit: Optional[discord.Message] = None) -> None:
        """Stream a track via the dedicated Lavalink node with 0% stutter."""
        if not self.voice_client or not self.voice_client.connected:
            vc = self.guild.voice_client
            if vc and isinstance(vc, wavelink.Player):
                self.voice_client = vc

        # If voice client is still completing handshake, wait briefly
        if self.voice_client and not self.voice_client.connected:
            for _ in range(6):
                await asyncio.sleep(0.5)
                if self.voice_client.connected:
                    break

        if not self.voice_client or not self.voice_client.connected:
            logger.warning(f"Guild {self.guild.id}: Cannot play, voice client not connected.")
            return

        # Direct playable if already resolved, otherwise resolve via Lavalink
        playable = getattr(track, "_playable", None)
        if not playable:
            playable = await self._resolve_playable(track)

        if not playable:
            logger.error(f"Guild {self.guild.id}: Lavalink could not resolve playable for '{track.title}'")
            # Try next in queue if available
            if self.queue:
                next_t = self.queue.pop(0)
                await self.play_track(next_t, message_to_edit=message_to_edit)
            else:
                self.current = None
                await self.send_queue_ended_card()
                self.schedule_empty_vc_timer()
            return

        self.current = track
        self.autoplay_history.add(track.title.lower())
        self._last_advance_time = time.time()
        self._was_paused_for_empty_vc = False

        # Start playback on Lavalink node with volume (explicitly unpaused)
        vol_int = int(self.volume * 100)
        await self.voice_client.play(playable, volume=vol_int, paused=False)

        # Send sleek Now Playing card with buttons
        await self.send_now_playing_card(track, message_to_edit=message_to_edit)

    # Domains that are NOT direct audio streams — Lavalink can't play their page URLs
    _NON_STREAM_DOMAINS = (
        "jiosaavn.com",
        "spotify.com",
        "open.spotify.com",
        "music.youtube.com",
        "soundcloud.com",
        "youtube.com/watch",
        "youtu.be",
    )

    def _is_direct_stream_url(self, url: str) -> bool:
        """Return True only if url is a raw audio stream Lavalink can play via HTTP."""
        if not url or not url.startswith("http"):
            return False
        # Only JioSaavn Akamai MP4/AAC CDN direct streams are 100% playable via Lavalink HTTP.
        # SoundCloud HLS (.m3u8), Spotify web, YouTube links return 403 on raw HTTP.
        u_low = url.lower()
        if any(dom in u_low for dom in ("saavncdn.com", "jiosaavn.com")) and ".mp4" in u_low:
            return True
        return False

    async def _resolve_playable(self, track: Track) -> Optional[wavelink.Playable]:
        """Resolve Lavalink Playable via direct unblocked CDN stream, attached playable, or search."""
        # ── Priority 1: Direct Stream URL (JioSaavn 320kbps CDN stream) ──
        # Direct Akamai HTTP streams are 100% unblocked on Lavalink
        stream_url = getattr(track, "stream_url", None)
        if stream_url and self._is_direct_stream_url(stream_url):
            try:
                results = await wavelink.Playable.search(stream_url)
                if results:
                    return results[0] if isinstance(results, list) else results.tracks[0]
            except Exception as e:
                logger.debug(f"Direct stream URL resolve error for '{stream_url}': {e}")

        # ── Priority 1.5: If no stream_url, resolve via NativeExtractor CDN first ──
        if not stream_url:
            try:
                from src.cogs.music._extractor import NativeExtractor
                target_q = track.query or f"{track.title} {track.author}".strip() or track.url
                if target_q:
                    ext = await NativeExtractor.extract(target_q, requester=track.requester)
                    if ext and ext.stream_url and self._is_direct_stream_url(ext.stream_url):
                        track.stream_url = ext.stream_url
                        results = await wavelink.Playable.search(ext.stream_url)
                        if results:
                            return results[0] if isinstance(results, list) else results.tracks[0]
            except Exception as e:
                logger.debug(f"NativeExtractor resolve fallback error: {e}")

        # ── Priority 2: Attached Playable (already resolved by play.py Step 1) ──
        playable = getattr(track, "_playable", None)
        if playable:
            return playable

        # ── Priority 3: Direct URL (YouTube, SoundCloud, direct stream) ──
        url = track.url or ""
        if url.startswith(("http://", "https://")):
            try:
                results = await wavelink.Playable.search(url)
                if results:
                    return results[0] if isinstance(results, list) else results.tracks[0]
            except Exception as e:
                logger.debug(f"Direct URL resolve error for '{url}': {e}")

        # ── Priority 4: Search Fallbacks (YouTube Music -> YouTube -> Spotify) ──
        search_target = f"{track.title} {track.author}".strip() or track.query or track.title
        if search_target:
            try:
                results = await wavelink.Playable.search(search_target, source=wavelink.TrackSource.YouTubeMusic)
                if results:
                    return results[0] if isinstance(results, list) else results.tracks[0]
            except Exception as e:
                logger.debug(f"YouTube Music search error for '{search_target}': {e}")

        if search_target:
            try:
                results = await wavelink.Playable.search(search_target, source=wavelink.TrackSource.YouTube)
                if results:
                    return results[0] if isinstance(results, list) else results.tracks[0]
            except Exception as e:
                logger.debug(f"YouTube search error for '{search_target}': {e}")

        if search_target:
            try:
                results = await wavelink.Playable.search(f"spsearch:{search_target}")
                if results:
                    return results[0] if isinstance(results, list) else results.tracks[0]
            except Exception as e:
                logger.debug(f"Spotify search error for '{search_target}': {e}")

        return None

    # ── Controls ──

    def pause(self) -> bool:
        """Pause playback."""
        if self.voice_client and self.voice_client.playing and not self.voice_client.paused:
            asyncio.create_task(self.voice_client.pause(True))
            return True
        return False

    def resume(self) -> bool:
        """Resume playback."""
        if self.voice_client and self.voice_client.paused:
            asyncio.create_task(self.voice_client.pause(False))
            self._was_paused_for_empty_vc = False
            return True
        return False

    async def skip(self) -> None:
        """Skip currently playing track."""
        if self.voice_client:
            await self.voice_client.skip(force=True)

    async def stop(self) -> None:
        """Stop playback and disconnect."""
        self.queue.clear()
        self.current = None

        if self.voice_client:
            try:
                await self.voice_client.disconnect()
            except Exception:
                pass
            self.voice_client = None

        # Clear reference without deleting card from chat
        self.controller_message = None

    def set_volume(self, volume_percent: int) -> int:
        """Adjust volume (0 - 150%)."""
        clamped = max(0, min(150, volume_percent))
        self.volume = clamped / 100.0
        if self.voice_client:
            asyncio.create_task(self.voice_client.set_volume(clamped))
        return clamped

    def set_loop_mode(self, mode: Optional[str] = None) -> str:
        """
        Cycle loop mode or set specific mode ('off', 'track', 'queue').
        Accepts: 'off', 'track', 'queue', 'song', 'all', 'toggle', or None.
        """
        modes = ["off", "track", "queue"]
        m_str = (mode or "").strip().lower()

        if m_str in ("track", "song", "single", "1"):
            self.loop_mode = "track"
        elif m_str in ("queue", "all", "q"):
            self.loop_mode = "queue"
        elif m_str in ("off", "none", "disable", "stop", "0"):
            self.loop_mode = "off"
        else:
            cur_idx = modes.index(self.loop_mode) if self.loop_mode in modes else 0
            self.loop_mode = modes[(cur_idx + 1) % len(modes)]

        return self.loop_mode

    # ── Track End & Autoplay Transition ──

    async def on_track_end(self, reason: Optional[str] = None) -> None:
        """Invoked when Lavalink finishes playing a track."""
        if reason and str(reason).lower() in ("replaced", "cleanup"):
            return

        if reason and str(reason).lower() in ("loadfailed", "load_failed"):
            logger.warning(f"Guild {self.guild.id}: Lavalink reported track loadFailed.")
            # If track failed on Lavalink (e.g. YouTube blocked), attempt recovery via unblocked JioSaavn CDN stream
            cur_track = self.current
            if cur_track and not getattr(cur_track, "_cdn_recovered", False):
                cur_track._cdn_recovered = True
                try:
                    from src.cogs.music._extractor import NativeExtractor
                    target_q = cur_track.query or f"{cur_track.title} {cur_track.author}".strip() or cur_track.title
                    ext = await NativeExtractor.extract(target_q, requester=cur_track.requester)
                    if ext and ext.stream_url and self._is_direct_stream_url(ext.stream_url):
                        cur_track.stream_url = ext.stream_url
                        cur_track._playable = None
                        logger.info(f"Guild {self.guild.id}: Recovering failed track with JioSaavn CDN stream: '{cur_track.title}'")
                        await self.play_track(cur_track)
                        return
                except Exception as e:
                    logger.debug(f"CDN track recovery error: {e}")

            if self.queue:
                next_track = self.queue.pop(0)
                await self.play_track(next_track)
            else:
                self.current = None
                await self.send_queue_ended_card()
                self.schedule_empty_vc_timer()
            return

        now = time.time()
        if now - self._last_advance_time < 0.8:
            logger.debug(f"Guild {self.guild.id}: Duplicate on_track_end call debounced")
            return

        async with self._advance_lock:
            self._last_advance_time = time.time()
            if self.loop_mode == "track" and self.current:
                await self.play_track(self.current)
                return
            elif self.loop_mode == "queue" and self.current:
                self.queue.append(self.current)

            if self.queue:
                next_track = self.queue.pop(0)
                await self.play_track(next_track)
            elif self.smart_autoplay and self.current:
                # Smart Autoplay AI recommendation
                try:
                    rec = await NativeSmartAutoplay.get_next_recommendation(
                        self.current, self.autoplay_history, self.bot.db
                    )
                    if rec:
                        rec.requester = "⚡ Smart Autoplay"
                        await self.play_track(rec)
                    else:
                        self.current = None
                        await self.send_queue_ended_card()
                        self.schedule_empty_vc_timer()
                except Exception as e:
                    logger.error(f"Guild {self.guild.id}: Smart autoplay error: {e}", exc_info=True)
                    self.current = None
                    await self.send_queue_ended_card()
                    self.schedule_empty_vc_timer()
            else:
                self.current = None
                await self.send_queue_ended_card()
                self.schedule_empty_vc_timer()

    # ── Components V2 Controller Card ──

    def build_now_playing_container(self, track: Track) -> KyroContainer:
        """Construct the Components V2 Now Playing card matching custom layout."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        heart_e = ""
        if e_reg:
            heart_e = (
                e_reg.get("heart_dot", "")
                or e_reg.get("icons_heart", "")
                or e_reg.get("heart", "")
            )
        link_emoji = e_reg.get("link", "") if e_reg else ""

        container = KyroContainer(accent_color=None)

        # 1. Title: Now Playing (ZERO emoji on title)
        container.add_text("## Now Playing")

        # 2. 1 Divider line directly beneath Now Playing
        container.add_separator(divider=True)

        # 3. Song, Artist, and Duration with heart emoji in front (NO normal/unicode emojis, no source)
        song_display = f"[{track.title}]({track.url})" if track.url else track.title
        artist_display = track.author or "Unknown Artist"
        duration_display = track.formatted_duration or "00:00"

        bullet = f"{heart_e} " if heart_e else "> "
        link_prefix = f"{link_emoji} " if link_emoji else ""

        body_lines = [
            f"{bullet}**Song:** {song_display}",
            f"{bullet}**Artist:** `{artist_display}`",
            f"{bullet}**Duration:** `{duration_display}`",
        ]
        if track.url:
            body_lines.append(f"> {link_prefix}[Track Link]({track.url})")

        container.add_section(content="\n".join(body_lines))

        # Resolve thumbnail (fallback to YouTube thumbnail if missing)
        thumb = track.thumbnail
        if not thumb and track.url and ("youtube.com" in track.url or "youtu.be" in track.url):
            import re
            m = re.search(r"(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})", track.url)
            if m:
                thumb = f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg"
                track.thumbnail = thumb

        if thumb:
            container.add_thumbnail(thumb)

        # 4. Divider line before footer
        container.add_separator(divider=True)

        # 5. Footer: Requested by (+ player state indicators without unicode bullets)
        vol_pct = int(self.volume * 100)
        ap_status = "ON" if self.smart_autoplay else "OFF"
        container.add_text(
            f"-# Requested by: {track.requester} | Vol: `{vol_pct}%` | Loop: `{self.loop_mode.upper()}` | Autoplay: `{ap_status}`"
        )
        return container

    async def send_now_playing_card(self, track: Track, message_to_edit: Optional[discord.Message] = None) -> None:
        """Post or edit the interactive Now Playing card in home channel."""
        if not self.home_channel:
            return

        container = self.build_now_playing_container(track)
        view = MusicControlView(self.bot, player=self, track_url=track.url)

        target = message_to_edit or self.controller_message
        if target and isinstance(target, discord.Message):
            try:
                await edit_container_response(target, container, view=view, content=None)
                self.controller_message = target
                return
            except Exception as e:
                logger.debug(f"Failed to edit existing controller message: {e}")

        try:
            msg = await send_container_response(
                self.home_channel, container, view=view, content=None
            )
            if isinstance(msg, discord.Message):
                self.controller_message = msg
        except Exception as e:
            logger.debug(f"Failed to send now playing card: {e}")

    async def update_controller_message(self, force: bool = False) -> None:
        """Refresh active controller card."""
        if not self.controller_message or not self.current:
            return

        container = self.build_now_playing_container(self.current)
        view = MusicControlView(self.bot, player=self, track_url=self.current.url)
        try:
            await edit_container_response(self.controller_message, container, view=view, content=None)
        except Exception as e:
            logger.debug(f"Failed to edit controller message: {e}")

    async def send_queue_ended_card(self) -> None:
        """Post or edit the Queue Ended card in home channel."""
        if not self.home_channel:
            return

        dot = self.bot.custom_emojis.get("heart_dot", "")
        bullet = f"{dot} " if dot else "> "

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"# **Queue Concluded**\n"
                f"{bullet}All queued songs have finished playing.\n"
                f"> Add more tracks using `?play <song>` or enable autoplay with `?autoplay on`!"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Disconnecting in 3 minutes if no new songs are added.")
        container.add_separator(divider=True)

        if self.controller_message and isinstance(self.controller_message, discord.Message):
            try:
                await edit_container_response(
                    self.controller_message,
                    container,
                    view=None,
                    content=None,
                )
                self.controller_message = None
                return
            except Exception:
                pass

        try:
            await send_container_response(
                self.home_channel,
                container,
                content=None,
            )
        except Exception:
            pass

    # ── Inactivity Timers ──

    def cancel_empty_vc_timer(self, auto_resume: bool = False) -> None:
        """Cancel idle disconnect timer."""
        if self._empty_vc_task and not self._empty_vc_task.done():
            self._empty_vc_task.cancel()
            self._empty_vc_task = None

    def schedule_empty_vc_timer(self) -> None:
        """Schedule disconnect after 3 minutes of idle queue."""
        self.cancel_empty_vc_timer()
        self._empty_vc_task = asyncio.create_task(self._empty_vc_timeout(180))

    async def _empty_vc_timeout(self, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
            if not self.is_playing and not self.queue:
                logger.info(f"Guild {self.guild.id}: Idle timeout reached, disconnecting silently.")
                await self.stop()
        except asyncio.CancelledError:
            pass
