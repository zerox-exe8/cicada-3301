"""
Kyro Discord Bot - Native Stream Extractor
High-performance async extractor utilizing multi-client yt-dlp and SoundCloud fallbacks.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import List, Optional, Tuple, Union

import aiohttp
import yt_dlp

from src.cogs.music._models import Track

logger = logging.getLogger("Kyro.Music.Extractor")

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1:",
    "extract_flat": False,
    "youtube_include_dash_manifest": False,
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "ios", "web"],
        }
    },
}

CONVERSATIONAL_INTENT_PATTERN = re.compile(
    r"\b(?:play|sunao|chalao|bajao|lagao|gaana|song|suno|listen to|put on|music|track)\b",
    re.IGNORECASE,
)

METADATA_NOISE_PATTERN = re.compile(
    r"\b(?:official\s+video|official\s+audio|lyric\s+video|lyrics|full\s+song|hd\s+video|4k|1080p|320kbps|video\s+song|audio\s+song)\b",
    re.IGNORECASE,
)

PHONETIC_TYPO_MAP = {
    "mossewala": "moose wala",
    "mosewala": "moose wala",
    "sidhu moosewala": "sidhu moose wala",
    "diljeet": "diljit",
    "arijith": "arijit",
    "arjit": "arijit",
    "aniruth": "anirudh",
    "alan waker": "alan walker",
    "marshmellow": "marshmello",
    "eminum": "eminem",
    "post malon": "post malone",
    "som help": "some help",
}


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
    """Clean query by removing conversational intents and metadata noise."""
    cleaned = html.unescape(raw_query).strip()
    no_intent = CONVERSATIONAL_INTENT_PATTERN.sub(" ", cleaned)
    core = METADATA_NOISE_PATTERN.sub(" ", no_intent)
    core_lower = core.lower()
    for typo, correction in PHONETIC_TYPO_MAP.items():
        if typo in core_lower:
            core = re.sub(rf"\b{re.escape(typo)}\b", correction, core, flags=re.IGNORECASE)
    core = re.sub(r"\s+", " ", core).strip()
    return core if core else cleaned


class NativeExtractor:
    """Async audio stream extractor for native Discord playback."""

    @classmethod
    async def extract(
        cls,
        query: str,
        requester: str = "DJ / AutoPlay",
        is_autoplay: bool = False,
    ) -> Optional[Track]:
        """Extract a playable Track from query or URL."""
        raw_q = query.strip()
        if not raw_q:
            return None

        # 1. Spotify URL Handling
        if "spotify.com" in raw_q:
            spotify_title = await cls._fetch_spotify_title(raw_q)
            if spotify_title:
                raw_q = spotify_title

        # 2. Extract in background thread to avoid blocking asyncio event loop
        target = parse_and_clean_query(raw_q)
        return await asyncio.to_thread(cls._sync_extract, target, requester, is_autoplay)

    @classmethod
    def _sync_extract(
        cls,
        query: str,
        requester: str,
        is_autoplay: bool,
    ) -> Optional[Track]:
        """Synchronous yt-dlp extraction with fallback."""
        # Check if direct URL vs search query
        is_url = query.startswith(("http://", "https://"))
        search_target = query if is_url else f"ytsearch1:{query}"

        entry = None
        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(search_target, download=False)
                if info:
                    if "entries" in info and info["entries"]:
                        entry = info["entries"][0]
                    else:
                        entry = info
        except Exception as e:
            logger.debug(f"Primary search notice for '{query}': {e}")

        # Fallback to SoundCloud search if primary failed
        if not entry and not is_url:
            try:
                with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                    info = ydl.extract_info(f"scsearch1:{query}", download=False)
                    if info:
                        if "entries" in info and info["entries"]:
                            entry = info["entries"][0]
                        else:
                            entry = info
            except Exception as e:
                logger.debug(f"SoundCloud fallback notice for '{query}': {e}")

        if not entry:
            return None

        title = clean_track_title(entry.get("title") or "Unknown Track")
        author = entry.get("uploader") or entry.get("artist") or "Official Artist"
        stream_url = entry.get("url")
        webpage_url = entry.get("webpage_url") or entry.get("url") or "https://discord.com"
        duration = int(entry.get("duration") or 0)
        thumbnail = entry.get("thumbnail")

        if not stream_url:
            return None

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
    async def _fetch_spotify_title(spotify_url: str) -> Optional[str]:
        """Extract track title and artist from Spotify URL via oEmbed."""
        oembed_url = f"https://open.spotify.com/oembed?url={spotify_url}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        title = data.get("title", "")
                        return title.strip() if title else None
        except Exception as e:
            logger.debug(f"Spotify oEmbed fetch error: {e}")
        return None
