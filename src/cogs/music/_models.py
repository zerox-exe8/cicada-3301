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
    def formatted_duration(self) -> str:
        if self.duration <= 0:
            return "Live Stream"
        m = self.duration // 60
        s = self.duration % 60
        return f"{m:02d}:{s:02d}"
