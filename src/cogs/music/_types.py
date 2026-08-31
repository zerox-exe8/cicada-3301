"""
Cicada 3301 Discord Bot - Ultra-Armor Music Types & Streaming Constants
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TrackItem:
    title: str
    author: str
    duration: int
    url: str
    stream_url: str
    thumbnail: str
    requester: str


# Ultra-Armor Rock-Solid FFmpeg Streaming Options (Zero Buffering, 32MB Buffer, 48kHz Stereo)
FFMPEG_OPTIONS = {
    'before_options': (
        '-reconnect 1 '
        '-reconnect_at_eof 1 '
        '-reconnect_streamed 1 '
        '-reconnect_delay_max 2 '
        '-probesize 32M '
        '-analyzeduration 0 '
        '-thread_queue_size 8192'
    ),
    'options': (
        '-vn '
        '-b:a 320k '
        '-ar 48000 '
        '-ac 2 '
        '-bufsize 32768k '
        '-max_muxing_queue_size 8192 '
        '-fflags +nobuffer+fastseek'
    )
}

# 100% Authentic Multi-Client YouTube Studio Extractor Flags
YDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'source_address': '0.0.0.0',
    'socket_timeout': 8,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios', 'web']
        }
    }
}
