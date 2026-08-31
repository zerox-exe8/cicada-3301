"""
Cicada 3301 Discord Bot - Music Types & Streaming Constants
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


# Rock-Solid High-Quality FFmpeg Streaming Options
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 320k'
}

# 100% Authentic YouTube & YouTube Music Official Studio Extractor Flags
YDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios']
        }
    }
}
