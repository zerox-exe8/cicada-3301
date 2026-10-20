import asyncio
import base64
import html
import logging
import re
import urllib.parse
from typing import Optional, List, Dict, Any
import aiohttp
import pyDes

from schemas.media import MediaTrack, MediaSearchResult
from storage.cache import CacheManager

logger = logging.getLogger("kyro.engine.managers.media")

# JioSaavn DES 320kbps decryption cipher
_SAAVN_DES_CIPHER = pyDes.des(
    b"38346591",
    pyDes.ECB,
    b"\0\0\0\0\0\0\0\0",
    pad=None,
    padmode=pyDes.PAD_PKCS5,
)

class MediaManager:
    """Universal Headless Audio Streaming & Extraction Service.
    Powers Web Music Players, Mobile Apps, Telegram Bots, and Discord Voice.
    """

    def __init__(self, cache: Optional[CacheManager] = None) -> None:
        self.cache = cache
        self._session: Optional[aiohttp.ClientSession] = None
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            "X-Forwarded-For": "103.240.233.1",
            "Cookie": "geo=IN; cc=in; L=hindi%2Cenglish",
        }

    async def get_session(self) -> aiohttp.ClientSession:
        current_loop = asyncio.get_running_loop()
        if (
            self._session is None
            or self._session.closed
            or getattr(self._session, "_loop", None) != current_loop
            or self._session._loop.is_closed()
        ):
            self._session = aiohttp.ClientSession(headers=self._headers)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    @staticmethod
    def _decrypt_stream_url(enc_url: str, has_320kbps: bool = True) -> Optional[str]:
        try:
            enc_bytes = base64.b64decode(enc_url.strip())
            dec_bytes = _SAAVN_DES_CIPHER.decrypt(enc_bytes)
            url = dec_bytes.decode("utf-8").strip()
            if has_320kbps:
                return url.replace("_96.mp4", "_320.mp4").replace("_160.mp4", "_320.mp4")
            return url.replace("_96.mp4", "_160.mp4")
        except Exception as e:
            logger.debug("Failed to decrypt stream URL: %s", e)
            return None

    def _parse_song_payload(self, song: Dict[str, Any]) -> Optional[MediaTrack]:
        more_info = song.get("more_info", {})
        enc_url = more_info.get("encrypted_media_url")
        if not enc_url:
            return None

        has_320 = str(more_info.get("320kbps", "true")).lower() != "false"
        stream_url = self._decrypt_stream_url(enc_url, has_320kbps=True)
        if not stream_url:
            return None

        # Clean title & author
        raw_title = song.get("title") or song.get("song") or "Unknown Track"
        title = html.unescape(raw_title).strip()
        artists = more_info.get("artistMap", {}).get("primary_artists", [])
        if artists:
            author = ", ".join([a.get("name", "") for a in artists if a.get("name")])
        else:
            author = song.get("subtitle") or "Official Artist"

        # Image thumbnail (upgrade to 500x500 high-res)
        raw_img = song.get("image") or ""
        thumb = raw_img.replace("150x150", "500x500").replace("50x50", "500x500") if raw_img else None

        duration = int(more_info.get("duration") or song.get("duration") or 0)
        track_id = str(song.get("id") or song.get("perma_url") or title)

        return MediaTrack(
            id=track_id,
            title=title,
            artist=author,
            album=song.get("album"),
            duration=duration,
            stream_url=stream_url,
            webpage_url=song.get("perma_url"),
            thumbnail=thumb,
            bitrate_kbps=320 if has_320 else 160,
            source="jiosaavn"
        )

    async def search(self, query: str, limit: int = 5) -> MediaSearchResult:
        """Search JioSaavn catalog and return structured results with direct playable streams."""
        query_clean = query.strip()
        if not query_clean:
            return MediaSearchResult(query="", count=0, tracks=[])

        # Check Cache
        cache_key = f"media:search:{query_clean.lower()}:{limit}"
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                return MediaSearchResult(**cached)

        session = await self.get_session()
        enc_q = urllib.parse.quote(query_clean)
        url = (
            f"https://www.jiosaavn.com/api.php?"
            f"__call=search.getResults&_format=json&p=1&n={limit}&q={enc_q}"
            f"&_marker=0&api_version=4&ctx=web6dot0&cc=in"
        )

        tracks: List[MediaTrack] = []
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    results = data.get("results", [])
                    for s in results:
                        track = self._parse_song_payload(s)
                        if track:
                            tracks.append(track)
        except Exception as e:
            logger.error("Media search error for '%s': %s", query_clean, e)

        search_result = MediaSearchResult(query=query_clean, count=len(tracks), tracks=tracks)

        # Cache for 10 minutes
        if self.cache and tracks:
            await self.cache.set(cache_key, search_result.model_dump(), ttl_seconds=600)

        return search_result

    async def resolve(self, query: str) -> Optional[MediaTrack]:
        """Resolve a query into the single best match high-fidelity playable track."""
        res = await self.search(query, limit=1)
        if res.tracks:
            return res.tracks[0]
        return None
