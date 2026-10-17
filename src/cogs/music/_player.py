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
        self.smart_autoplay: bool = True
        self.autoplay_history: Set[str] = set()

        # UI & Communication
        self.home_channel: Optional[discord.TextChannel | discord.Thread] = None
        self.controller_message: Optional[discord.Message] = None
        self._disconnect_announced: bool = False
        self._empty_vc_task: Optional[asyncio.Task] = None

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
        except Exception as e:
            logger.error(f"Guild {self.guild.id}: Wavelink connect error: {e}")
            raise

    # ── Playback Engine ──

    async def play_track(self, track: Track, message_to_edit: Optional[discord.Message] = None) -> None:
        """Stream a track via the dedicated Lavalink node with 0% stutter."""
        if not self.voice_client or not self.voice_client.connected:
            vc = self.guild.voice_client
            if vc and isinstance(vc, wavelink.Player) and vc.connected:
                self.voice_client = vc
            else:
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
            return

        self.current = track
        self.autoplay_history.add(track.title.lower())

        # Start playback on Lavalink node with volume
        vol_int = int(self.volume * 100)
        await self.voice_client.play(playable, volume=vol_int)

        # Send sleek Now Playing card with buttons
        await self.send_now_playing_card(track, message_to_edit=message_to_edit)

    async def _resolve_playable(self, track: Track) -> Optional[wavelink.Playable]:
        """Resolve Lavalink Playable via direct playable, Wavelink search, or stream URL."""
        # ── Priority 1: Attached Playable ──
        playable = getattr(track, "_playable", None)
        if playable:
            return playable

        # ── Priority 2: Direct Wavelink Resolution (YouTube, Spotify, SoundCloud) ──
        search_target = track.url or track.query or f"{track.title} {track.author}".strip()
        if search_target:
            try:
                lookup = search_target if search_target.startswith("http") else f"ytmsearch:{search_target}"
                results = await wavelink.Playable.search(lookup)
                if results:
                    return results[0] if isinstance(results, list) else results.tracks[0]
            except Exception as e:
                logger.debug(f"Direct Lavalink resolve error for '{search_target}': {e}")

        # ── Priority 3: Direct 320kbps HTTP Stream Fallback ──
        if track.stream_url:
            try:
                node = wavelink.Pool.get_node()
                results = await node.fetch_tracks(track.stream_url)
                if results:
                    return results[0] if isinstance(results, list) else results.tracks[0]
            except Exception as e:
                logger.debug(f"Direct Lavalink HTTP load error for '{track.title}': {e}")

        return None

    # ── Controls ──

    def pause(self) -> None:
        """Pause playback."""
        if self.voice_client and self.voice_client.playing:
            asyncio.create_task(self.voice_client.pause(True))

    def resume(self) -> None:
        """Resume playback."""
        if self.voice_client and self.voice_client.paused:
            asyncio.create_task(self.voice_client.pause(False))

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

        if self.controller_message:
            try:
                await self.controller_message.delete()
            except Exception:
                pass
            self.controller_message = None

    def set_volume(self, volume_percent: int) -> int:
        """Adjust volume (0 - 150%)."""
        clamped = max(0, min(150, volume_percent))
        self.volume = clamped / 100.0
        if self.voice_client:
            asyncio.create_task(self.voice_client.set_volume(clamped))
        return clamped

    # ── Track End & Autoplay Transition ──

    async def on_track_end(self) -> None:
        """Invoked when Lavalink finishes playing a track."""
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
            rec = await NativeSmartAutoplay.get_next_recommendation(
                self.current, self.autoplay_history, self.bot.db
            )
            if rec:
                rec.requester = "Kyro Autoplay"
                await self.play_track(rec)
            else:
                self.current = None
                self.schedule_empty_vc_timer()
        else:
            self.current = None
            self.schedule_empty_vc_timer()

    # ── Components V2 Controller Card ──

    def build_now_playing_container(self, track: Track) -> KyroContainer:
        """Construct the Components V2 Now Playing card."""
        e_reg = getattr(self.bot, "custom_emojis", {})
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### {track.title}\n"
                f"> **Artist:** `{track.author or 'Unknown'}`\n"
                f"> **Duration:** `{track.formatted_duration}` • **Source:** `Lavalink 320kbps`\n"
                f"> **Requested by:** {track.requester}"
            )
        )

        if track.thumbnail:
            container.add_thumbnail(track.thumbnail)

        container.add_separator(divider=True)

        ap_status = "ON" if self.smart_autoplay else "OFF"
        q_len = len(self.queue)
        vol_pct = int(self.volume * 100)
        container.add_text(
            f"-# Volume: `{vol_pct}%` • Loop: `{self.loop_mode.upper()}` • Autoplay: `{ap_status}` • Queue: `{q_len}`"
        )
        return container

    async def send_now_playing_card(self, track: Track, message_to_edit: Optional[discord.Message] = None) -> None:
        """Post or edit the interactive Now Playing card in home channel."""
        if not self.home_channel:
            return

        container = self.build_now_playing_container(track)
        view = MusicControlView(self.bot, player=self)

        if message_to_edit and isinstance(message_to_edit, discord.Message):
            try:
                await edit_container_response(message_to_edit, container, view=view)
                self.controller_message = message_to_edit
                return
            except Exception:
                pass

        if self.controller_message and self.controller_message != message_to_edit:
            try:
                await self.controller_message.delete()
            except Exception:
                pass
            self.controller_message = None

        try:
            self.controller_message = await send_container_response(
                self.home_channel, container, view=view
            )
        except Exception as e:
            logger.debug(f"Failed to send now playing card: {e}")

    async def update_controller_message(self, force: bool = False) -> None:
        """Refresh active controller card."""
        if not self.controller_message or not self.current:
            return

        container = self.build_now_playing_container(self.current)
        view = MusicControlView(self.bot, player=self)
        try:
            await edit_container_response(self.controller_message, container, view=view)
        except Exception as e:
            logger.debug(f"Failed to edit controller message: {e}")

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
                if self.home_channel and not self._disconnect_announced:
                    c = KyroContainer(accent_color=None)
                    c.add_text("-# Left voice channel due to inactivity.")
                    try:
                        await send_container_response(self.home_channel, c)
                    except Exception:
                        pass
                await self.stop()
        except asyncio.CancelledError:
            pass
