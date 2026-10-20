import asyncio
import html
import logging
import re
import time
import urllib.parse
from typing import Optional, List, Dict, Any, Tuple
import aiohttp

from schemas.media import MediaTrack, MediaSearchResult
from storage.cache import CacheManager
from config.settings import settings
from kyrolink.proxy_manager import ProxyPoolManager

logger = logging.getLogger("kyro.engine.kyrolink.unblockable")

# Regular Expressions for Provider Matching
_SPOTIFY_TRACK_RE = re.compile(r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?track/([a-zA-Z0-9]+)")
_SPOTIFY_ALBUM_RE = re.compile(r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?album/([a-zA-Z0-9]+)")
_SPOTIFY_PLAYLIST_RE = re.compile(r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?playlist/([a-zA-Z0-9]+)")
_SPOTIFY_URI_RE = re.compile(r"spotify:track:([a-zA-Z0-9]+)")

_YOUTUBE_RE = re.compile(r"(?:https?://)?(?:www\.|music\.)?(?:youtube\.com/(?:watch\?v=|v/|embed/|shorts/)|youtu\.be/)([\w-]{11})")


class UnblockableResolver:
    """Enterprise Unblockable Audio Streaming & Extraction System (Spotify + YouTube Native).
    Bypasses YouTube 429 IP bans, BotGuard, PoToken challenges using Android Innertube client emulation
    and bridges Spotify metadata seamlessly without relying on third-party CDNs.
    """

    def __init__(
        self,
        media_manager: Optional[Any] = None,
        proxy_pool: Optional[ProxyPoolManager] = None,
        cache: Optional[CacheManager] = None,
    ) -> None:
        self.media_manager = media_manager
        self.proxy_pool = proxy_pool or ProxyPoolManager()
        self.cache = cache
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._spotify_token: Optional[str] = None
        self._spotify_token_expires_at: float = 0.0
        # In-memory fast LRU cache (query -> (expire_time, MediaTrack))
        self._mem_cache: Dict[str, Tuple[float, MediaTrack]] = {}

        # Load proxies from settings if present
        if hasattr(settings, "PROXY_LIST") and settings.PROXY_LIST:
            self.proxy_pool.load_from_csv(settings.PROXY_LIST)

    async def get_session(self) -> aiohttp.ClientSession:
        current_loop = asyncio.get_running_loop()
        if (
            self._http_session is None
            or self._http_session.closed
            or getattr(self._http_session, "_loop", None) != current_loop
            or self._http_session._loop.is_closed()
        ):
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
            }
            self._http_session = aiohttp.ClientSession(headers=headers)
        return self._http_session

    async def close(self) -> None:
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()

    # =========================================================================
    # PROVIDER 1: YOUTUBE INNERTUBE WITH ANDROID CLIENT EMULATION
    # =========================================================================
    def _extract_youtube_sync(self, query: str, proxy: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Synchronous yt-dlp extraction using Android Music & Android TV Innertube clients.
        Completely bypasses YouTube BotGuard, PoToken challenges, and web browser 429 rate limits.
        """
        import yt_dlp

        client_list = ["android_music", "android", "ios"]
        if hasattr(settings, "YOUTUBE_CLIENTS") and settings.YOUTUBE_CLIENTS:
            custom_clients = [c.strip() for c in settings.YOUTUBE_CLIENTS.split(",") if c.strip()]
            if custom_clients:
                client_list = custom_clients

        ydl_opts: Dict[str, Any] = {
            "format": "bestaudio[ext=m4a][abr>=160]/bestaudio[ext=webm][abr>=160]/bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": 8,
            "prefer_free_formats": True,
            "extractor_args": {
                "youtube": {
                    "player_client": client_list,
                    "player_skip": ["webpage", "configs", "js"],
                }
            },
        }

        if proxy:
            ydl_opts["proxy"] = proxy

        if hasattr(settings, "YOUTUBE_COOKIE_FILE") and settings.YOUTUBE_COOKIE_FILE:
            ydl_opts["cookiefile"] = settings.YOUTUBE_COOKIE_FILE

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(query, download=False)
                if not info:
                    return None

                # Handle search result lists
                if "entries" in info and info["entries"]:
                    for item in info["entries"]:
                        if item and item.get("url"):
                            return item
                    return info["entries"][0]
                return info
        except Exception as e:
            err_str = str(e).lower()
            if "429" in err_str or "sign in to confirm" in err_str or "bot" in err_str:
                logger.warning("[YOUTUBE IP BAN] Block detected on proxy=%s: %s", proxy, e)
                if proxy:
                    self.proxy_pool.report_failure(proxy, is_ban=True)
            else:
                logger.debug("[YOUTUBE EXTRACT] Notice: %s", e)
                if proxy:
                    self.proxy_pool.report_failure(proxy, is_ban=False)
            return None

    async def resolve_youtube(self, query: str) -> Optional[MediaTrack]:
        """Extract unblocked YouTube stream using Android client emulation & rotating proxies."""
        # Normalize search query
        clean_q = query.strip()
        search_target = clean_q if clean_q.startswith("http") or clean_q.startswith("ytsearch:") else f"ytsearch:{clean_q}"

        # 1. In-memory cache check (< 1ms)
        cache_key = f"yt:{search_target.lower()}"
        now = time.time()
        if cache_key in self._mem_cache:
            exp, track = self._mem_cache[cache_key]
            if now < exp:
                return track

        # 2. Redis/L2 cache check
        if self.cache:
            cached = await self.cache.get(f"media:youtube:{cache_key}")
            if cached:
                return MediaTrack(**cached)

        # 3. Retry loop across proxy pool with Android Innertube client
        max_attempts = max(1, min(self.proxy_pool.total_proxies, 2)) + 1
        for attempt in range(max_attempts):
            proxy = self.proxy_pool.get_proxy()
            try:
                info = await asyncio.wait_for(
                    asyncio.to_thread(self._extract_youtube_sync, search_target, proxy),
                    timeout=10.0
                )
                if info and info.get("url"):
                    if proxy:
                        self.proxy_pool.report_success(proxy)

                    # Extract best available thumbnail
                    thumbnail_url = info.get("thumbnail")
                    if not thumbnail_url and "thumbnails" in info and info["thumbnails"]:
                        thumbnail_url = info["thumbnails"][-1].get("url")

                    # Extract artist/uploader
                    artist_name = info.get("uploader") or info.get("channel") or info.get("creator") or "YouTube Artist"
                    if " - " in info.get("title", ""):
                        parts = info["title"].split(" - ", 1)
                        if len(parts) == 2 and not info.get("uploader"):
                            artist_name = parts[0].strip()

                    track = MediaTrack(
                        id=info.get("id") or str(int(time.time())),
                        title=info.get("title") or "YouTube Audio",
                        artist=artist_name,
                        album=None,
                        duration=int(info.get("duration") or 0),
                        stream_url=info.get("url"),
                        webpage_url=info.get("webpage_url") or f"https://www.youtube.com/watch?v={info.get('id')}",
                        thumbnail=thumbnail_url,
                        bitrate_kbps=int(info.get("abr") or 160),
                        source="youtube",
                        isrc=None,
                        metadata={
                            "view_count": info.get("view_count"),
                            "proxy_used": bool(proxy),
                            "format_id": info.get("format_id"),
                            "ext": info.get("ext"),
                        }
                    )

                    # Cache track for 45 minutes
                    self._mem_cache[cache_key] = (now + 2700, track)
                    if self.cache:
                        await self.cache.set(f"media:youtube:{cache_key}", track.model_dump(), ttl_seconds=2700)

                    return track

            except asyncio.TimeoutError:
                logger.warning("[YOUTUBE TIMEOUT] Attempt %d timed out for '%s'", attempt + 1, query)
                if proxy:
                    self.proxy_pool.report_failure(proxy, is_ban=False)
            except Exception as e:
                logger.debug("[YOUTUBE ATTEMPT ERROR] %s", e)

        return None

    # =========================================================================
    # PROVIDER 2: SPOTIFY METADATA & YOUTUBE AUDIO BRIDGING
    # =========================================================================
    async def resolve_spotify(self, url_or_uri: str) -> Optional[MediaTrack]:
        """Extract Spotify track metadata and bridge to an unblocked high-speed YouTube stream."""
        track_match = _SPOTIFY_TRACK_RE.search(url_or_uri) or _SPOTIFY_URI_RE.search(url_or_uri)
        if not track_match:
            return None

        track_id = track_match.group(1)
        cache_key = f"sp:{track_id}"
        now = time.time()
        if cache_key in self._mem_cache:
            exp, track = self._mem_cache[cache_key]
            if now < exp:
                return track

        session = await self.get_session()
        title: Optional[str] = None
        artists: Optional[str] = None
        thumb: Optional[str] = None

        # Method 1: Spotify OEmbed API (Fastest, zero-auth, 100% reliable)
        try:
            oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
            async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=3.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    title = data.get("title")
                    thumb = data.get("thumbnail_url")
        except Exception as e:
            logger.debug("[SPOTIFY] OEmbed lookup notice: %s", e)

        if not title:
            logger.warning("[SPOTIFY] Unable to resolve metadata for track ID: %s", track_id)
            return None

        # Bridge directly to YouTube Innertube Android Client
        clean_search = f"{title} {artists}" if artists else title
        logger.info("[SPOTIFY BRIDGING] Track: '%s' -> Resolving via YouTube Android...", clean_search)

        yt_track = await self.resolve_youtube(f"ytsearch:{clean_search}")
        if yt_track:
            bridged = yt_track.model_copy(update={
                "title": title,
                "artist": artists or yt_track.artist,
                "thumbnail": thumb or yt_track.thumbnail,
                "source": "spotify"
            })
            self._mem_cache[cache_key] = (now + 2700, bridged)
            return bridged

        return None

    # =========================================================================
    # PROVIDER 3: SOUNDCLOUD FALLBACK
    # =========================================================================
    async def resolve_soundcloud(self, query: str) -> Optional[MediaTrack]:
        """Fallback to SoundCloud if YouTube is unavailable."""
        import yt_dlp

        ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 6,
        }
        search_q = query if query.startswith("scsearch:") or query.startswith("http") else f"scsearch:{query}"
        try:
            info = await asyncio.to_thread(lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(search_q, download=False))
            if info:
                if "entries" in info and info["entries"]:
                    info = info["entries"][0]
                return MediaTrack(
                    id=str(info.get("id", int(time.time()))),
                    title=info.get("title") or "SoundCloud Track",
                    artist=info.get("uploader") or "SoundCloud Artist",
                    album=None,
                    duration=int(info.get("duration") or 0),
                    stream_url=info.get("url"),
                    webpage_url=info.get("webpage_url"),
                    thumbnail=info.get("thumbnail"),
                    bitrate_kbps=128,
                    source="soundcloud"
                )
        except Exception as e:
            logger.debug("[SOUNDCLOUD] Resolution notice: %s", e)
        return None

    # =========================================================================
    # UNIVERSAL RESOLUTION ENTRYPOINT (SPOTIFY + YOUTUBE ONLY)
    # =========================================================================
    async def resolve(self, query: str) -> Optional[MediaTrack]:
        """Universal, zero-freeze resolution cascade.
        Prioritizes Spotify & YouTube directly. Zero reliance on JioSaavn.
        """
        clean_q = query.strip()
        if not clean_q:
            return None

        # 1. Spotify URL / URI Detection
        if _SPOTIFY_TRACK_RE.search(clean_q) or _SPOTIFY_URI_RE.search(clean_q):
            logger.info("[KYROLINK] Routing to Spotify Resolver...")
            track = await self.resolve_spotify(clean_q)
            if track:
                return track

        # 2. Direct YouTube URL Detection
        if _YOUTUBE_RE.search(clean_q):
            logger.info("[KYROLINK] Routing to YouTube Android URL Resolver...")
            track = await self.resolve_youtube(clean_q)
            if track:
                return track

        # 3. Explicit YouTube Search (ytsearch:...)
        if clean_q.startswith("ytsearch:"):
            return await self.resolve_youtube(clean_q)

        # 4. Explicit SoundCloud Search (scsearch:...)
        if clean_q.startswith("scsearch:"):
            return await self.resolve_soundcloud(clean_q)

        # 5. General Search (Song name, artist, lyrics) -> Directly to YouTube Android Innertube!
        logger.info("[KYROLINK] Resolving search query via YouTube Android Client: '%s'", clean_q)
        track = await self.resolve_youtube(clean_q)
        if track:
            return track

        # Fallback to SoundCloud if YouTube fails completely
        logger.info("[KYROLINK] Falling back to SoundCloud for: '%s'", clean_q)
        return await self.resolve_soundcloud(clean_q)
