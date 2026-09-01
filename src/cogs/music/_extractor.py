"""
Kyro Discord Bot - Native Stream Extractor & Unbreakable Search Engine
Multi-tier phonetic typo resolver with YouTube, SoundCloud, and Spotify fallbacks.
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
    "extract_flat": False,
    "youtube_include_dash_manifest": False,
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "ios", "web"],
        }
    },
}

CONVERSATIONAL_INTENT_PATTERN = re.compile(
    r"\b(?:play|sunao|chalao|bajao|lagao|gaana|song|suno|listen to|put on|music|track|bhai|karo|pls|please|chal)\b",
    re.IGNORECASE,
)

METADATA_NOISE_PATTERN = re.compile(
    r"\b(?:official\s+video|official\s+audio|lyric\s+video|lyrics|full\s+song|hd\s+video|4k|1080p|320kbps|video\s+song|audio\s+song)\b",
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
    """Clean query by removing conversational intents, metadata noise, and fixing phonetic typos."""
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
    """Unbreakable Multi-Tier Search Engine & Audio Stream Extractor."""

    @classmethod
    async def extract(
        cls,
        query: str,
        requester: str = "DJ / AutoPlay",
        is_autoplay: bool = False,
    ) -> Optional[Track]:
        """Extract a playable Track from query or URL using 5-tier fallback cascade."""
        raw_q = query.strip()
        if not raw_q:
            return None

        # 1. Spotify URL Handling
        if "spotify.com" in raw_q:
            spotify_title = await cls._fetch_spotify_title(raw_q)
            if spotify_title:
                raw_q = spotify_title

        # 2. Extract in background thread to avoid blocking asyncio event loop
        return await asyncio.to_thread(cls._sync_extract, raw_q, requester, is_autoplay)

    @classmethod
    def _sync_extract(
        cls,
        raw_query: str,
        requester: str,
        is_autoplay: bool,
    ) -> Optional[Track]:
        """Synchronous 5-tier multi-source search cascade."""
        is_url = raw_query.startswith(("http://", "https://"))
        cleaned_query = parse_and_clean_query(raw_query)

        # Build prioritized search targets
        if is_url:
            search_targets = [raw_query]
        else:
            search_targets = [
                f"ytsearch1:{cleaned_query}",
                f"ytsearch1:{raw_query}",
                f"scsearch1:{cleaned_query}",
                f"scsearch1:{raw_query}",
            ]

        entry = None
        for target in search_targets:
            try:
                with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                    info = ydl.extract_info(target, download=False)
                    if info:
                        cand = info["entries"][0] if "entries" in info and info["entries"] else info
                        if cand and cand.get("url"):
                            entry = cand
                            break
            except Exception as e:
                logger.debug(f"Search target notice for '{target}': {e}")

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
