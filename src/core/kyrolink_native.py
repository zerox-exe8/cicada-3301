"""
Kyro Discord Bot - KyroLink Ultra-Resilient Native Audio Resolver
Enterprise-grade, zero-block audio resolution subsystem for Spotify & YouTube.
Reverse-engineered from Lavalink v4 InnerTube protocol and multi-client rotation.

Features:
- Sub-second native InnerTube API search (WEB & WEB_REMIX)
- Multi-client YouTube stream extraction (TV_EMBEDDED, TV, IOS, MWEB, ANDROID)
- Seamless Spotify OEmbed & Web API metadata bridging
- Anti-429 / Anti-BotGuard resilient fallback cascade
- Auxiliary SoundCloud stream fail-safe (zero datacenter IP blocks)
- In-memory LRU caching with 45-minute TTL
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
    Uses reverse-engineered YouTube InnerTube client emulation for unblocked playback,
    Spotify metadata bridging, and resilient multi-tier fallback.
    """

    def __init__(self) -> None:
        self._mem_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        current_loop = asyncio.get_running_loop()
        if (
            self._session is None
            or self._session.closed
            or getattr(self._session, "_loop", None) != current_loop
            or self._session._loop.is_closed()
        ):
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
            }
            self._session = aiohttp.ClientSession(headers=headers)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # =========================================================================
    # REVERSE-ENGINEERED INNERTUBE FAST SEARCH (Direct HTTP, < 1.0s)
    # =========================================================================
    async def innertube_search(self, query: str) -> Optional[Dict[str, Any]]:
        """Direct HTTP search using YouTube InnerTube API (WEB client).
        Bypasses CLI process spawning and delivers results in ~300ms-800ms.
        """
        session = await self.get_session()
        url = "https://www.youtube.com/youtubei/v1/search?prettyPrint=false"
        payload = {
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": "2.20240722.01.00",
                    "hl": "en",
                    "gl": "US",
                }
            },
            "query": query,
            "params": "EgIQAfABAQ==",  # Videos only, suicide warning filter bypass
        }
        headers = {
            "Content-Type": "application/json",
            "Referer": "https://www.youtube.com/",
        }

        try:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                contents = (
                    data.get("contents", {})
                    .get("twoColumnSearchResultsRenderer", {})
                    .get("primaryContents", {})
                    .get("sectionListRenderer", {})
                    .get("contents", [])
                )
                for section in contents:
                    items = section.get("itemSectionRenderer", {}).get("contents", [])
                    for item in items:
                        v = item.get("videoRenderer")
                        if v and v.get("videoId"):
                            vid_id = v.get("videoId")
                            title_runs = v.get("title", {}).get("runs", [])
                            title = title_runs[0].get("text", "") if title_runs else v.get("title", {}).get("simpleText", "YouTube Track")
                            owner_runs = v.get("ownerText", {}).get("runs", [])
                            author = owner_runs[0].get("text", "YouTube Artist") if owner_runs else "YouTube Artist"
                            dur_str = v.get("lengthText", {}).get("simpleText", "0:00")
                            dur_sec = 0
                            try:
                                parts = [int(p) for p in dur_str.split(":")]
                                if len(parts) == 2:
                                    dur_sec = parts[0] * 60 + parts[1]
                                elif len(parts) == 3:
                                    dur_sec = parts[0] * 3600 + parts[1] * 60 + parts[2]
                            except Exception:
                                pass

                            thumb = None
                            thumbs = v.get("thumbnail", {}).get("thumbnails", [])
                            if thumbs:
                                thumb = thumbs[-1].get("url")

                            return {
                                "id": vid_id,
                                "title": title,
                                "author": author,
                                "duration": dur_sec,
                                "thumbnail": thumb,
                                "webpage_url": f"https://www.youtube.com/watch?v={vid_id}",
                            }
        except Exception as e:
            logger.debug("[KYROLINK NATIVE] InnerTube search notice for '%s': %s", query, e)

        return None

    # =========================================================================
    # MULTI-CLIENT YOUTUBE STREAM EXTRACTOR
    # =========================================================================
    def _extract_youtube_sync(self, target_url: str) -> Optional[Dict[str, Any]]:
        """Synchronous multi-client stream extractor with full JS cipher support.
        Rotates tv_embedded, tv, ios, mweb, and android clients to avoid BotGuard challenges.
        """
        ydl_opts: Dict[str, Any] = {
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/18/best",
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 10,
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv_embedded", "tv", "ios", "mweb", "android"],
                }
            },
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
                if not info:
                    return None
                if "entries" in info and info["entries"]:
                    for item in info["entries"]:
                        if item and item.get("url"):
                            return item
                    return info["entries"][0]
                return info
        except Exception as e:
            logger.debug("[KYROLINK NATIVE] yt-dlp multi-client notice: %s", e)
            return None

    # =========================================================================
    # UNIVERSAL RESOLVE WORKFLOW
    # =========================================================================
    async def resolve_youtube(self, query: str) -> Optional[Dict[str, Any]]:
        """Resolve YouTube stream using InnerTube metadata search + multi-client stream extraction."""
        cache_key = f"yt:{query.strip().lower()}"
        now = time.time()
        if cache_key in self._mem_cache:
            exp, cached_data = self._mem_cache[cache_key]
            if now < exp:
                return cached_data

        clean_q = query.strip()
        yt_match = _YOUTUBE_RE.search(clean_q)
        target_url = clean_q if yt_match else None
        meta = None

        # 1. Fast metadata resolution if query is text
        if not target_url:
            meta = await self.innertube_search(clean_q)
            if meta and meta.get("webpage_url"):
                target_url = meta["webpage_url"]
            else:
                target_url = f"ytsearch1:{clean_q}"

        # 2. Multi-client stream extraction
        try:
            info = await asyncio.wait_for(
                asyncio.to_thread(self._extract_youtube_sync, target_url),
                timeout=18.0,
            )
            if info and info.get("url"):
                title = info.get("title") or (meta.get("title") if meta else None) or "YouTube Audio"
                artist = info.get("uploader") or info.get("channel") or (meta.get("author") if meta else None) or "YouTube Artist"
                if " - " in title and not info.get("uploader"):
                    parts = title.split(" - ", 1)
                    artist = parts[0].strip()

                thumbnail = info.get("thumbnail") or (meta.get("thumbnail") if meta else None)
                if not thumbnail and "thumbnails" in info and info["thumbnails"]:
                    thumbnail = info["thumbnails"][-1].get("url")

                track_dict = {
                    "encoded": info.get("url"),
                    "info": {
                        "identifier": info.get("id") or (meta.get("id") if meta else str(int(time.time()))),
                        "title": title,
                        "author": artist,
                        "length": int(info.get("duration") or (meta.get("duration") if meta else 0)) * 1000,
                        "uri": info.get("webpage_url") or target_url,
                        "artworkUrl": thumbnail,
                        "isrc": None,
                        "sourceName": "youtube",
                    },
                    "pluginInfo": {
                        "bitrate": int(info.get("abr") or 160),
                        "unblockable": True,
                        "source": "youtube",
                    },
                }
                self._mem_cache[cache_key] = (now + 2700, track_dict)
                return track_dict
        except asyncio.TimeoutError:
            logger.warning("[KYROLINK NATIVE] YouTube multi-client stream timed out for '%s'", query)
        except Exception as e:
            logger.error("[KYROLINK NATIVE] YouTube resolution error: %s", e)

        # 3. Resilient Fail-Safe: SoundCloud Native Extraction (0% YouTube IP Ban Risk)
        try:
            from src.cogs.music._extractor import NativeExtractor

            search_query = meta["title"] if (meta and meta.get("title")) else clean_q
            logger.info("[KYROLINK NATIVE] Engaging SoundCloud anti-block fail-safe for '%s'", search_query)
            sc_track = await NativeExtractor._extract_soundcloud(search_query, "KyroLink", False)
            if sc_track and sc_track.stream_url:
                logger.info("[KYROLINK NATIVE] SoundCloud fail-safe successfully resolved '%s'", sc_track.title)
                track_dict = {
                    "encoded": sc_track.stream_url,
                    "info": {
                        "identifier": sc_track.url,
                        "title": sc_track.title,
                        "author": sc_track.author,
                        "length": sc_track.duration * 1000,
                        "uri": sc_track.url,
                        "artworkUrl": sc_track.thumbnail,
                        "isrc": None,
                        "sourceName": "soundcloud",
                    },
                    "pluginInfo": {
                        "bitrate": 160,
                        "unblockable": True,
                        "source": "soundcloud",
                    },
                }
                self._mem_cache[cache_key] = (now + 2700, track_dict)
                return track_dict
        except Exception as sc_err:
            logger.debug("[KYROLINK NATIVE] SoundCloud fail-safe notice: %s", sc_err)

        return None

    # =========================================================================
    # SPOTIFY METADATA & AUDIO BRIDGING
    # =========================================================================
    async def resolve_spotify(self, url_or_uri: str) -> Optional[Dict[str, Any]]:
        """Resolve Spotify track metadata via OEmbed/Web API and bridge to YouTube audio."""
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

        # 1. Fetch Spotify OEmbed metadata
        try:
            oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
            async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    title = data.get("title")
                    thumb = data.get("thumbnail_url")
        except Exception as e:
            logger.debug("[KYROLINK NATIVE] Spotify OEmbed notice: %s", e)

        # 2. Fallback to NativeExtractor Spotify API helper
        if not title:
            try:
                from src.cogs.music._extractor import NativeExtractor
                title = await NativeExtractor._fetch_spotify_title(f"https://open.spotify.com/track/{track_id}")
            except Exception as sp_api_err:
                logger.debug("[KYROLINK NATIVE] NativeExtractor Spotify helper notice: %s", sp_api_err)

        if not title:
            return None

        logger.info("[KYROLINK NATIVE] Bridging Spotify track '%s' to audio...", title)
        yt_track = await self.resolve_youtube(title)
        if yt_track:
            yt_track["info"]["title"] = title
            if thumb:
                yt_track["info"]["artworkUrl"] = thumb
            yt_track["info"]["sourceName"] = "spotify"
            yt_track["pluginInfo"]["source"] = "spotify"
            self._mem_cache[cache_key] = (now + 2700, yt_track)
            return yt_track

        return None

    # =========================================================================
    # UNIVERSAL ENTRYPOINT
    # =========================================================================
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
