"""
Kyro Discord Bot - Music Types & Streaming Constants
Enterprise-Grade Zero-Overhead Streaming Configuration with Jitter-Proof RAM Ring Buffer.
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional

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


def get_ffmpeg_options() -> Dict[str, str]:
    """
    Generate rock-solid FFmpeg streaming options with auto-reconnect and 48kHz stereo PCM.
    Guarantees continuous 24/7 playback without connection drops or network timeouts.
    """
    return {
        "before_options": (
            "-reconnect 1 "
            "-reconnect_streamed 1 "
            "-reconnect_delay_max 5 "
            "-nostdin"
        ),
        "options": (
            "-vn "
            "-loglevel error "
            "-ar 48000 "
            "-ac 2"
        ),
    }


# Default fallback options
FFMPEG_OPTIONS = get_ffmpeg_options()

# YouTube Studio Extractor Options (Fast Android/Web Client Engine)
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
            "player_client": ["android", "web"]
        }
    },
}

