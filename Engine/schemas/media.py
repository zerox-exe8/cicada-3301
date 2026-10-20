from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class MediaTrack(BaseModel):
    id: str
    title: str
    artist: str
    album: Optional[str] = None
    duration: int = Field(description="Duration in seconds")
    stream_url: str = Field(description="Direct, unblocked decrypted high-bitrate stream URL")
    webpage_url: Optional[str] = None
    thumbnail: Optional[str] = None
    bitrate_kbps: int = 320
    source: str = "jiosaavn"
    isrc: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class MediaSearchResult(BaseModel):
    query: str
    count: int
    tracks: List[MediaTrack] = Field(default_factory=list)
