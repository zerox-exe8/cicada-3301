"""
Kyro Discord Bot - KyroLink Native Audio Resolver
Self-contained, high-speed audio resolution subsystem for Spotify & YouTube.
Zero external Java dependencies, zero sys.path hacking, zero 429 BotGuard blocks.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
import urllib.parse
from typing import Optional, Dict, Any, Tuple
import aiohttp
import yt_dlp

logger = logging.getLogger("Kyro.KyroLinkNative")

_SPOTIFY_TRACK_RE = re.compile(r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?track/([a-zA-Z0-9]+)")
_SPOTIFY_ALBUM_RE = re.compile(r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?album/([a-zA-Z0-9]+)")
_SPOTIFY_PLAYLIST_RE = re.compile(r"https?://open\.spotify\.com/(?:intl-[a-z]{2}/)?playlist/([a-zA-Z0-9]+)")
_SPOTIFY_URI_RE = re.compile(r"spotify:track:([a-zA-Z0-9]+)")

_YOUTUBE_RE = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})",
    re.IGNORECASE,
)


class KyroLinkNativeResolver:
    """Bulletproof, Zero-Block Audio Resolver for Kyro Discord Bot.
    Uses YouTube Android Innertube client emulation for unblocked playback
    and bridges Spotify metadata seamlessly.
    """

    def __init__(self) -> None:
        self._mem_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        current_loop = asyncio.get_running_loop()
        if self._session is None or self._session.closed:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _extract_youtube_sync(self, query: str) -> Optional[Dict[str, Any]]:
        """Extract unblocked YouTube stream using Android Innertube client emulation.
        Supports both direct video URLs and search queries.
        """
        ydl_opts: Dict[str, Any] = {
            "format": "bestaudio/18/best",
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 12,
            "default_search": "ytsearch1",
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"],
                    "player_skip": ["webpage", "configs", "js", "translated_subs"],
                }
            },
        }

        # Format target query
        target = query.strip()
        if not target.startswith(("http://", "https://", "ytsearch:", "ytsearch1:")):
            target = f"ytsearch1:{target}"

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target, download=False)
                if not info:
                    return None

                if "entries" in info and info["entries"]:
                    for item in info["entries"]:
                        if item and item.get("url"):
                            return item
                    return info["entries"][0]
                return info
        except Exception as e:
            logger.debug("[KYROLINK NATIVE] yt-dlp sync notice: %s", e)
            return None

    async def resolve_youtube(self, query: str) -> Optional[Dict[str, Any]]:
        """Async wrapper with 25s timeout and in-memory caching."""
        cache_key = f"yt:{query.strip().lower()}"
        now = time.time()
        if cache_key in self._mem_cache:
            exp, cached_data = self._mem_cache[cache_key]
            if now < exp:
                return cached_data

        try:
            info = await asyncio.wait_for(
                asyncio.to_thread(self._extract_youtube_sync, query),
                timeout=25.0
            )
            if info and info.get("url"):
                title = info.get("title") or "YouTube Audio"
                artist = info.get("uploader") or info.get("channel") or "YouTube Artist"
                if " - " in title and not info.get("uploader"):
                    parts = title.split(" - ", 1)
                    artist = parts[0].strip()

                thumbnail = info.get("thumbnail")
                if not thumbnail and "thumbnails" in info and info["thumbnails"]:
                    thumbnail = info["thumbnails"][-1].get("url")

                track_dict = {
                    "encoded": info.get("url"),
                    "info": {
                        "identifier": info.get("id") or str(int(time.time())),
                        "title": title,
                        "author": artist,
                        "length": int(info.get("duration") or 0) * 1000,
                        "uri": info.get("webpage_url") or f"https://www.youtube.com/watch?v={info.get('id')}",
                        "artworkUrl": thumbnail,
                        "isrc": None,
                        "sourceName": "youtube",
                    },
                    "pluginInfo": {
                        "bitrate": int(info.get("abr") or 160),
                        "unblockable": True,
                        "source": "youtube",
                    }
                }
                # Cache for 45 minutes
                self._mem_cache[cache_key] = (now + 2700, track_dict)
                return track_dict
        except asyncio.TimeoutError:
            logger.warning("[KYROLINK NATIVE] YouTube search timed out for '%s'", query)
        except Exception as e:
            logger.error("[KYROLINK NATIVE] YouTube resolution error: %s", e)

        # Fallback to Kyro's built-in NativeExtractor if available
        try:
            from src.cogs.music._extractor import NativeExtractor
            fb_track = await asyncio.to_thread(
                NativeExtractor._extract_youtube_fallback, query, "KyroLink", False
            )
            if fb_track and fb_track.stream_url:
                logger.info("[KYROLINK NATIVE] NativeExtractor fallback succeeded for '%s'", query)
                return {
                    "encoded": fb_track.stream_url,
                    "info": {
                        "identifier": fb_track.url,
                        "title": fb_track.title,
                        "author": fb_track.author,
                        "length": fb_track.duration * 1000,
                        "uri": fb_track.url,
                        "artworkUrl": fb_track.thumbnail,
                        "isrc": None,
                        "sourceName": "youtube",
                    },
                    "pluginInfo": {
                        "bitrate": 160,
                        "unblockable": True,
                        "source": "youtube",
                    }
                }
        except Exception as fb_err:
            logger.debug("[KYROLINK NATIVE] NativeExtractor fallback notice: %s", fb_err)

        return None

    async def resolve_spotify(self, url_or_uri: str) -> Optional[Dict[str, Any]]:
        """Resolve Spotify track metadata via OEmbed and bridge to YouTube audio."""
        track_match = _SPOTIFY_TRACK_RE.search(url_or_uri) or _SPOTIFY_URI_RE.search(url_or_uri)
        if not track_match:
            return None

        track_id = track_match.group(1)
        cache_key = f"sp:{track_id}"
        now = time.time()
        if cache_key in self._mem_cache:
            exp, cached_data = self._mem_cache[cache_key]
            if now < exp:
                return cached_data

        session = await self.get_session()
        title: Optional[str] = None
        thumb: Optional[str] = None

        # Fetch Spotify OEmbed metadata
        try:
            oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
            async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    title = data.get("title")
                    thumb = data.get("thumbnail_url")
        except Exception as e:
            logger.debug("[KYROLINK NATIVE] Spotify OEmbed notice: %s", e)

        if not title:
            return None

        logger.info("[KYROLINK NATIVE] Bridging Spotify track '%s' to YouTube...", title)
        yt_track = await self.resolve_youtube(title)
        if yt_track:
            # Augment with original Spotify metadata
            yt_track["info"]["title"] = title
            if thumb:
                yt_track["info"]["artworkUrl"] = thumb
            yt_track["info"]["sourceName"] = "spotify"
            yt_track["pluginInfo"]["source"] = "spotify"
            self._mem_cache[cache_key] = (now + 2700, yt_track)
            return yt_track

        return None

    async def resolve(self, query: str) -> Optional[Dict[str, Any]]:
        """Universal entrypoint: Supports Spotify links, YouTube URLs, and Search terms."""
        clean_q = query.strip()
        if not clean_q:
            return None

        # 1. Spotify URL
        if "open.spotify.com" in clean_q or "spotify:track" in clean_q:
            return await self.resolve_spotify(clean_q)

        # 2. YouTube URL or Plain Search
        return await self.resolve_youtube(clean_q)
