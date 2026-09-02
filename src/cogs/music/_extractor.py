"""
Kyro Discord Bot - Native Stream Extractor & Unbreakable Search Engine
Ultra-fast, 100% accurate search pipeline powered by YouTube Music, YouTube,
SoundCloud, and Spotify oEmbed cascade with smart phonetic typo resolver.
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import yt_dlp

from src.cogs.music._models import Track

logger = logging.getLogger("Kyro.Music.Extractor")

# Fast, high-stability yt-dlp extractor configuration
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

# Only strip intent prefixes/suffixes at the edges so inner song titles remain intact
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


def select_best_candidate(entries: List[Dict[str, Any]], query: str) -> Optional[Dict[str, Any]]:
    """Score and pick the most accurate musical track candidate from search results."""
    if not entries:
        return None

    query_lower = query.lower()
    scored_candidates = []

    for entry in entries:
        if not entry or not entry.get("url"):
            continue

        title = (entry.get("title") or "").lower()
        uploader = (entry.get("uploader") or entry.get("artist") or "").lower()
        duration = int(entry.get("duration") or 0)

        # Baseline score
        score = 100

        # Penalize non-music clutter unless user asked for it
        if duration < 30 and "short" not in query_lower:
            score -= 60  # Likely a YouTube Short / Meme
        elif duration > 7200 and "mix" not in query_lower and "playlist" not in query_lower:
            score -= 30  # 2+ hour long video

        if "reaction" in title and "reaction" not in query_lower:
            score -= 80
        if "review" in title and "review" not in query_lower:
            score -= 80
        if "parody" in title and "parody" not in query_lower:
            score -= 70

        # Reward official / topic / verified releases
        if "- topic" in uploader or "vevo" in uploader or "official" in uploader:
            score += 25

        # Reward query word matches in title
        for word in query_lower.split():
            if len(word) > 2 and word in title:
                score += 15

        scored_candidates.append((score, entry))

    if not scored_candidates:
        return entries[0] if entries else None

    # Sort descending by score
    scored_candidates.sort(key=lambda x: x[0], reverse=True)
    return scored_candidates[0][1]


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

        # 1. Check in-memory search cache for instant playback
        cache_key = raw_q.lower()
        now = time.time()
        if cache_key in _SEARCH_CACHE:
            cached_time, cached_track = _SEARCH_CACHE[cache_key]
            if now - cached_time < _CACHE_TTL:
                # Return clone with updated requester
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

        # 3. Extract in background thread
        track = await asyncio.to_thread(cls._sync_extract, raw_q, requester, is_autoplay)
        
        # 4. Store in cache if successful
        if track:
            _SEARCH_CACHE[cache_key] = (now, track)
            # Prune old cache entries if too large
            if len(_SEARCH_CACHE) > 500:
                oldest_key = min(_SEARCH_CACHE.keys(), key=lambda k: _SEARCH_CACHE[k][0])
                _SEARCH_CACHE.pop(oldest_key, None)

        return track

    @classmethod
    def _sync_extract(
        cls,
        raw_query: str,
        requester: str,
        is_autoplay: bool,
    ) -> Optional[Track]:
        """Synchronous multi-source search cascade with YTM priority and smart scoring."""
        is_url = raw_query.startswith(("http://", "https://"))
        cleaned_query = parse_and_clean_query(raw_query)

        # Build prioritized search targets (YouTube Music first for 100% music accuracy)
        if is_url:
            search_targets = [raw_query]
        else:
            search_targets = [
                f"ytmsearch3:{cleaned_query}",  # YouTube Music (Pure music/tracks)
                f"ytsearch3:{cleaned_query}",   # YouTube standard fallback
                f"ytsearch3:{raw_query}",       # Raw search fallback
                f"scsearch2:{cleaned_query}",   # SoundCloud fallback
            ]

        entry = None
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            for target in search_targets:
                try:
                    info = ydl.extract_info(target, download=False)
                    if info:
                        entries = info.get("entries") or [info]
                        cand = select_best_candidate(entries, cleaned_query)
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
