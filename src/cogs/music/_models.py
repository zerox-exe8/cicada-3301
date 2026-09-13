"""
Kyro Discord Bot - Native Audio Track Model
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Track:
    """Represents a playable audio track."""
    title: str
    author: str
    url: str
    stream_url: str
    duration: int  # in seconds
    thumbnail: Optional[str] = None
    requester: str = "DJ / AutoPlay"
    requester_id: Optional[int] = None
    is_autoplay: bool = False

    @property
    def uri(self) -> str:
        return self.url

    @property
    def formatted_duration(self) -> str:
        if self.duration <= 0:
            return "Live Stream"
        m = self.duration // 60
        s = self.duration % 60
        return f"{m:02d}:{s:02d}"


@dataclass
class PlaylistTrackItem:
    """Represents an item in an external playlist before stream resolution."""
    title: str
    author: str
    query: str
    duration: int = 0
    url: Optional[str] = None


@dataclass
class PlaylistResult:
    """Represents a loaded external playlist collection."""
    title: str
    author: str
    url: str
    tracks: list[PlaylistTrackItem]
    thumbnail: Optional[str] = None
    requester: str = "DJ / AutoPlay"
    requester_id: Optional[int] = None

    @property
    def track_count(self) -> int:
        return len(self.tracks)
