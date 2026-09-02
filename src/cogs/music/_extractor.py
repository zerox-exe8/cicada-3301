"""
Kyro Discord Bot - Unblocked Native Stream Extractor & Search Engine
Ultra-fast, high-fidelity audio pipeline powered by:
- Tier 1: JioSaavn 320kbps HD Audio Engine (0% Cloud Block, 100M+ Worldwide Tracks)
- Tier 2: JioSaavn Autocomplete & Detailed Lookup Cascade
- Tier 3: YouTube Metadata Resolver & Direct Stream Fallback
- Spotify & YouTube URL Auto-Bridging
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import pyDes
import yt_dlp

from src.cogs.music._models import Track

logger = logging.getLogger("Kyro.Music.Extractor")

# DES decryption cipher for JioSaavn 320kbps encrypted media streams
_SAAVN_DES_CIPHER = pyDes.des(
    b"38346591",
    pyDes.ECB,
    b"\0\0\0\0\0\0\0\0",
    pad=None,
    padmode=pyDes.PAD_PKCS5,
)

# yt-dlp configuration for YouTube fallback
YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "skip_download": True,
    "socket_timeout": 6,
    "source_address": "0.0.0.0",
    "youtube_include_dash_manifest": False,
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "ios", "web"],
        }
    },
}

# Conversational prefix and suffix pattern stripper
CONVERSATIONAL_PREFIX_PATTERN = re.compile(
    r"^(?:play|sunao|chalao|bajao|lagao|suno|listen\s+to|put\s+on|bhai|karo|pls|please)\s+",
    re.IGNORECASE,
)
CONVERSATIONAL_SUFFIX_PATTERN = re.compile(
    r"\s+(?:sunao|chalao|bajao|lagao|bhai|karo|pls|please)$",
    re.IGNORECASE,
)

METADATA_NOISE_PATTERN = re.compile(
    r"\b(?:official\s+video|official\s+audio|lyric\s+video|full\s+song|hd\s+video|4k|1080p|320kbps|video\s+song|audio\s+song)\b",
    re.IGNORECASE,
)

PHONETIC_TYPO_MAP = {
    "mossewala": "sidhu moose wala",
    "mosewala": "sidhu moose wala",
    "sidhu moosewala": "sidhu moose wala",
    "diljeet": "diljit dosanjh",
    "diljit dosanj": "diljit dosanjh",
    "arijith": "arijit singh",
    "arjit": "arijit singh",
    "arijit sing": "arijit singh",
    "aniruth": "anirudh",
    "alan waker": "alan walker",
    "marshmellow": "marshmello",
    "eminum": "eminem",
    "post malon": "post malone",
    "billie ellish": "billie eilish",
    "sabrina carptener": "sabrina carpenter",
    "karan ojla": "karan aujla",
    "ap dillon": "ap dhillon",
    "shub": "shubh",
    "badsha": "badshah",
    "honeysingh": "yo yo honey singh",
    "arman malik": "armaan malik",
    "atif": "atif aslam",
    "jubin": "jubin nautiyal",
}

# In-memory search cache with 10-minute TTL for instant repeat queries
_SEARCH_CACHE: Dict[str, Tuple[float, Track]] = {}
_CACHE_TTL = 600.0  # 10 minutes


def clean_track_title(raw_title: str) -> str:
    """Clean raw track title for presentation."""
    if not raw_title:
        return ""
    clean = html.unescape(raw_title).strip()
    clean = re.sub(
        r"[\(\[\{]\s*(?:official\s+video|official\s+audio|lyrics?|full\s+song|hd|4k|1080p|audio|video|prod\..*?|dir\..*?)[\)\]\}]",
        "",
        clean,
        flags=re.IGNORECASE,
    )
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def parse_and_clean_query(raw_query: str) -> str:
    """Safely clean query without breaking legitimate song names."""
    cleaned = html.unescape(raw_query).strip()

    # Strip conversational commands from start/end only
    cleaned = CONVERSATIONAL_PREFIX_PATTERN.sub("", cleaned)
    cleaned = CONVERSATIONAL_SUFFIX_PATTERN.sub("", cleaned)

    # Strip noise like 'official video', 'full hd', etc.
    core = METADATA_NOISE_PATTERN.sub(" ", cleaned)
    core_lower = core.lower()

    # Apply phonetic typo corrections
    for typo, correction in PHONETIC_TYPO_MAP.items():
        if typo in core_lower:
            core = re.sub(rf"\b{re.escape(typo)}\b", correction, core, flags=re.IGNORECASE)

    core = re.sub(r"\s+", " ", core).strip()
    return core if core else cleaned


class NativeExtractor:
    """Multi-Tier Cloud Unblocked Music Search Engine & Stream Extractor."""

    @classmethod
    async def extract(
        cls,
        query: str,
        requester: str = "DJ / AutoPlay",
        is_autoplay: bool = False,
    ) -> Optional[Track]:
        """Extract a playable Track from query or URL using multi-tier fallback cascade."""
        raw_q = query.strip()
        if not raw_q:
            return None

        # 1. Check in-memory search cache for instant playback
        cache_key = raw_q.lower()
        now = time.time()
        if cache_key in _SEARCH_CACHE:
            cached_time, cached_track = _SEARCH_CACHE[cache_key]
            if now - cached_time < _CACHE_TTL:
                return Track(
                    title=cached_track.title,
                    author=cached_track.author,
                    url=cached_track.url,
                    stream_url=cached_track.stream_url,
                    duration=cached_track.duration,
                    thumbnail=cached_track.thumbnail,
                    requester=requester,
                    is_autoplay=is_autoplay,
                )

        # 2. Spotify URL Handling
        if "spotify.com" in raw_q:
            spotify_title = await cls._fetch_spotify_title(raw_q)
            if spotify_title:
                raw_q = spotify_title

        # 3. YouTube URL Handling (Extract title metadata to bridge to 320kbps unblocked stream)
        if "youtube.com" in raw_q or "youtu.be" in raw_q:
            yt_title = await cls._fetch_youtube_title(raw_q)
            if yt_title:
                raw_q = yt_title

        cleaned_query = parse_and_clean_query(raw_q)

        # Tier 1 & 2: JioSaavn 320kbps HD Audio (100% Unblocked on Cloud/Render)
        track = await cls._extract_jiosaavn(cleaned_query, requester, is_autoplay)

        # Tier 3: YouTube Fallback (Any rare remaining audio)
        if not track:
            track = await asyncio.to_thread(cls._extract_youtube_fallback, raw_q, requester, is_autoplay)

        # Cache successful extraction
        if track:
            _SEARCH_CACHE[cache_key] = (now, track)
            if len(_SEARCH_CACHE) > 500:
                oldest_key = min(_SEARCH_CACHE.keys(), key=lambda k: _SEARCH_CACHE[k][0])
                _SEARCH_CACHE.pop(oldest_key, None)

        return track

    @classmethod
    async def _extract_jiosaavn(
        cls,
        query: str,
        requester: str,
        is_autoplay: bool,
    ) -> Optional[Track]:
        """Fetch and decrypt 320kbps stream URL from JioSaavn 2-tier search cascade."""
        if not query:
            return None

        encoded_q = urllib.parse.quote(query)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        }

        # Step 1: Query search.getResults
        search_url = (
            f"https://www.jiosaavn.com/api.php?"
            f"__call=search.getResults&_format=json&p=1&n=5&q={encoded_q}"
            f"&_marker=0&api_version=4&ctx=web6dot0"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        data = json.loads(text)
                        results = data.get("results", [])
                        if results:
                            song = results[0]
                            more_info = song.get("more_info", {})
                            has_320 = str(more_info.get("320kbps", "")).lower() == "true"
                            enc_url = more_info.get("encrypted_media_url")
                            if enc_url:
                                dec_stream = cls._decrypt_saavn_url(enc_url, has_320kbps=has_320)
                                if dec_stream:
                                    title = clean_track_title(song.get("title") or song.get("song") or query)
                                    raw_art = more_info.get("artistMap", {}).get("primary_artists", [])
                                    if raw_art:
                                        author = ", ".join([a.get("name", "") for a in raw_art if a.get("name")])
                                    else:
                                        author = song.get("subtitle") or "Official Artist"

                                    raw_image = song.get("image") or ""
                                    thumbnail = (
                                        raw_image.replace("150x150", "500x500").replace("50x50", "500x500")
                                        if raw_image
                                        else "https://cdn.discordapp.com/embed/avatars/0.png"
                                    )
                                    duration = int(more_info.get("duration") or song.get("duration") or 0)
                                    webpage = song.get("perma_url") or "https://www.jiosaavn.com"

                                    return Track(
                                        title=title,
                                        author=author,
                                        url=webpage,
                                        stream_url=dec_stream,
                                        duration=duration,
                                        thumbnail=thumbnail,
                                        requester=requester,
                                        is_autoplay=is_autoplay,
                                    )

                # Step 2: Fallback to autocomplete.get + song.getDetails
                auto_url = (
                    f"https://www.jiosaavn.com/api.php?"
                    f"__call=autocomplete.get&_format=json&_marker=0&cc=in&includeMetaTags=1&query={encoded_q}"
                )
                async with session.get(auto_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp2:
                    if resp2.status == 200:
                        text2 = await resp2.text()
                        data2 = json.loads(text2)
                        songs2 = data2.get("songs", {}).get("data", [])
                        if songs2:
                            first_song = songs2[0]
                            pid = first_song.get("id")
                            if pid:
                                det_url = (
                                    f"https://www.jiosaavn.com/api.php?"
                                    f"__call=song.getDetails&cc=in&_marker=0%3F_marker%3D0&_format=json&pids={pid}"
                                )
                                async with session.get(det_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp3:
                                    if resp3.status == 200:
                                        text3 = await resp3.text()
                                        det_data = json.loads(text3)
                                        sinfo = det_data.get(pid, {})
                                        enc_url = sinfo.get("encrypted_media_url")
                                        if enc_url:
                                            dec_stream = cls._decrypt_saavn_url(enc_url)
                                            if dec_stream:
                                                title = clean_track_title(first_song.get("title") or query)
                                                author = first_song.get("description") or first_song.get("more_info", {}).get("primary_artists") or "Official Artist"
                                                raw_image = first_song.get("image") or ""
                                                thumbnail = (
                                                    raw_image.replace("150x150", "500x500").replace("50x50", "500x500")
                                                    if raw_image
                                                    else "https://cdn.discordapp.com/embed/avatars/0.png"
                                                )
                                                duration = int(sinfo.get("duration") or 0)
                                                webpage = first_song.get("url") or "https://www.jiosaavn.com"

                                                return Track(
                                                    title=title,
                                                    author=author,
                                                    url=webpage,
                                                    stream_url=dec_stream,
                                                    duration=duration,
                                                    thumbnail=thumbnail,
                                                    requester=requester,
                                                    is_autoplay=is_autoplay,
                                                )
        except Exception as e:
            logger.debug(f"JioSaavn search notice for '{query}': {e}")

        return None

    @staticmethod
    def _decrypt_saavn_url(encrypted_url: str, has_320kbps: bool = True) -> Optional[str]:
        """Decrypt JioSaavn media stream URL with reliable bitrate fallback."""
        try:
            enc_bytes = base64.b64decode(encrypted_url.strip())
            dec_bytes = _SAAVN_DES_CIPHER.decrypt(enc_bytes)
            url = dec_bytes.decode("utf-8").strip()
            if has_320kbps:
                return url.replace("_96.mp4", "_320.mp4").replace("_160.mp4", "_320.mp4")
            else:
                return url.replace("_96.mp4", "_160.mp4")
        except Exception:
            return None

    @classmethod
    def _extract_youtube_fallback(
        cls,
        raw_query: str,
        requester: str,
        is_autoplay: bool,
    ) -> Optional[Track]:
        """YouTube search fallback for rare tracks."""
        is_url = raw_query.startswith(("http://", "https://"))
        target = raw_query if is_url else f"ytsearch1:{raw_query}"
        entry = cls._sync_yt_dlp_extract(target)
        if not entry or not entry.get("url"):
            return None

        title = clean_track_title(entry.get("title") or "Unknown Track")
        author = entry.get("uploader") or entry.get("artist") or "YouTube Artist"
        stream_url = entry.get("url")
        webpage_url = entry.get("webpage_url") or entry.get("url") or "https://youtube.com"
        duration = int(entry.get("duration") or 0)
        thumbnail = entry.get("thumbnail")

        return Track(
            title=title,
            author=author,
            url=webpage_url,
            stream_url=stream_url,
            duration=duration,
            thumbnail=thumbnail,
            requester=requester,
            is_autoplay=is_autoplay,
        )

    @staticmethod
    def _sync_yt_dlp_extract(target: str) -> Optional[Dict[str, Any]]:
        """Helper to run yt-dlp extraction safely."""
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            try:
                info = ydl.extract_info(target, download=False)
                if not info:
                    return None
                entries = info.get("entries") or [info]
                if entries and len(entries) > 0 and entries[0]:
                    return entries[0]
            except Exception:
                pass
        return None

    @staticmethod
    async def _fetch_spotify_title(spotify_url: str) -> Optional[str]:
        """Extract track title and artist from Spotify URL via oEmbed."""
        oembed_url = f"https://open.spotify.com/oembed?url={spotify_url}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        data = json.loads(text)
                        title = data.get("title", "")
                        return title.strip() if title else None
        except Exception as e:
            logger.debug(f"Spotify oEmbed fetch error: {e}")
        return None

    @staticmethod
    async def _fetch_youtube_title(youtube_url: str) -> Optional[str]:
        """Extract title and artist metadata from YouTube URL without streaming chunk blocks."""
        try:
            def _get_title():
                with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as ydl:
                    info = ydl.extract_info(youtube_url, download=False)
                    if info:
                        return info.get("title")
                return None

            return await asyncio.to_thread(_get_title)
        except Exception as e:
            logger.debug(f"YouTube title extract error: {e}")
        return None
