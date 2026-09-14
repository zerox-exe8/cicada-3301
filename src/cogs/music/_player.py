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
from src.cogs.music._extractor import NativeExtractor
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

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
    High-Performance, Jitter-Buffered FFmpeg Audio Source for Discord Voice.
    Uses a dedicated daemon background worker to decouple network pipe I/O
    from Discord's real-time 20ms audio transmission loop.
    Eliminates packet rushing, stuttering, cutting, and premature EOF.
    """
    FRAME_SIZE = 3840  # 20ms of 48000Hz 16-bit stereo PCM
    BUFFER_SIZE = 150  # ~3 seconds of pre-buffered RAM audio frames

    def __init__(self, stream_url: str, executable: str, volume: float = 1.0) -> None:
        self.stream_url = stream_url
        self.executable = executable
        self._volume = max(0.0, min(volume, 2.0))
        self._process: Optional[subprocess.Popen] = None
        self._queue: queue.Queue[Optional[bytes]] = queue.Queue(maxsize=self.BUFFER_SIZE)
        self._stopped = threading.Event()
        self._reader_thread: Optional[threading.Thread] = None
        self._prebuffered = False
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
            "-reconnect_at_eof", "1",
            "-reconnect_delay_max", "5",
            "-nostdin",
            "-i", self.stream_url,
            "-vn",
            "-af", "aresample=48000",
            "-f", "s16le",
            "-ar", "48000",
            "-ac", "2",
            "-loglevel", "warning",
            "pipe:1",
        ]
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=512 * 1024,
        )
        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name="FFmpeg-Audio-Reader",
        )
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        """Continuously pull raw PCM bytes from FFmpeg pipe and enqueue exact frames."""
        buf = bytearray()
        stdout = self._process.stdout if self._process else None
        if not stdout:
            self._queue.put(None)
            return

        while not self._stopped.is_set():
            try:
                chunk = stdout.read(self.FRAME_SIZE)
                if not chunk:
                    # True EOF from FFmpeg
                    break
                buf.extend(chunk)
                while len(buf) >= self.FRAME_SIZE and not self._stopped.is_set():
                    frame = bytes(buf[:self.FRAME_SIZE])
                    del buf[:self.FRAME_SIZE]
                    # Block with timeout so we can exit promptly if stopped
                    while not self._stopped.is_set():
                        try:
                            self._queue.put(frame, timeout=0.05)
                            break
                        except queue.Full:
                            continue
            except Exception as e:
                logger.debug(f"FFmpeg reader pipe notice: {e}")
                break

        if self._process:
            self._process.poll()
            if self._process.returncode not in (0, None):
                logger.warning(f"FFmpeg reader process exited with code {self._process.returncode}")

        # Flush remaining bytes padded to frame size
        if len(buf) > 0 and not self._stopped.is_set():
            padded = bytes(buf).ljust(self.FRAME_SIZE, b"\x00")
            try:
                self._queue.put(padded, timeout=0.5)
            except Exception:
                pass

        # Sentinel indicating end of stream
        try:
            self._queue.put(None, timeout=0.5)
        except Exception:
            pass

    def read(self) -> bytes:
        if self._stopped.is_set():
            return b""

        try:
            frame = self._queue.get_nowait()
        except queue.Empty:
            # If process is still running but network temporarily buffering,
            # return silent frame immediately so Discord's 20ms voice pacing is never stalled
            if self._process and self._process.poll() is None:
                return b"\x00" * self.FRAME_SIZE
            return b""

        if frame is None:
            # Sentinel reached: End of song
            return b""

        if self._volume != 1.0:
            try:
                import audioop
                frame = audioop.mul(frame, 2, self._volume)
            except Exception:
                pass

        return frame

    def cleanup(self) -> None:
        self._stopped.set()
        if self._process:
            try:
                self._process.kill()
            except Exception:
                pass
            self._process = None
        # Drain queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Exception:
                break


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


def render_progress_bar(elapsed_sec: float, total_sec: float, length: int = 12) -> str:
    """Render high-contrast dynamic studio progress bar."""
    if total_sec <= 0:
        return "`Live Stream` 🔴"
    clamped = max(0.0, min(elapsed_sec, total_sec))
    progress = clamped / total_sec
    fill_count = int(progress * length)
    fill_count = max(0, min(fill_count, length))
    bar = "━" * fill_count + "🔘" + "─" * (length - fill_count)
    cur_m, cur_s = divmod(int(clamped), 60)
    tot_m, tot_s = divmod(int(total_sec), 60)
    return f"`{cur_m:02d}:{cur_s:02d}` {bar} `{tot_m:02d}:{tot_s:02d}`"


class GuildPlayer:
    """Guild audio player using native Discord.py VoiceClient & Zero-Stutter Dual-Buffer RAM Pipeline."""

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
        self.is_247: bool = False
        
        self.played_history: Set[str] = set()
        self.consecutive_same_artist: int = 0
        self.last_artist: str = ""
        self.consecutive_failures: int = 0
        self._track_started_at: float = 0.0

        # Zero-Stutter Dual-Buffer RAM Pipeline
        self._current_stream: Optional[DirectFFmpegStream] = None
        self._next_stream: Optional[DirectFFmpegStream] = None
        self._next_track: Optional[Track] = None
        self._prebuffer_task: Optional[asyncio.Task] = None

        # Live Real-Time Dynamic Progress Controller
        self._progress_task: Optional[asyncio.Task] = None
        self._last_controller_edit: float = 0.0
        self._track_paused_duration: float = 0.0
        self._pause_timestamp: float = 0.0

        # AI Voice Recognition & Wake-Word Listener
        self.voice_listening: bool = False
        self._voice_sink: Any = None

        self._current_gen: int = 0
        self._lock = asyncio.Lock()

    @property
    def elapsed_time(self) -> float:
        """Calculate exact playback elapsed seconds taking pauses into account."""
        if self._track_started_at <= 0:
            return 0.0
        if self.is_paused:
            return max(0.0, self._pause_timestamp - self._track_started_at - self._track_paused_duration)
        return max(0.0, time.time() - self._track_started_at - self._track_paused_duration)

    @property
    def is_playing(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_playing())

    @property
    def is_paused(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_paused())

    @property
    def is_connected(self) -> bool:
        return bool(self.voice_client and self.voice_client.is_connected())

    @property
    def voice_channel(self) -> Optional[discord.VoiceChannel]:
        if self.voice_client and self.voice_client.channel:
            return self.voice_client.channel
        return None

    def set_loop_mode(self, mode: str) -> str:
        """Set loop mode: 'off', 'track' (single song), 'queue' (all songs)."""
        m = mode.lower().strip()
        if m in ("track", "song", "1"):
            self.loop_mode = "track"
        elif m in ("queue", "all"):
            self.loop_mode = "queue"
        else:
            self.loop_mode = "off"
        # Reschedule prebuffer when loop changes
        self._schedule_prebuffer()
        return self.loop_mode

    def set_volume(self, vol_pct: int) -> int:
        """Set player volume (0 to 200%) dynamically in real time."""
        clamped = max(0, min(200, vol_pct))
        self.volume = clamped / 100.0
        if self.voice_client and self.voice_client.source:
            if hasattr(self.voice_client.source, "volume"):
                self.voice_client.source.volume = self.volume
        if self._next_stream and hasattr(self._next_stream, "volume"):
            self._next_stream.volume = self.volume
        return clamped

    async def connect_voice(self, channel: discord.VoiceChannel) -> None:
        """Connect or move to voice channel safely with VoiceRecv support."""
        vc = self.guild.voice_client
        if vc and vc.is_connected():
            self.voice_client = vc
            if self.voice_client.channel != channel:
                await self.voice_client.move_to(channel)
            return

        cls = discord.VoiceClient
        try:
            import discord.ext.voice_recv as voice_recv
            cls = voice_recv.VoiceRecvClient
        except Exception:
            pass

        self.voice_client = await channel.connect(cls=cls, self_deaf=False, timeout=20.0, reconnect=True)

    async def _handle_voice_command(self, user: discord.Member, action: str, query: str) -> None:
        """Handle incoming recognized voice command from a speaking user."""
        logger.info(f"Executing Voice Action '{action}' with query '{query}' requested by {user}")
        if not self.home_channel:
            return

        if action == "play" and query:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**AI Voice Command Detected**\n"
                    f"> {user.mention} asked to play: `{query}`"
                )
            )
            await send_container_response(self.home_channel, container)

            resolved = await NativeExtractor.extract(query, requester=user.display_name)
            if resolved:
                if not self.is_playing and not self.is_paused:
                    await self.play_track(resolved)
                else:
                    self.queue.append(resolved)
                    self._schedule_prebuffer()
                    c = KyroContainer(accent_color=None)
                    c.add_section(
                        content=(
                            "**Track Queued via Voice**\n"
                            f"> Enqueued [{resolved.title}]({resolved.url}) at position `#{len(self.queue)}`."
                        )
                    )
                    await send_container_response(self.home_channel, c)

        elif action == "pause":
            if self.pause():
                await self.update_controller_message(force=True)
                c = KyroContainer(accent_color=None)
                c.add_text(f"**Playback paused via voice command** ({user.mention}).")
                await send_container_response(self.home_channel, c)

        elif action == "resume":
            if self.resume():
                await self.update_controller_message(force=True)
                c = KyroContainer(accent_color=None)
                c.add_text(f"**Playback resumed via voice command** ({user.mention}).")
                await send_container_response(self.home_channel, c)

        elif action == "skip":
            c = KyroContainer(accent_color=None)
            c.add_text(f"**Skipping track via voice command** ({user.mention})...")
            await send_container_response(self.home_channel, c)
            await self.skip()

        elif action == "stop":
            c = KyroContainer(accent_color=None)
            c.add_text(f"**Player stopped via voice command** ({user.mention}).")
            await send_container_response(self.home_channel, c)
            await self.stop()

        elif action == "volume" and query.isdigit():
            v = int(query)
            new_v = self.set_volume(v)
            await self.update_controller_message(force=True)
            c = KyroContainer(accent_color=None)
            c.add_text(f"**Volume set to `{new_v}%` via voice command** ({user.mention}).")
            await send_container_response(self.home_channel, c)

    def start_voice_listening(self) -> bool:
        """Attach voice sink to listen for wake-word voice commands."""
        if not self.voice_client or not hasattr(self.voice_client, "listen"):
            return False

        from src.cogs.music._voice_listener import VoiceCommandSink, HAS_VOICE_RECV
        if not HAS_VOICE_RECV:
            return False

        if self.voice_listening:
            return True

        try:
            self._voice_sink = VoiceCommandSink(self, self._handle_voice_command)
            self.voice_client.listen(self._voice_sink)
            self.voice_listening = True
            logger.info(f"AI Voice Commander: Started listening in guild {self.guild.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to start voice listening: {e}", exc_info=True)
            return False

    def stop_voice_listening(self) -> None:
        """Stop voice listening and clean up sink."""
        if self.voice_client and hasattr(self.voice_client, "stop_listening"):
            try:
                self.voice_client.stop_listening()
            except Exception:
                pass
        if self._voice_sink:
            try:
                self._voice_sink.cleanup()
            except Exception:
                pass
            self._voice_sink = None
        self.voice_listening = False
        logger.info(f"AI Voice Commander: Stopped listening in guild {self.guild.id}")

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

        # Resolve deferred stream URL on-demand (e.g. for external playlist queue items)
        if not track.stream_url:
            lookup_query = track.query or f"{track.title} {track.author}".strip()
            resolved = await NativeExtractor.extract(lookup_query, requester=track.requester)
            if resolved and resolved.stream_url:
                track.stream_url = resolved.stream_url
                track.duration = resolved.duration or track.duration
                if resolved.thumbnail:
                    track.thumbnail = resolved.thumbnail
            else:
                logger.warning(f"Could not resolve stream for track: {track.title}")
                if self.queue:
                    next_t = self.queue.pop(0)
                    await self.play_track(next_t, message_to_edit=message_to_edit)
                    return
                else:
                    return

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

        # Zero-Stutter Gapless Dual-Buffer Transition Check
        audio_source = None
        if (
            self._next_stream
            and self._next_track
            and (self._next_track == track or getattr(self._next_track, "url", None) == track.url)
            and not self._next_stream._stopped.is_set()
        ):
            audio_source = self._next_stream
            self._next_stream = None
            self._next_track = None
            logger.info(f"Zero-Stutter Gapless Engine: INSTANT 0ms playback transition for '{track.title}' from RAM buffer!")
        else:
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

        self._current_stream = audio_source
        self._current_gen += 1
        current_gen = self._current_gen
        self._track_started_at = time.time()
        self._track_paused_duration = 0.0
        self._pause_timestamp = 0.0

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

        # Immediately kick off background pre-buffering into RAM for the upcoming track
        self._schedule_prebuffer()
        self._start_progress_loop()

    async def _handle_track_finish(self, gen: int) -> None:
        """Fired automatically when a track finishes naturally."""
        await asyncio.sleep(0.1)
        if gen != self._current_gen:
            return

        async with self._lock:
            if gen != self._current_gen:
                return

            elapsed = (time.time() - self._track_started_at) if self._track_started_at > 0 else 10.0
            if elapsed < 2.0:
                self.consecutive_failures += 1
            else:
                self.consecutive_failures = 0

            if self.consecutive_failures >= 3:
                logger.warning(f"Aborting playback in guild {self.guild.id}: 3 consecutive fast failures.")
                self.current = None
                self.consecutive_failures = 0
                if self._progress_task and not self._progress_task.done():
                    self._progress_task.cancel()
                if self.home_channel:
                    try:
                        c = KyroContainer(accent_color=None)
                        c.add_section(
                            content=(
                                "**Playback Paused**\n"
                                "> Multiple audio streams failed to play consecutively.\n"
                                "> Playback has been paused to protect your queue."
                            )
                        )
                        c.add_separator(divider=True)
                        c.add_text("-# Kyro Music Engine")
                        await send_container_response(self.home_channel, c)
                    except Exception:
                        pass
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
            if self._progress_task and not self._progress_task.done():
                self._progress_task.cancel()

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
        """Skip current track and trigger instant gapless transition."""
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()

    def _schedule_prebuffer(self) -> None:
        """Asynchronously pre-resolve and pre-buffer upcoming track into RAM ahead of time."""
        if self._prebuffer_task and not self._prebuffer_task.done():
            self._prebuffer_task.cancel()
        self._prebuffer_task = asyncio.create_task(self._prebuffer_worker())

    async def _prebuffer_worker(self) -> None:
        """Background worker that decodes upcoming track into a standby RAM buffer."""
        try:
            candidate: Optional[Track] = None
            if self.loop_mode == "track" and self.current:
                candidate = self.current
            elif self.queue:
                candidate = self.queue[0]
            elif self.loop_mode == "queue" and self.current:
                candidate = self.current
            elif self.smart_autoplay and self.current:
                candidate = await NativeSmartAutoplay.get_next_track(
                    current_track=self.current,
                    played_history=self.played_history,
                    consecutive_same_artist=self.consecutive_same_artist,
                )

            if not candidate:
                return

            if not candidate.stream_url:
                lookup_query = candidate.query or f"{candidate.title} {candidate.author}".strip()
                resolved = await NativeExtractor.extract(lookup_query, requester=candidate.requester)
                if resolved and resolved.stream_url:
                    candidate.stream_url = resolved.stream_url
                    candidate.duration = resolved.duration or candidate.duration
                    if resolved.thumbnail:
                        candidate.thumbnail = resolved.thumbnail

            if not candidate.stream_url:
                return

            if self._next_track == candidate and self._next_stream and not self._next_stream._stopped.is_set():
                return

            if self._next_stream:
                try:
                    self._next_stream.cleanup()
                except Exception:
                    pass
                self._next_stream = None

            ffmpeg_exe = resolve_ffmpeg_executable()
            standby_stream = DirectFFmpegStream(
                stream_url=candidate.stream_url,
                executable=ffmpeg_exe,
                volume=self.volume,
            )
            self._next_stream = standby_stream
            self._next_track = candidate
            logger.info(f"Zero-Stutter Gapless Engine: Pre-buffered next track '{candidate.title}' in RAM.")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Pre-buffer worker notice: {e}")

    def pause(self) -> bool:
        """Pause current playback."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            self._pause_timestamp = time.time()
            return True
        return False

    def resume(self) -> bool:
        """Resume paused playback."""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            if self._pause_timestamp > 0:
                self._track_paused_duration += (time.time() - self._pause_timestamp)
                self._pause_timestamp = 0.0
            return True
        return False

    async def stop(self) -> None:
        """Clear queue and disconnect cleanly."""
        self._current_gen += 1
        if self._prebuffer_task and not self._prebuffer_task.done():
            self._prebuffer_task.cancel()
        if self._progress_task and not self._progress_task.done():
            self._progress_task.cancel()

        if self._next_stream:
            try:
                self._next_stream.cleanup()
            except Exception:
                pass
            self._next_stream = None
            self._next_track = None

        if self._current_stream:
            try:
                self._current_stream.cleanup()
            except Exception:
                pass
            self._current_stream = None

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

    def build_now_playing_container(self, track: Track, elapsed: Optional[float] = None) -> KyroContainer:
        """Build signature Now Playing card with live dynamic progress bar & studio metrics."""
        e_reg = self.bot.custom_emojis
        music_icon = e_reg.get("Music_Playing", e_reg.get("music_playing", e_reg.get("music_music", "")))
        play_prefix = f"{music_icon} " if music_icon else ""

        short_artist_name = shorten_artist(track.author)
        channel_mention = f"<#{self.voice_client.channel.id}>" if (self.voice_client and self.voice_client.channel) else "#Hangout"

        if elapsed is None:
            elapsed = self.elapsed_time

        progress_str = render_progress_bar(elapsed, track.duration)
        vol_pct = int(self.volume * 100)
        loop_str = self.loop_mode.capitalize()

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
            f"> **Timeline** • {progress_str}\n"
            f"> **Volume** • `{vol_pct}%` • **Loop** • `{loop_str}` • **Engine** • `Gapless RAM`\n"
            f"> **Channel** • {channel_mention} • **Requester** • `{track.requester}`\n\n"
            f"-# Kyro Music Engine • Live Studio Controller"
        )

        return container

    async def update_controller_message(self, force: bool = False) -> None:
        """Edit the Now Playing controller card in-place without cluttering channel."""
        if not self.now_playing_message or not self.current:
            return

        now = time.time()
        # Rate-limit automatic dynamic progress updates to avoid Discord 429
        if not force and (now - self._last_controller_edit) < 4.5:
            return

        try:
            from src.cogs.music._views import MusicControlView
            container = self.build_now_playing_container(self.current)
            view = MusicControlView(self.bot, self, self.guild.id)
            await edit_container_response(self.now_playing_message, container, view=view)
            self._last_controller_edit = now
        except discord.NotFound:
            self.now_playing_message = None
        except Exception as e:
            logger.debug(f"Controller message edit notice: {e}")

    def _start_progress_loop(self) -> None:
        """Start the live real-time progress bar updater."""
        if self._progress_task and not self._progress_task.done():
            self._progress_task.cancel()
        self._progress_task = asyncio.create_task(self._progress_updater())

    async def _progress_updater(self) -> None:
        """Periodically update the live progress bar in-place every 5 seconds."""
        try:
            while self.is_playing or self.is_paused:
                await asyncio.sleep(5.0)
                if not self.is_paused and self.current and self.now_playing_message:
                    await self.update_controller_message(force=False)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Progress updater notice: {e}")

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
                await edit_container_response(message_to_edit, container, view=view)
                self.now_playing_message = message_to_edit
                self._start_progress_loop()
                return
            except Exception:
                pass

        try:
            self.now_playing_message = await send_container_response(
                self.home_channel,
                container,
                view=view,
            )
            self._start_progress_loop()
        except Exception as e:
            logger.debug(f"Now playing card send notice: {e}")
