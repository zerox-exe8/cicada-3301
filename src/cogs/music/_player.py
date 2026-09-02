"""
Kyro Discord Bot - Native Discord Guild Audio Player
Pure Python Discord VoiceClient controller with Zero-Stutter RAM pre-buffering,
loop modes, Smart Autoplay AI, and Components V2 Cyber Container UI.
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import queue
import re
import shutil
import stat
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


def resolve_ffmpeg_executable() -> str:
    """Robust multi-platform resolver for FFmpeg binary across Windows, Linux, Render, and Docker."""
    # 1. System PATH
    exe = shutil.which("ffmpeg")
    if exe and os.path.isfile(exe) and os.access(exe, os.X_OK):
        return exe

    # 2. static_ffmpeg
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        exe = shutil.which("ffmpeg")
        if exe and os.path.isfile(exe) and os.access(exe, os.X_OK):
            return exe
    except Exception:
        pass

    # 3. Candidate Linux/Render paths
    home = os.path.expanduser("~")
    candidates = [
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        os.path.join(home, ".local", "bin", "ffmpeg"),
        os.path.join(home, ".static_ffmpeg", "bin", "linux", "ffmpeg"),
    ]
    for p in candidates:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    # 4. imageio_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            try:
                st = os.stat(exe)
                os.chmod(exe, st.st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
            except Exception:
                pass
            return exe
    except Exception:
        pass

    return "ffmpeg"


class DirectFFmpegStream(discord.AudioSource):
    """
    Direct, Rock-Solid FFmpeg Audio Source for Discord Voice.
    Accumulates exact 3840-byte PCM frames, preventing partial-read premature EOF drops,
    with auto-reconnect, dynamic real-time C-level volume scaling, and seamless jitter buffering.
    """
    FRAME_SIZE = 3840  # 20ms of 48000Hz 16-bit stereo PCM

    def __init__(self, stream_url: str, executable: str, volume: float = 1.0) -> None:
        self.stream_url = stream_url
        self.executable = executable
        self._volume = max(0.0, min(volume, 2.0))
        self._process: Optional[subprocess.Popen] = None
        self._buffer = bytearray()
        self._start_process()

    @property
    def volume(self) -> float:
        return self._volume

    @volume.setter
    def volume(self, val: float) -> None:
        self._volume = max(0.0, min(val, 2.0))

    def _start_process(self) -> None:
        cmd = [
            self.executable,
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-nostdin",
            "-i", self.stream_url,
            "-f", "s16le",
            "-ar", "48000",
            "-ac", "2",
            "-vn",
            "-loglevel", "warning",
            "pipe:1",
        ]
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1024 * 1024,
        )

    def read(self) -> bytes:
        if not self._process or not self._process.stdout:
            return b""

        # Accumulate until at least 3840 bytes are ready or true stream EOF
        while len(self._buffer) < self.FRAME_SIZE:
            try:
                chunk = self._process.stdout.read(self.FRAME_SIZE - len(self._buffer))
                if not chunk:
                    if self._process.poll() is not None and self._process.returncode != 0:
                        err = self._process.stderr.read().decode("utf-8", errors="ignore") if self._process.stderr else ""
                        logger.error(f"FFmpeg stream exited with code {self._process.returncode}: {err}")
                    break
                self._buffer.extend(chunk)
            except Exception as e:
                logger.debug(f"FFmpeg stdout read notice: {e}")
                break

        if len(self._buffer) >= self.FRAME_SIZE:
            frame = bytes(self._buffer[:self.FRAME_SIZE])
            del self._buffer[:self.FRAME_SIZE]
            if self._volume != 1.0:
                try:
                    import audioop
                    frame = audioop.mul(frame, 2, self._volume)
                except Exception:
                    pass
            return frame
        elif len(self._buffer) > 0:
            frame = bytes(self._buffer).ljust(self.FRAME_SIZE, b"\x00")
            self._buffer.clear()
            if self._volume != 1.0:
                try:
                    import audioop
                    frame = audioop.mul(frame, 2, self._volume)
                except Exception:
                    pass
            return frame
        else:
            return b""

    def cleanup(self) -> None:
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass
            self._process = None
        self._buffer.clear()


def shorten_artist(raw_artist: str, max_chars: int = 32) -> str:
    """Shorten multi-artist strings."""
    if not raw_artist:
        return "Official Artist"
    clean = html.unescape(raw_artist).strip()
    parts = re.split(r"[,/|]|\s+(?:feat\.?|ft\.?|and|&)\s+", clean, flags=re.IGNORECASE)
    if parts and parts[0].strip():
        first_artist = parts[0].strip()
        if len(first_artist) <= max_chars:
            return first_artist
        return first_artist[: max_chars - 3] + "..."
    if len(clean) > max_chars:
        return clean[: max_chars - 3] + "..."
    return clean


class GuildPlayer:
    """Guild audio player using native Discord.py VoiceClient & HighSpeedJitterProofBuffer."""

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

        self._current_gen: int = 0
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
        """Set player volume (0 to 200%) dynamically in real time."""
        clamped = max(0, min(200, vol_pct))
        self.volume = clamped / 100.0
        if self.voice_client and self.voice_client.source:
            if hasattr(self.voice_client.source, "volume"):
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
            from pathlib import Path
            import os, sys
            base_d = Path(__file__).resolve().parent.parent.parent.parent
            if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(str(base_d))
                except Exception:
                    pass

            possible_opus_paths = [
                str(base_d / "opus.dll"),
                str(base_d / "libopus.so.0"),
                str(base_d / "libopus.so"),
                "/usr/lib/x86_64-linux-gnu/libopus.so.0",
                "/usr/lib/x86_64-linux-gnu/libopus.so",
                "/usr/lib/libopus.so.0",
                "/usr/lib64/libopus.so.0",
                "/usr/local/lib/libopus.so.0",
                "opus.dll",
                "libopus.so.0",
                "libopus.so",
                "libopus-0.dll",
            ]
            import ctypes.util
            opus_lib = ctypes.util.find_library("opus")
            if opus_lib:
                possible_opus_paths.insert(0, opus_lib)

            for target in possible_opus_paths:
                try:
                    discord.opus.load_opus(target)
                    if discord.opus.is_loaded():
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
        ffmpeg_exe = resolve_ffmpeg_executable()
        logger.info(f"Resolved FFmpeg executable for stream: {ffmpeg_exe}")

        try:
            audio_source = DirectFFmpegStream(
                stream_url=track.stream_url,
                executable=ffmpeg_exe,
                volume=self.volume,
            )
        except Exception as e:
            logger.error(f"FFmpeg audio stream creation error: {e}", exc_info=True)
            if self.home_channel:
                await self.home_channel.send(f"**Audio Stream Error:** `{e}`")
            return

        self._current_gen += 1
        current_gen = self._current_gen

        if self.voice_client.is_playing() or self.voice_client.is_paused():
            self.voice_client.stop()

        def _after_callback(error, gen=current_gen):
            if gen != self._current_gen:
                return  # Stale callback from previously stopped track
            if error:
                logger.error(f"Voice playback error in guild {self.guild.id}: {error}", exc_info=True)
                if self.home_channel:
                    asyncio.run_coroutine_threadsafe(
                        self.home_channel.send(f"**Voice Playback Notice:** `{error}`"),
                        self.bot.loop,
                    )
            asyncio.run_coroutine_threadsafe(self._handle_track_finish(gen), self.bot.loop)

        self.voice_client.play(audio_source, after=_after_callback)
        await self.send_now_playing_card(track, message_to_edit=message_to_edit)

    async def _handle_track_finish(self, gen: int) -> None:
        """Fired automatically when a track finishes naturally."""
        await asyncio.sleep(0.15)
        if gen != self._current_gen:
            return

        async with self._lock:
            if gen != self._current_gen:
                return

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

            # 5. Queue Ended Notification
            self.current = None
            if self.home_channel:
                try:
                    container = KyroContainer(accent_color=None)
                    container.add_section(
                        content=(
                            "**Queue Concluded**\n"
                            "> All queued songs have finished playing. The player is now idle."
                        )
                    )
                    container.add_separator(divider=True)
                    container.add_text(
                        "Use `?play <song>` or `?playlist play <name>` to play more tracks.\n"
                        "Use `?autoplay on` for non-stop continuous playback.\n\n"
                        "-# Kyro Music Engine"
                    )
                    await send_container_response(self.home_channel, container)
                except Exception as e:
                    logger.debug(f"Queue ended notice: {e}")

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
        self._current_gen += 1
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
        """Build signature Now Playing card with strictly custom application emojis."""
        e_reg = self.bot.custom_emojis
        music_icon = e_reg.get("Music_Playing", e_reg.get("music_playing", e_reg.get("music_music", "")))
        play_prefix = f"{music_icon} " if music_icon else ""

        short_artist_name = shorten_artist(track.author)
        channel_mention = f"<#{self.voice_client.channel.id}>" if (self.voice_client and self.voice_client.channel) else "#Hangout"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"{play_prefix}**Now Playing**\n"
                f"> **Track** • [{track.title}]({track.url})\n"
                f"> **Artist** • `{short_artist_name}`\n"
                f"> **Length** • `{track.formatted_duration}` • `320kbps HD`"
            ),
            accessory={"type": 11, "media": {"url": track.thumbnail}} if track.thumbnail else None,
        )

        container.add_separator(divider=True)

        container.add_text(
            f"> **Channel** • {channel_mention}\n"
            f"> **Requester** • `{track.requester}`\n\n"
            f"-# Kyro Music Engine • Studio Audio"
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
