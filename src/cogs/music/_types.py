"""
Cicada 3301 Discord Bot - Music Types & Streaming Constants
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
import discord


@dataclass
class TrackItem:
    title: str
    author: str
    duration: int
    url: str
    stream_url: str
    thumbnail: str
    requester: str


# Ultra-Armor Rock-Solid FFmpeg Streaming Options with Studio Dynamics Compressor & Peak Limiter
FFMPEG_OPTIONS = {
    "before_options": (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_at_eof 1 "
        "-reconnect_delay_max 5 "
        "-probesize 16M "
        "-analyzeduration 0 "
        "-thread_queue_size 8192"
    ),
    "options": (
        "-vn "
        "-b:a 320k "
        "-ar 48000 "
        "-ac 2 "
        "-af acompressor=threshold=-14dB:ratio=2.0:attack=5:release=50,alimiter=limit=-1.0dB:attack=5:release=50:level=disabled"
    ),
}

# YouTube Studio Extractor Options
YDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "source_address": "0.0.0.0",
    "socket_timeout": 10,
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "ios", "web", "mweb"]
        }
    },
}


class BufferedAudioSource(discord.AudioSource):
    """
    High-Performance Thread-Safe Jitter-Proof Audio Buffer.
    Pre-buffers 20ms audio frames (approx 3-5 seconds ahead) in RAM so Discord voice
    never starves of frames due to transient network lag, packet drops, or CDN delay.
    """

    def __init__(self, original: discord.AudioSource, buffer_size: int = 200) -> None:
        self.original = original
        self.buffer: queue.Queue[bytes] = queue.Queue(maxsize=buffer_size)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="AudioPrefetchWorker")
        self._thread.start()

    def _worker(self) -> None:
        while not self._stop_event.is_set():
            try:
                data = self.original.read()
                if not data:
                    self.buffer.put(b"")  # EOF marker
                    break
                while not self._stop_event.is_set():
                    try:
                        self.buffer.put(data, timeout=0.5)
                        break
                    except queue.Full:
                        time.sleep(0.01)
            except Exception:
                break

    def read(self) -> bytes:
        try:
            return self.buffer.get_nowait()
        except queue.Empty:
            # Buffer briefly empty under extreme lag: output silence frame (prevents discord.py crackle)
            return b"\x00" * 3840

    def cleanup(self) -> None:
        self._stop_event.set()
        try:
            self.original.cleanup()
        except Exception:
            pass
