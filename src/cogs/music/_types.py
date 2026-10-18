from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


LoopMode = Literal["off", "track", "queue"]
TrackSourceType = Literal["youtube", "youtube_music", "jiosaavn", "spotify", "soundcloud"]


@dataclass
class TrackItem:
    """Lightweight track descriptor for queue items."""
    title: str
    author: str
    duration: int
    url: str
    stream_url: str = ""
    thumbnail: Optional[str] = None
    requester: str = "DJ / AutoPlay"
