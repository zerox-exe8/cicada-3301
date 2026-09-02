"""
Kyro Discord Bot - Native Discord Guild Audio Player
Pure Python Discord VoiceClient controller with Zero-Stutter RAM pre-buffering,
loop modes, Smart Autoplay AI, and Components V2 Cyber Container UI.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import subprocess
import threading
import time
from typing import TYPE_CHECKING, List, Optional, Set

import discord

from src.cogs.music._models import Track
from src.cogs.music._autoplay import NativeSmartAutoplay, clean_track_title
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Music.Player")


class BufferedAudioSource(discord.AudioSource):
    """
    High-Performance RAM-Buffered Audio Source.
    Pre-buffers audio in a background thread to prevent network jitter / voice cuts.
    """
    FRAME_SIZE = 3840  # 20ms of 48000Hz 16-bit stereo PCM

    def __init__(self, stream_url: str) -> None:
        self.stream_url = stream_url
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._finished = False
        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None

        self._start_ffmpeg()

    def _start_ffmpeg(self) -> None:
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            import shutil
            ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"

        cmd = [
            ffmpeg_exe,
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-probesize", "32",
            "-analyzeduration", "0",
            "-i", self.stream_url,
            "-f", "s16le",
            "-ar", "48000",
            "-ac", "2",
            "-vn",
            "-loglevel", "error",
            "pipe:1",
        ]
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=1024 * 1024,
        )
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _reader_loop(self) -> None:
        while self._process and self._process.poll() is None:
            data = self._process.stdout.read(65536)
            if not data:
                break
            with self._lock:
                self._buffer.extend(data)
                # Keep up to 10 seconds of audio pre-buffered in RAM (~1.9MB)
                while len(self._buffer) > 1920000:
                    time.sleep(0.05)
        self._finished = True

    def read(self) -> bytes:
        with self._lock:
            if len(self._buffer) >= self.FRAME_SIZE:
                chunk = bytes(self._buffer[:self.FRAME_SIZE])
                del self._buffer[:self.FRAME_SIZE]
                return chunk
            elif self._finished and len(self._buffer) > 0:
                chunk = bytes(self._buffer).ljust(self.FRAME_SIZE, b"\x00")
                self._buffer.clear()
                return chunk
            elif self._finished:
                return b""
            else:
                return b"\x00" * self.FRAME_SIZE

    def cleanup(self) -> None:
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass
            self._process = None
        with self._lock:
            self._buffer.clear()


def shorten_artist(raw_artist: str, max_chars: int = 32) -> str:
    """Shorten multi-artist strings."""
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


class GuildPlayer:
    """Guild audio player using native Discord.py VoiceClient & BufferedAudioSource."""

    def __init__(self, bot: KyroBot, guild: discord.Guild) -> None:
        self.bot = bot
        self.guild = guild
        self.voice_client: Optional[discord.VoiceClient] = None
        self.home_channel: Optional[discord.abc.Messageable] = None
        self.now_playing_message: Optional[discord.Message] = None

        self.queue: List[Track] = []
        self.current: Optional[Track] = None
        self.loop_mode: str = "off"  # "off", "track", "queue"
        self.volume: float = 1.0     # 100%
        self.smart_autoplay: bool = False
        
        self.played_history: Set[str] = set()
        self.consecutive_same_artist: int = 0
        self.last_artist: str = ""

        self._lock = asyncio.Lock()

    @property
    def is_playing(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_playing())

    @property
    def is_paused(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_paused())

    @property
    def is_connected(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_connected())

    def set_loop_mode(self, mode: str) -> str:
        """Set loop mode: 'off', 'track' (single song), 'queue' (all songs)."""
        m = mode.lower().strip()
        if m in ("track", "song", "1"):
            self.loop_mode = "track"
        elif m in ("queue", "all"):
            self.loop_mode = "queue"
        else:
            self.loop_mode = "off"
        return self.loop_mode

    def set_volume(self, vol_pct: int) -> int:
        """Set player volume (0 to 200%)."""
        clamped = max(0, min(200, vol_pct))
        self.volume = clamped / 100.0
        if self.voice_client and self.voice_client.source:
            if isinstance(self.voice_client.source, discord.PCMVolumeTransformer):
                self.voice_client.source.volume = self.volume
        return clamped

    async def connect_voice(self, channel: discord.VoiceChannel) -> None:
        """Connect or move to voice channel safely."""
        vc = self.guild.voice_client
        if vc and vc.is_connected():
            self.voice_client = vc
            if self.voice_client.channel != channel:
                await self.voice_client.move_to(channel)
            return

        self.voice_client = await channel.connect(self_deaf=True, timeout=20.0, reconnect=True)

    async def play_track(self, track: Track, message_to_edit: Optional[discord.Message] = None) -> None:
        """Stream track through RAM-buffered audio source with 0 cuts."""
        if not self.voice_client or not self.voice_client.is_connected():
            vc = self.guild.voice_client
            if vc and vc.is_connected():
                self.voice_client = vc
            else:
                return

        # Ensure Opus is loaded across Linux, Render, and Windows
        if not discord.opus.is_loaded():
            import ctypes.util
            opus_lib = ctypes.util.find_library("opus")
            if opus_lib:
                try:
                    discord.opus.load_opus(opus_lib)
                except Exception:
                    pass

            if not discord.opus.is_loaded():
                from pathlib import Path
                base_d = Path(__file__).resolve().parent.parent.parent.parent
                for lib_name in ["libopus.so.0", "libopus.so", "opus.dll", "libopus-0.dll", "libopus.dll"]:
                    cand_path = base_d / lib_name
                    target = str(cand_path) if cand_path.exists() else lib_name
                    try:
                        discord.opus.load_opus(target)
                        break
                    except Exception:
                        pass

        self.current = track
        clean_t = clean_track_title(track.title).lower()
        self.played_history.add(clean_t)

        # Anti-fatigue artist tracking
        art_clean = (track.author or "").lower().strip()
        if art_clean and art_clean == self.last_artist:
            self.consecutive_same_artist += 1
        else:
            self.consecutive_same_artist = 1
            self.last_artist = art_clean

        # Resolve FFmpeg executable
        try:
            import imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            import shutil
            ffmpeg_exe = shutil.which("ffmpeg") or "ffmpeg"

        # Direct Opus Stream with YouTube User-Agent Header & Auto-reconnect
        before_options = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin -user_agent \"Mozilla/5.0 (Windows NT 10.0; Win64; x64)\""
        vol_opt = f"-filter:a volume={self.volume}" if self.volume != 1.0 else ""
        options = f"-vn {vol_opt}".strip()

        try:
            audio_source: discord.AudioSource = discord.FFmpegOpusAudio(
                track.stream_url,
                executable=ffmpeg_exe,
                before_options=before_options,
                options=options,
            )
        except Exception:
            raw_source = discord.FFmpegPCMAudio(
                track.stream_url,
                executable=ffmpeg_exe,
                before_options=before_options,
                options=options,
            )
            audio_source = discord.PCMVolumeTransformer(raw_source, volume=self.volume)

        if self.voice_client.is_playing() or self.voice_client.is_paused():
            self.voice_client.stop()

        def _after_callback(error):
            if error:
                logger.error(f"Voice playback error in guild {self.guild.id}: {error}")
            asyncio.run_coroutine_threadsafe(self._handle_track_finish(), self.bot.loop)

        self.voice_client.play(audio_source, after=_after_callback)
        await self.send_now_playing_card(track, message_to_edit=message_to_edit)

    async def _handle_track_finish(self) -> None:
        """Fired automatically when a track finishes naturally."""
        async with self._lock:
            # 1. Loop Track
            if self.loop_mode == "track" and self.current:
                await self.play_track(self.current)
                return

            # 2. Loop Queue (push finished track to end)
            if self.loop_mode == "queue" and self.current:
                self.queue.append(self.current)

            # 3. Next Track in Queue
            if self.queue:
                next_track = self.queue.pop(0)
                await self.play_track(next_track)
                return

            # 4. Smart Autoplay Radio
            if self.smart_autoplay and self.current:
                next_track = await NativeSmartAutoplay.get_next_track(
                    current_track=self.current,
                    played_history=self.played_history,
                    consecutive_same_artist=self.consecutive_same_artist,
                )
                if next_track:
                    await self.play_track(next_track)
                    return

            # 5. Queue Ended
            self.current = None

    async def skip(self) -> None:
        """Skip current track."""
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()

    def pause(self) -> bool:
        """Pause current playback."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            return True
        return False

    def resume(self) -> bool:
        """Resume paused playback."""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            return True
        return False

    async def stop(self) -> None:
        """Clear queue and disconnect."""
        self.queue.clear()
        self.current = None
        if self.voice_client:
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()
            try:
                await self.voice_client.disconnect(force=True)
            except Exception:
                pass
            self.voice_client = None

    def build_now_playing_container(self, track: Track) -> KyroContainer:
        """Build exact signature card matching user reference."""
        e_reg = self.bot.custom_emojis
        music_icon = e_reg.get("Music_Playing", e_reg.get("music_playing", e_reg.get("music_music", "")))
        play_prefix = f"{music_icon} " if music_icon else ""

        short_artist_name = shorten_artist(track.author)
        channel_mention = f"<#{self.voice_client.channel.id}>" if (self.voice_client and self.voice_client.channel) else "#Hangout"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{play_prefix}Now Playing**\n"
                f"**Title:** [{track.title}]({track.url})\n"
                f"**Artist:** `{short_artist_name}`\n"
                f"**Duration:** `{track.formatted_duration}`"
            ),
            accessory={"type": 11, "media": {"url": track.thumbnail}} if track.thumbnail else None,
        )

        container.add_text(
            f"• **Channel:** {channel_mention}\n"
            f"• **Requested By:** {track.requester}\n\n"
            f"-# Kyro Music Engine"
        )

        return container

    async def send_now_playing_card(self, track: Track, message_to_edit: Optional[discord.Message] = None) -> None:
        """Send Now Playing Card directly or edit searching message to prevent duplicate embeds."""
        if not self.home_channel:
            return

        from src.cogs.music._views import MusicControlView

        container = self.build_now_playing_container(track)
        view = MusicControlView(self.bot, self, self.guild.id)

        # If we have an existing search message to edit into Now Playing
        if message_to_edit and isinstance(message_to_edit, discord.Message):
            try:
                await message_to_edit.edit(embed=container.to_embed(), view=view)
                self.now_playing_message = message_to_edit
                return
            except Exception:
                pass

        try:
            self.now_playing_message = await send_container_response(
                self.home_channel,
                container,
                view=view,
            )
        except Exception as e:
            logger.debug(f"Now playing card send notice: {e}")
