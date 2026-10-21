from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Track:
    """Represents a playable audio track."""
    title: str
    author: str
    url: str
    stream_url: str = ""
    duration: int = 0  # in seconds
    thumbnail: Optional[str] = None
    requester: str = "DJ / AutoPlay"
    requester_id: Optional[int] = None
    is_autoplay: bool = False
    query: Optional[str] = None

    @property
    def uri(self) -> str:
        return self.url

    @property
    def formatted_duration(self) -> str:
        if self.duration <= 0:
            return "Live Stream"
        dur = self.duration
        # Handle durations accidentally passed in milliseconds (> 86400 seconds)
        if dur > 86400 and dur > 100000:
            dur = dur // 1000
        h = dur // 3600
        m = (dur % 3600) // 60
        s = dur % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
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
