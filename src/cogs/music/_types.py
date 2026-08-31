"""
Cicada 3301 Discord Bot - Music Types & Streaming Constants
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TrackItem:
    title: str
    author: str
    duration: int
    url: str
    stream_url: str
    thumbnail: str
    requester: str


# Ultra-Armor Stream Buffering Options (Unbreakable Continuous Streaming)
FFMPEG_OPTIONS = {
    'before_options': (
        '-reconnect 1 '
        '-reconnect_at_eof 1 '
        '-reconnect_streamed 1 '
        '-reconnect_delay_max 2 '
        '-probesize 64M '
        '-analyzeduration 0 '
        '-thread_queue_size 4096'
    ),
    'options': (
        '-vn '
        '-b:a 320k '
        '-bufsize 16384k '
        '-max_muxing_queue_size 4096 '
        '-fflags +nobuffer+fastseek'
    )
}

# Fast Android/iOS YouTube Client Flags
YDL_OPTS = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'source_address': '0.0.0.0',
    'socket_timeout': 6,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios'],
            'skip': ['dash', 'hls', 'translated_subs']
        }
    }
}
