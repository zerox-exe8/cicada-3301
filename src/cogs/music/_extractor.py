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
import os
import re
import time
import unicodedata
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import pyDes
import yt_dlp

from src.cogs.music._models import Track, PlaylistResult, PlaylistTrackItem

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
    "ignoreerrors": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["android"],
        }
    },
}

# Regex to reliably match and extract YouTube 11-char video ID from any link or text format
YOUTUBE_URL_REGEX = re.compile(
    r"(?:https?://)?(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([a-zA-Z0-9_-]{11})",
    re.IGNORECASE,
)

# Conversational prefix and suffix pattern stripper (safe for titles like 'Play Date' or 'Suno Na')
CONVERSATIONAL_PREFIX_PATTERN = re.compile(
    r"^(?:(?:pls|please|can\s+you)\s+play\s+|(?:bhai\s+)?(?:ek\s+)?(?:gana|gaana|song)\s+(?:sunao|bajao|chalao|lagao)\s+|listen\s+to\s+|put\s+on\s+)",
    re.IGNORECASE,
)
CONVERSATIONAL_SUFFIX_PATTERN = re.compile(
    r"\s+(?:sunao|chalao|bajao|lagao|bhai)$",
    re.IGNORECASE,
)

METADATA_NOISE_PATTERN = re.compile(
    r"\b(?:official\s+(?:music\s+)?video|official\s+audio|lyric(?:al)?(?:\s+video)?|full\s+(?:video|song)|video\s+song|audio\s+song|hd\s+video|4k|1080p|320kbps|gaana\s+originals?|promo\s+video|visualizer)\b",
    re.IGNORECASE,
)

# Strip leading format prefixes (e.g. '8D Audio -', '[8D AUDIO]', '8D Song', 'Slowed + Reverb -')
AUDIO_FORMAT_PREFIX_PATTERN = re.compile(
    r"^(?:(?:\[|\()?\s*(?:8d|3d|16d|spatial|surround|lo-?fi|slowed(?:\s*\+\s*reverb)?|bass\s*boosted|remix|acoustic)?\s*(?:audio|music|songs?|version|mix)?\s*(?:\]|\))?\s*[-:|~•]\s*)+"
    r"|^(?:(?:\[|\()?\s*(?:8d|3d|16d|spatial|surround)\s*(?:audio|music|songs?|version|mix)?\s*(?:\]|\))?\s*[-:|~•]?\s*)+",
    re.IGNORECASE,
)

AUDIO_FORMAT_TAGS = re.compile(
    r"\b(?:use\s+headphones?|put\s+on\s+headphones?|headphones?\s+recommended|8d\s+audio|8d\s+song|8d\s+music|3d\s+audio|3d\s+song|spatial\s+audio)\b",
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

# Modifiers indicating non-original / alternate versions of songs
UNWANTED_VERSION_KEYWORDS = [
    # DJ, Remixes & Dance edits
    "remix", "remixed", "dj", "dj mix", "dj version", "djs", "dance mix",
    "club mix", "flip", "bootleg", "drop", "bass boosted", "trap mix", "mashup",
    
    # Guitar, Instrumental & Acoustic Covers
    "guitar", "guitar cover", "fingerstyle", "lead guitar", "acoustic guitar",
    "acoustic", "unplugged", "piano version", "piano cover", "instrumental",
    "flute", "violin", "sitar", "harmonium", "ukulele", "orchestral", "8-bit",
    
    # Lo-fi, Slowed & Sped up
    "lofi", "lo-fi", "slowed", "slowed + reverb", "slowed down", "reverb",
    "chillhop", "nightcore", "daycore", "sped up", "speed up",
    
    # Covers & Non-original versions
    "cover", "reprise", "female version", "male version", "karaoke", "reply",
    "status", "ringtone", "dholki", "8d", "tribute", "parody",
    "originally performed", "originally by", "backing track", "backing",
    "amateur", "re-recorded", "tribute to", "bgm", "theme music",
    "rework", "re-work", "private school", "remake", "rendition", "adaptation",
    "sound tower", "cover version", "different version", "different", "another version",
    "arz kiya", "spoof", "mimicry", "short version", "reaction", "version",
]


def score_candidate(
    title: str,
    subtitle_or_author: str,
    query: str,
    views: int = 0,
    duration: int = 0,
) -> float:
    """
    Score candidate song match to prioritize the original official version.
    Uses fuzzy token matching to handle transliteration variants (e.g. kesariya/kesariyaa).
    Penalties are calibrated to avoid discarding legitimate official songs.
    """
    c_title = (title or "").lower()
    c_author = (subtitle_or_author or "").lower()
    q_lower = query.lower()
    q_words = set(re.findall(r"\w+", q_lower))

    user_requested = {
        kw for kw in UNWANTED_VERSION_KEYWORDS
        if kw in q_lower or any(part in q_words for part in kw.split())
    }

    score = 0.0
    q_tokens = [w for w in re.findall(r"\w+", q_lower) if len(w) > 1]
    title_tokens = [w for w in re.findall(r"\w+", c_title) if len(w) > 1]

    def _fuzzy_match(tok: str, tokens: list) -> bool:
        """Check for exact or near-transliteration match (±2 chars, substring)."""
        if tok in tokens:
            return True
        # Handles "kesariya" vs "kesariyaa", "arijit" vs "arijite" etc.
        return any(
            (tok in t or t in tok) and abs(len(tok) - len(t)) <= 2
            for t in tokens
        )

    # Ensure the candidate's TITLE has substantive overlap with the query
    substantive_q_tokens = {
        w for w in q_tokens
        if w not in {"8d", "3d", "audio", "song", "music", "video", "official", "use", "headphones", "sound"}
    }
    title_matched = sum(1 for tok in substantive_q_tokens if _fuzzy_match(tok, title_tokens))
    if substantive_q_tokens and not title_matched:
        # Candidate has ZERO matching substantive title words: immediately disqualify
        return -500.0

    matched = sum(1 for tok in q_tokens if _fuzzy_match(tok, title_tokens) or tok in c_author)
    if q_tokens:
        score += (matched / len(q_tokens)) * 60.0

    # Check for unwanted bracket keywords (e.g. '(Different Version)', '(Cover)', '(Acoustic)')
    bracket_content = " ".join(re.findall(r"[\(\[\{]([^\)\]\}]+)[\)\]\}]", c_title)).lower()
    has_unwanted_bracket = any(kw in bracket_content for kw in UNWANTED_VERSION_KEYWORDS if kw not in user_requested)

    clean_c_title = re.sub(r"\(.*?\)|\[.*?\]", "", c_title).strip()
    clean_title_matches = bool(clean_c_title and (q_lower == clean_c_title or clean_c_title in q_lower or q_lower.startswith(clean_c_title)))
    if clean_title_matches and not has_unwanted_bracket:
        score += 45.0

    # Penalize if query had explicit artist/author tokens not in candidate title that don't match candidate author
    extra_tokens = [tok for tok in substantive_q_tokens if not _fuzzy_match(tok, title_tokens)]
    if len(extra_tokens) >= 2:
        author_tokens = re.findall(r"\w{3,}", c_author.lower())
        author_matched = sum(1 for tok in extra_tokens if _fuzzy_match(tok, author_tokens))
        if author_matched == 0:
            score -= 85.0

    # Ensure candidate core title has at least one substantive token present in query (prevents unrelated songs by same artist)
    core_words = [w for w in re.findall(r"\w{3,}", clean_c_title) if w not in {"from", "ost", "song", "audio", "video"}]
    query_substantive = [w for w in re.findall(r"\w{3,}", q_lower) if w not in {"from", "ost", "song", "audio", "video", "official"}]
    if core_words and query_substantive:
        overlap = [w for w in core_words if any(_fuzzy_match(w, [qw]) for qw in query_substantive)]
        if not overlap:
            score -= 100.0

    # Boost official artist topic tracks and original audio
    if " - topic" in c_author or "topic" in c_author:
        score += 40.0
    if "official audio" in c_title or "official music video" in c_title or "original track" in c_title:
        score += 30.0

    # Penalize unwanted modifier keywords using exact word boundaries
    for kw in UNWANTED_VERSION_KEYWORDS:
        if kw in user_requested or any(part in user_requested for part in kw.split()):
            continue

        pattern = rf"\b{re.escape(kw)}\b"
        if re.search(pattern, c_title) or re.search(pattern, c_author):
            # Heavily penalize unrequested alternate versions/covers/parodies so official songs win
            score -= 250.0
            break

    if views > 10_000_000:
        score += 40.0
    elif views > 1_000_000:
        score += 20.0

    # Standard song length is 120s - 600s; penalize short snippets (< 120s)
    if 120 <= duration <= 600:
        score += 15.0
    elif 0 < duration < 120:
        score -= 50.0
    elif duration > 1800:
        score -= 100.0

    return score



# In-memory search cache with 10-minute TTL for instant repeat queries
_SEARCH_CACHE: Dict[str, Tuple[float, Track]] = {}
_CACHE_TTL = 600.0  # 10 minutes

# Fast cache for canonical search query resolutions (1 hour TTL)
_CANONICAL_CACHE: Dict[str, Tuple[float, str]] = {}
_CANONICAL_CACHE_TTL = 3600.0  # 1 hour


def normalize_unicode_text(text: str) -> str:
    r"""
    Normalize styled, mathematical, or script Unicode characters into standard plain letters,
    and strip emojis/variation selectors safely without erasing stylized alphanumeric words.
    """
    if not text:
        return ""
    # nFKD converts mathematical bold/italic/sans/serif/fullwidth into plain letters & numbers
    norm = unicodedata.normalize("NFKD", text)
    # remove variation selectors & zero-width characters
    norm = re.sub(r"[\ufe00-\ufe0f\u200b-\u200d]", "", norm)
    # remove non-BMP characters (emojis and extra planes)
    norm = re.sub(r"[\U00010000-\U0010ffff]", " ", norm)
    # remove standard symbols (dingbats, misc symbols, enclosed characters)
    norm = re.sub(r"[\u2600-\u27bf\u2300-\u23ff\u2b50-\u2b55]", " ", norm)
    return norm


def clean_track_title(raw_title: str) -> str:
    """Clean raw track title for presentation."""
    if not raw_title:
        return ""
    clean = html.unescape(raw_title).strip()
    clean = normalize_unicode_text(clean)
    clean = AUDIO_FORMAT_PREFIX_PATTERN.sub("", clean).strip()
    clean = AUDIO_FORMAT_TAGS.sub("", clean).strip()
    clean = re.sub(r"\.mp3$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"[\(\[\{][a-zA-Z0-9\-_]+\.(?:in|com|net|org|co|pk|cc)[\)\]\}]", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"[-–]\s*\d+\s*kbps.*$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\b\d+\s*kbps\b", "", clean, flags=re.IGNORECASE)
    clean = re.sub(
        r"[\(\[\{]\s*(?:official\s+video|official\s+audio|lyrics?|full\s+song|hd|4k|1080p|audio|video|prod\..*?|dir\..*?|use\s+headphones?)[\)\]\}]",
        "",
        clean,
        flags=re.IGNORECASE,
    )
    clean = re.sub(r"^[\s\-:|~•]+|[\s\-:|~•]+$", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def parse_and_clean_query(raw_query: str) -> str:
    r"""
    Smart Universal Query Normalizer.
    Reads the full title without cutting or truncating:
    - Neutralizes symbols (| , / , \ , - , _ , ~ , • , : , () , [] , {}) to spaces
    - Strips non-music noise (viewing instructions, emojis, audio formats)
    - Retains full song name, primary artist, and featured artists intact
    """
    cleaned = html.unescape(raw_query).strip()
    cleaned = normalize_unicode_text(cleaned)

    # Strip conversational commands from start/end only
    cleaned = CONVERSATIONAL_PREFIX_PATTERN.sub("", cleaned)
    cleaned = CONVERSATIONAL_SUFFIX_PATTERN.sub("", cleaned)

    # Strip audio format prefixes (like '8D Audio -', '[8D AUDIO]', '8D Song')
    cleaned = AUDIO_FORMAT_PREFIX_PATTERN.sub("", cleaned).strip()
    cleaned = AUDIO_FORMAT_TAGS.sub("", cleaned).strip()
    cleaned = re.sub(r"[\(\[\{]\s*(?:8d|3d|16d|use\s+headphones?|slowed|reverb)[\)\]\}]", " ", cleaned, flags=re.IGNORECASE)

    # Normalize collaboration keywords like 'with', 'feat.', 'ft.'
    cleaned = re.sub(r"\b(?:with|feat\.?|ft\.?)\b", " ", cleaned, flags=re.IGNORECASE)

    # Convert all punctuation and delimiters (| , / , \ , - , _ , ~ , • , : , ; , () , [] , {}) to spaces
    # so NO symbol breaks the query and the full song title is read cleanly without confusion
    cleaned = re.sub(r"[|/\\_~•:;!@#$%^&*()\[\]{}<>+=?\"'`]", " ", cleaned)

    # Strip generic metadata noise (e.g. 'official video', '4k', 'full song', etc.)
    core = METADATA_NOISE_PATTERN.sub(" ", cleaned)
    core_lower = core.lower()

    # Apply phonetic typo corrections
    for typo, correction in PHONETIC_TYPO_MAP.items():
        if typo in core_lower:
            core = re.sub(rf"\b{re.escape(typo)}\b", correction, core, flags=re.IGNORECASE)

    # Clean leftover delimiters at edges
    core = re.sub(r"^[\s\-:|~•]+|[\s\-:|~•]+$", "", core)
    core = re.sub(r"\s+", " ", core).strip()
    return core if core else cleaned


def is_playlist_url(raw_url: str) -> bool:
    """Detect if a query/url is an external playlist or album link."""
    if not raw_url or not isinstance(raw_url, str):
        return False
    u = raw_url.strip()
    if u.startswith("<") and u.endswith(">"):
        u = u[1:-1].strip()
    u_low = u.lower()

    # Spotify short links (mobile share links like spotify.link, spotify.app.link, spoti.fi)
    if any(sp in u_low for sp in ("spotify.link/", "spotify.app.link/", "spoti.fi/")):
        return True

    # YouTube Playlists (only pure playlists without specific video target 'v=')
    if any(yt in u_low for yt in ("youtube.com/", "youtu.be/", "music.youtube.com/")):
        if "/playlist" in u_low:
            return True
        if "list=" in u_low and "v=" not in u_low:
            return True

    # Spotify Playlists & Albums
    if any(sp in u_low for sp in ("spotify.com/", "spotify.link/")):
        if any(sec in u_low for sec in ("/playlist/", "/album/")):
            return True

    # SoundCloud Sets
    if "soundcloud.com/" in u_low and "/sets/" in u_low:
        return True

    return False


class NativeExtractor:
    """Multi-Tier Cloud Unblocked Music Search Engine & Stream Extractor."""

    @classmethod
    async def extract(
        cls,
        query: str,
        requester: str = "DJ / AutoPlay",
        is_autoplay: bool = False,
    ) -> Optional[Track]:
        """Extract a playable Track from query or URL using Lavalink YouTube/YouTubeMusic resolution."""
        raw_q = query.strip()
        if not raw_q:
            return None

        # Strip Discord URL angle brackets if present
        if raw_q.startswith("<") and raw_q.endswith(">"):
            raw_q = raw_q[1:-1].strip()

        # check in-memory search cache for instant playback
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
                    query=cached_track.query,
                )

        import wavelink

        # direct YouTube URL Handling
        yt_match = YOUTUBE_URL_REGEX.search(raw_q)
        orig_yt_url = None
        if yt_match:
            video_id = yt_match.group(1)
            orig_yt_url = f"https://www.youtube.com/watch?v={video_id}"
            try:
                results = await asyncio.wait_for(wavelink.Playable.search(orig_yt_url), timeout=8.0)
                if results:
                    top = results[0] if isinstance(results, list) else results.tracks[0]
                    thumb = top.artwork or (f"https://i.ytimg.com/vi/{top.identifier}/hqdefault.jpg" if getattr(top, "identifier", None) else None)
                    trk = Track(
                        title=top.title or "Unknown Track",
                        author=top.author or "Unknown Artist",
                        url=orig_yt_url,
                        stream_url="",
                        duration=int((top.length or 0) / 1000),
                        thumbnail=thumb,
                        requester=requester,
                        is_autoplay=is_autoplay,
                        query=raw_q,
                    )
                    trk._playable = top
                    _SEARCH_CACHE[cache_key] = (now, trk)
                    return trk
            except Exception as e:
                logger.debug(f"Direct YouTube URL resolution notice: {e}")

        # Spotify URL Handling (Extract '{Title} {Artist}' metadata to bridge to YouTube)
        is_spotify = any(sp in raw_q for sp in ("spotify.com/", "spotify.link/", "spotify:track:", "spotify.app.link/", "spoti.fi/"))
        orig_spotify_url = None
        search_target = raw_q

        if is_spotify:
            sp_url = raw_q
            if sp_url.startswith("spotify:track:"):
                sp_url = f"https://open.spotify.com/track/{sp_url.split(':')[-1]}"
            orig_spotify_url = sp_url
            try:
                spotify_title = await asyncio.wait_for(cls._fetch_spotify_title(sp_url), timeout=6.0)
                if spotify_title:
                    search_target = spotify_title
            except Exception as e:
                logger.debug(f"Spotify metadata fetch notice: {e}")

        # Smart canonical query discovery: for bare search terms without known artists or URLs,
        # resolve the official track & primary artist from YouTube public index in ~0.2s.
        is_direct_url = bool(orig_yt_url or is_spotify or raw_q.startswith(("http://", "https://")))
        if not is_direct_url:
            canonical_q = await cls._resolve_canonical_query(raw_q)
            if canonical_q and canonical_q.lower() != raw_q.lower():
                search_target = canonical_q

        cleaned_query = parse_and_clean_query(search_target)

        # Priority 1: YouTube Music search via Lavalink (Official release priority)
        try:
            results = await asyncio.wait_for(
                wavelink.Playable.search(cleaned_query, source=wavelink.TrackSource.YouTubeMusic),
                timeout=8.0,
            )
            if results:
                top = results[0] if isinstance(results, list) else results.tracks[0]
                thumb = top.artwork or (f"https://i.ytimg.com/vi/{top.identifier}/hqdefault.jpg" if getattr(top, "identifier", None) else None)
                trk = Track(
                    title=top.title or cleaned_query,
                    author=top.author or "Artist",
                    url=orig_spotify_url or top.uri or orig_yt_url or raw_q,
                    stream_url="",
                    duration=int((top.length or 0) / 1000),
                    thumbnail=thumb,
                    requester=requester,
                    is_autoplay=is_autoplay,
                    query=raw_q,
                )
                trk._playable = top
                _SEARCH_CACHE[cache_key] = (now, trk)
                return trk
        except Exception as e:
            logger.debug(f"YouTube Music search notice: {e}")

        # Priority 2: Standard YouTube search via Lavalink
        try:
            results = await asyncio.wait_for(
                wavelink.Playable.search(cleaned_query, source=wavelink.TrackSource.YouTube),
                timeout=8.0,
            )
            if results:
                top = results[0] if isinstance(results, list) else results.tracks[0]
                thumb = top.artwork or (f"https://i.ytimg.com/vi/{top.identifier}/hqdefault.jpg" if getattr(top, "identifier", None) else None)
                trk = Track(
                    title=top.title or cleaned_query,
                    author=top.author or "Artist",
                    url=orig_spotify_url or top.uri or orig_yt_url or raw_q,
                    stream_url="",
                    duration=int((top.length or 0) / 1000),
                    thumbnail=thumb,
                    requester=requester,
                    is_autoplay=is_autoplay,
                    query=raw_q,
                )
                trk._playable = top
                _SEARCH_CACHE[cache_key] = (now, trk)
                return trk
        except Exception as e:
            logger.debug(f"YouTube fallback search notice: {e}")

        # Priority 3: Raw query fallback if cleaned was different
        if search_target.lower() != cleaned_query.lower():
            try:
                results = await asyncio.wait_for(
                    wavelink.Playable.search(search_target, source=wavelink.TrackSource.YouTube),
                    timeout=8.0,
                )
                if results:
                    top = results[0] if isinstance(results, list) else results.tracks[0]
                    thumb = top.artwork or (f"https://i.ytimg.com/vi/{top.identifier}/hqdefault.jpg" if getattr(top, "identifier", None) else None)
                    trk = Track(
                        title=top.title or search_target,
                        author=top.author or "Artist",
                        url=orig_spotify_url or top.uri or orig_yt_url or raw_q,
                        stream_url="",
                        duration=int((top.length or 0) / 1000),
                        thumbnail=thumb,
                        requester=requester,
                        is_autoplay=is_autoplay,
                        query=raw_q,
                    )
                    trk._playable = top
                    _SEARCH_CACHE[cache_key] = (now, trk)
                    return trk
            except Exception as e:
                logger.debug(f"Raw query fallback notice: {e}")

        return None


    @classmethod
    def _build_saavn_track(
        cls,
        song: Dict[str, Any],
        requester: str,
        is_autoplay: bool,
        query: str,
    ) -> Optional[Track]:
        """Convert a JioSaavn song payload to a playable Track."""
        more_info = song.get("more_info", {})
        has_320 = str(more_info.get("320kbps", "")).lower() == "true"
        enc_url = more_info.get("encrypted_media_url")
        if not enc_url:
            return None
        dec_stream = cls._decrypt_saavn_url(enc_url, has_320kbps=has_320)
        if not dec_stream:
            return None

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

    @classmethod
    async def _extract_jiosaavn(
        cls,
        query: str,
        requester: str,
        is_autoplay: bool,
    ) -> Optional[Track]:
        """Fetch and decrypt 320kbps stream URL from JioSaavn official catalog cascade."""
        if not query:
            return None

        encoded_q = urllib.parse.quote(query)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
            "X-Forwarded-For": "103.240.233.1",
            "CF-Connecting-IP": "103.240.233.1",
            "Client-IP": "103.240.233.1",
            "Cookie": "geo=IN; cc=in; L=hindi%2Cenglish",
        }

        try:
            async with aiohttp.ClientSession() as session:
                # ── Step 1: Autocomplete Popularity Index (Always Official Releases First!) ──
                auto_url = (
                    f"https://www.jiosaavn.com/api.php?"
                    f"__call=autocomplete.get&_format=json&_marker=0&cc=in&includeMetaTags=1&query={encoded_q}"
                )
                async with session.get(auto_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp1:
                    if resp1.status == 200:
                        data1 = await resp1.json(content_type=None)
                        songs1 = data1.get("songs", {}).get("data", [])
                        if songs1:
                            scored1 = []
                            for s in songs1:
                                s_dur = int(s.get("duration") or s.get("more_info", {}).get("duration") or 0)
                                sc = score_candidate(s.get("title") or "", s.get("description") or "", query, duration=s_dur)
                                scored1.append((sc, s))

                            scored1.sort(key=lambda x: x[0], reverse=True)
                            has_user_keyword = any(kw in query.lower() for kw in UNWANTED_VERSION_KEYWORDS)

                            for sc, cand in scored1:
                                if sc < 0 and not has_user_keyword:
                                    continue
                                pid = cand.get("id")
                                if not pid:
                                    continue
                                det_url = (
                                    f"https://www.jiosaavn.com/api.php?"
                                    f"__call=song.getDetails&cc=in&_marker=0%3F_marker%3D0&_format=json&pids={pid}"
                                )
                                async with session.get(det_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as det_resp:
                                    if det_resp.status == 200:
                                        det_data = await det_resp.json(content_type=None)
                                        sinfo = det_data.get(pid, {})
                                        enc_url = sinfo.get("encrypted_media_url")
                                        if enc_url:
                                            has_320 = str(sinfo.get("320kbps", "")).lower() == "true"
                                            dec_stream = cls._decrypt_saavn_url(enc_url, has_320kbps=has_320)
                                            if dec_stream:
                                                title = clean_track_title(sinfo.get("song") or cand.get("title") or query)
                                                author = sinfo.get("primary_artists") or cand.get("description") or "Official Artist"
                                                raw_image = sinfo.get("image") or cand.get("image") or ""
                                                thumbnail = (
                                                    raw_image.replace("150x150", "500x500").replace("50x50", "500x500")
                                                    if raw_image
                                                    else "https://cdn.discordapp.com/embed/avatars/0.png"
                                                )
                                                duration = int(sinfo.get("duration") or 0)
                                                webpage = sinfo.get("perma_url") or cand.get("url") or "https://www.jiosaavn.com"

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

                # ── Step 2: Detailed Catalog Search (15 candidates with Indian geo) ──
                search_url = (
                    f"https://www.jiosaavn.com/api.php?"
                    f"__call=search.getResults&_format=json&p=1&n=15&q={encoded_q}"
                    f"&_marker=0&api_version=4&ctx=web6dot0&cc=in"
                )
                async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as s_resp:
                    if s_resp.status == 200:
                        s_data = await s_resp.json(content_type=None)
                        results = s_data.get("results", [])
                        if results:
                            scored_res = []
                            for song in results:
                                s_title = song.get("title") or song.get("song") or ""
                                s_sub = song.get("subtitle") or ""
                                m_info = song.get("more_info", {})
                                dur = int(m_info.get("duration") or song.get("duration") or 0)
                                sc = score_candidate(s_title, s_sub, query, duration=dur)
                                scored_res.append((sc, song))

                            scored_res.sort(key=lambda x: x[0], reverse=True)
                            has_user_keyword = any(kw in query.lower() for kw in UNWANTED_VERSION_KEYWORDS)

                            for sc, song in scored_res:
                                if sc < 0 and not has_user_keyword:
                                    continue
                                trk = cls._build_saavn_track(song, requester, is_autoplay, query)
                                if trk:
                                    return trk
        except Exception as e:
            logger.debug(f"JioSaavn search notice for '{query}': {e}")

        # Step 3: Relaxed modifier fallback ONLY if user did not specify explicit version keywords
        has_user_keyword = any(kw in query.lower() for kw in UNWANTED_VERSION_KEYWORDS)
        if not has_user_keyword:
            relaxed = re.sub(
                r"\b(?:8d(?:\s*audio)?|3d(?:\s*audio)?|16d|spatial\s*audio|lofi|lo-fi|slowed(?:\s*\+\s*reverb)?|reverb|mashup|sad|status|version|acoustic|unplugged|bass boosted|dholki mix|remix|full song|song|track|use headphones?)\b",
                "",
                query,
                flags=re.IGNORECASE,
            )
            relaxed = re.sub(r"\s+", " ", relaxed).strip()
            if relaxed and relaxed.lower() != query.lower():
                relaxed_track = await cls._extract_jiosaavn(relaxed, requester, is_autoplay)
                if relaxed_track:
                    return relaxed_track

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

    _SC_CLIENT_ID: Optional[str] = "pJaCCaoD8RMOSFmlbrbYQuyvkjP1fiES"
    _SC_CID_EXPIRE: float = 0.0

    @classmethod
    def invalidate_sc_client_id(cls, dead_id: Optional[str] = None) -> None:
        """Immediately invalidate dead SoundCloud Client ID and trigger refresh."""
        if dead_id is None or cls._SC_CLIENT_ID == dead_id:
            cls._SC_CLIENT_ID = None
            cls._SC_CID_EXPIRE = 0.0

    @classmethod
    async def _get_sc_client_id(cls, session: aiohttp.ClientSession, force: bool = False) -> str:
        """Fetch or refresh dynamic SoundCloud Client ID using reversed asset bundle inspection."""
        now = time.time()
        if not force and cls._SC_CLIENT_ID and now < cls._SC_CID_EXPIRE:
            return cls._SC_CLIENT_ID

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        }
        try:
            async with session.get("https://soundcloud.com", headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    script_urls = re.findall(r'<script[^>]+src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"', text)
                    # Check scripts in reverse order (asset bundles with client_id are always at the end)
                    for s_url in reversed(script_urls[-5:]):
                        try:
                            async with session.get(s_url, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as s_resp:
                                if s_resp.status == 200:
                                    s_text = await s_resp.text()
                                    m = re.search(r'client_id[:=]"?([a-zA-Z0-9]{32})"?', s_text)
                                    if m:
                                        cls._SC_CLIENT_ID = m.group(1)
                                        cls._SC_CID_EXPIRE = now + 86400.0
                                        return cls._SC_CLIENT_ID
                        except Exception:
                            continue
        except Exception:
            pass

        # Valid active fallback ID pool
        cls._SC_CLIENT_ID = "pJaCCaoD8RMOSFmlbrbYQuyvkjP1fiES"
        cls._SC_CID_EXPIRE = now + 3600.0
        return cls._SC_CLIENT_ID

    @classmethod
    async def _extract_soundcloud(
        cls,
        query: str,
        requester: str,
        is_autoplay: bool,
    ) -> Optional[Track]:
        """Search and extract direct audio stream from SoundCloud Worldwide catalog with multi-candidate resilience."""
        if not query:
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
        }

        try:
            async with aiohttp.ClientSession() as session:
                for attempt in range(2):
                    cid = await cls._get_sc_client_id(session, force=(attempt > 0))
                    encoded_q = urllib.parse.quote(query)

                    candidates_to_try = []
                    if "soundcloud.com/" in query:
                        resolve_url = f"https://api-v2.soundcloud.com/resolve?url={encoded_q}&client_id={cid}"
                        async with session.get(resolve_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            if resp.status == 401:
                                cls.invalidate_sc_client_id(cid)
                                continue
                            if resp.status == 200:
                                data = await resp.json()
                                if data.get("media"):
                                    candidates_to_try = [data]
                    else:
                        search_url = f"https://api-v2.soundcloud.com/search/tracks?q={encoded_q}&client_id={cid}&limit=10"
                        async with session.get(search_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                            if resp.status == 401:
                                cls.invalidate_sc_client_id(cid)
                                continue
                            if resp.status != 200:
                                return None
                            data = await resp.json()
                            collection = data.get("collection", [])
                            if not collection:
                                return None

                            scored = []
                            for it in collection:
                                it_title = it.get("title") or ""
                                it_user = it.get("user", {}).get("username") or ""
                                it_dur = int((it.get("duration") or 0) / 1000)
                                sc = score_candidate(it_title, it_user, query, duration=it_dur)
                                scored.append((sc, it))

                            scored.sort(key=lambda x: x[0], reverse=True)
                            has_user_keyword = any(kw in query.lower() for kw in UNWANTED_VERSION_KEYWORDS)

                            for sc, candidate in scored:
                                if sc < 0 and not has_user_keyword:
                                    continue
                                candidates_to_try.append(candidate)

                            # If all were filtered out, still try the raw collection
                            if not candidates_to_try:
                                candidates_to_try = collection[:3]

                    # Loop through top candidates to extract a valid playable stream
                    for item in candidates_to_try[:4]:
                        raw_item_title = item.get("title") or query
                        title = clean_track_title(raw_item_title)
                        author = item.get("user", {}).get("username") or "SoundCloud Artist"
                        duration = int((item.get("duration") or 0) / 1000)

                        # Skip 30-second preview snippets (SoundCloud Go+ previews) if a longer track might exist
                        if duration <= 35 and len(candidates_to_try) > 1 and duration > 0:
                            # Check if next candidates have normal duration
                            longer_exists = any(int((c.get("duration") or 0)/1000) > 45 for c in candidates_to_try)
                            if longer_exists:
                                continue

                        thumbnail = item.get("artwork_url") or item.get("user", {}).get("avatar_url") or "https://cdn.discordapp.com/embed/avatars/0.png"
                        thumbnail = thumbnail.replace("-large", "-t500x500")
                        permalink = item.get("permalink_url") or "https://soundcloud.com"

                        media = item.get("media", {}).get("transcodings", [])
                        # Prioritize progressive, then HLS
                        sorted_transcodings = sorted(
                            media,
                            key=lambda x: 0 if x.get("format", {}).get("protocol") == "progressive" else 1
                        )

                        for t in sorted_transcodings:
                            ep = t.get("url")
                            if not ep:
                                continue
                            try:
                                async with session.get(f"{ep}?client_id={cid}", headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as s_resp:
                                    if s_resp.status == 401:
                                        cls.invalidate_sc_client_id(cid)
                                        break
                                    if s_resp.status == 200:
                                        s_data = await s_resp.json()
                                        final_stream_url = s_data.get("url")
                                        if final_stream_url:
                                            return Track(
                                                title=title,
                                                author=author,
                                                url=permalink,
                                                stream_url=final_stream_url,
                                                duration=duration,
                                                thumbnail=thumbnail,
                                                requester=requester,
                                                is_autoplay=is_autoplay,
                                            )
                            except Exception:
                                continue

        except Exception as e:
            logger.debug("SoundCloud extract notice for '%s': %s", query, e)

        return None

    @classmethod
    def _extract_youtube_fallback(
        cls,
        raw_query: str,
        requester: str,
        is_autoplay: bool,
    ) -> Optional[Track]:
        """YouTube search fallback with smart candidate ranking and anti-remix filter."""
        yt_match = YOUTUBE_URL_REGEX.search(raw_query)
        if yt_match:
            video_id = yt_match.group(1)
            target_url = f"https://www.youtube.com/watch?v={video_id}"
            entry = cls._sync_yt_dlp_extract(target_url)
        elif raw_query.startswith(("http://", "https://")):
            entry = cls._sync_yt_dlp_extract(raw_query)
        else:
            entry = cls._sync_yt_dlp_smart_search(raw_query)

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

    @classmethod
    def _sync_yt_dlp_smart_search(cls, query: str) -> Optional[Dict[str, Any]]:
        """Search top 5 YouTube entries, score them to avoid remixes/lofi, and extract the winning stream."""
        ydl_flat = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": True,
            "ignoreerrors": True,
            "socket_timeout": 6,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"],
                }
            },
        }
        with yt_dlp.YoutubeDL(ydl_flat) as ydl:
            try:
                res = ydl.extract_info(f"ytsearch8:{query}", download=False)
                entries = (res.get("entries") or []) if res else []
                scored = []
                for e in entries:
                    if not e:
                        continue
                    sc = score_candidate(
                        e.get("title") or "",
                        e.get("uploader") or "",
                        query,
                        views=int(e.get("view_count") or 0),
                        duration=int(e.get("duration") or 0),
                    )
                    scored.append((sc, e))

                if not scored:
                    return None

                scored.sort(key=lambda x: x[0], reverse=True)
                has_user_keyword = any(kw in query.lower() for kw in UNWANTED_VERSION_KEYWORDS)

                winner = None
                for sc, e in scored:
                    if sc < 0 and not has_user_keyword:
                        continue
                    winner = e
                    break

                if not winner:
                    return None

                candidates_to_try = [winner] + [c[1] for c in scored if c[1] != winner and (c[0] >= 0 or has_user_keyword)][:2]
                for cand in candidates_to_try:
                    vid_id = cand.get("id")
                    cand_url = cand.get("url") or (f"https://www.youtube.com/watch?v={vid_id}" if vid_id else None)
                    if cand_url:
                        ext = cls._sync_yt_dlp_extract(cand_url)
                        if ext and ext.get("url"):
                            return ext

                return None
            except Exception as e:
                logger.debug(f"YouTube smart search notice for '{query}': {e}")
                return None

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

    _SPOTIFY_TOKEN: Optional[str] = None
    _SPOTIFY_TOKEN_EXPIRES: float = 0.0

    @classmethod
    async def _get_spotify_token(cls, session: aiohttp.ClientSession) -> Optional[str]:
        """Obtain or refresh an official Spotify Web API OAuth token using Client Credentials."""
        cid = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
        secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
        if not cid or not secret:
            return None

        now = time.time()
        if cls._SPOTIFY_TOKEN and now < cls._SPOTIFY_TOKEN_EXPIRES - 60:
            return cls._SPOTIFY_TOKEN

        auth_str = f"{cid}:{secret}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        headers = {
            "Authorization": f"Basic {b64_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {"grant_type": "client_credentials"}
        try:
            async with session.post(
                "https://accounts.spotify.com/api/token",
                headers=headers,
                data=data,
                timeout=aiohttp.ClientTimeout(total=6),
            ) as resp:
                if resp.status == 200:
                    payload = await resp.json()
                    cls._SPOTIFY_TOKEN = payload.get("access_token")
                    cls._SPOTIFY_TOKEN_EXPIRES = now + float(payload.get("expires_in", 3600))
                    return cls._SPOTIFY_TOKEN
        except Exception as e:
            logger.debug(f"Spotify token request error: {e}")
        return None

    @classmethod
    async def _fetch_spotify_title(cls, spotify_url: str) -> Optional[str]:
        """
        Extract track title and artist name from Spotify track URL.
        Uses official Spotify Web API if SPOTIFY_CLIENT_ID & SECRET configured in .env,
        with HTML scraper and oEmbed fallback.
        """
        # Follow short spotify.link redirects to canonical open.spotify.com URL
        if "spotify.link/" in spotify_url:
            try:
                async with aiohttp.ClientSession() as s_link:
                    async with s_link.get(spotify_url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=6)) as r_link:
                        spotify_url = str(r_link.url)
            except Exception:
                pass

        track_m = re.search(r"spotify\.com/(?:intl-[a-zA-Z\-]+/)?track/([a-zA-Z0-9]+)", spotify_url)

        try:
            async with aiohttp.ClientSession() as session:
                # Tier 0: Official Spotify Web API (Ultra-fast, 100% accurate)
                if track_m:
                    sp_token = await cls._get_spotify_token(session)
                    if sp_token:
                        sp_api_url = f"https://api.spotify.com/v1/tracks/{track_m.group(1)}"
                        sp_headers = {"Authorization": f"Bearer {sp_token}"}
                        async with session.get(sp_api_url, headers=sp_headers, timeout=aiohttp.ClientTimeout(total=5)) as sp_resp:
                            if sp_resp.status == 200:
                                sp_data = await sp_resp.json()
                                t_name = sp_data.get("name") or ""
                                artists = ", ".join(a.get("name", "") for a in sp_data.get("artists", []) if a.get("name"))
                                if t_name and artists:
                                    return normalize_unicode_text(f"{t_name} {artists}")
                                elif t_name:
                                    return normalize_unicode_text(t_name)

                # Primary Fallback: Scrape Spotify HTML using Discordbot UA for full Title + Artist
                headers = {
                    "User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discordapp.com)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                }
                async with session.get(
                    spotify_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5),
                    allow_redirects=True,
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()

                        # Pattern 1: <title>Title - song and lyrics by Artist | Spotify</title>
                        t_match = re.search(
                            r"<title>(.*?)\s*-\s*song (?:and|&amp;|&) lyrics by (.*?)\s*\|\s*Spotify</title>",
                            text,
                            re.IGNORECASE,
                        )
                        if t_match:
                            song_title = html.unescape(t_match.group(1)).strip()
                            song_artist = html.unescape(t_match.group(2)).strip()
                            if song_title and song_artist:
                                return normalize_unicode_text(f"{song_title} {song_artist}")

                        # Pattern 2: OpenGraph tags
                        og_title_m = re.search(r'<meta property="og:title" content="(.*?)"', text)
                        og_desc_m = re.search(r'<meta property="og:description" content="(.*?)"', text)
                        if og_title_m:
                            song_title = html.unescape(og_title_m.group(1)).strip()
                            song_artist = ""
                            if og_desc_m:
                                desc = html.unescape(og_desc_m.group(1)).strip()
                                parts = [p.strip() for p in re.split(r"[·•\-]", desc) if p.strip()]
                                if parts:
                                    song_artist = parts[0]
                            if song_title and song_artist and "spotify" not in song_artist.lower():
                                return normalize_unicode_text(f"{song_title} {song_artist}")
                            elif song_title and "spotify" not in song_title.lower():
                                return normalize_unicode_text(song_title)

                # Secondary Fallback: Spotify oEmbed API
                oembed_url = f"https://open.spotify.com/oembed?url={spotify_url}"
                async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=4)) as o_resp:
                    if o_resp.status == 200:
                        text = await o_resp.text()
                        data = json.loads(text)
                        title = data.get("title", "")
                        return normalize_unicode_text(title.strip()) if title else None
        except Exception as e:
            logger.debug(f"Spotify metadata fetch error: {e}")
        return None

    @staticmethod
    def _parse_youtube_title(raw_title: str) -> str:
        """
        Intelligently parse YouTube video titles (especially Indian label titles)
        formatted like:
        'Tum Se Hi - Lyrical Video | Ankit Tiwari | Alia Bhatt | Adity Roy Kapur | Sanjay Dutt | Sadak 2'
        Extracts the clean song name and the primary singer/artist into an optimal search query.
        """
        if not raw_title:
            return ""
        clean = normalize_unicode_text(html.unescape(raw_title)).strip()
        chunks = [c.strip() for c in re.split(r"[|•]", clean) if c.strip()]
        if len(chunks) > 1:
            c0 = METADATA_NOISE_PATTERN.sub("", chunks[0])
            c0 = re.sub(r"[\(\[\{].*?[\)\]\}]", "", c0)
            c0 = re.sub(r"[\s\-:~]+$", "", c0).strip()

            chosen_artist = ""
            for c in chunks[1:]:
                c_clean = METADATA_NOISE_PATTERN.sub("", c).strip()
                c_clean = re.sub(r"[\(\[\{].*?[\)\]\}]", "", c_clean).strip()
                low = c_clean.lower()
                if not c_clean or any(tag in low for tag in [
                    "official", "video", "audio", "lyric", "gaana", "sony", "t-series",
                    "times music", "zeemusic", "tips", "speed records", "record", "records"
                ]):
                    continue
                chosen_artist = c_clean
                break

            if chosen_artist:
                return f"{c0} {chosen_artist}".strip()
            return c0.strip()

        cleaned = METADATA_NOISE_PATTERN.sub("", clean)
        cleaned = re.sub(r"[\(\[\{].*?[\)\]\}]", "", cleaned)
        cleaned = re.sub(r"[\s\-:~]+$", "", cleaned).strip()
        return cleaned

    @classmethod
    async def _resolve_canonical_query(cls, query: str) -> str:
        """Safe query pass-through without destructive web scraping."""
        return query.strip() if query else ""

    @staticmethod
    async def _fetch_youtube_title(youtube_url: str) -> Optional[str]:
        """Extract title and artist metadata from YouTube URL without streaming chunk blocks."""
        # official YouTube oEmbed protocol (Super fast, 100% unblocked on Cloud/Render)
        try:
            oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(youtube_url)}&format=json"
            async with aiohttp.ClientSession() as session:
                async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        data = json.loads(text)
                        title = data.get("title") or ""
                        author = data.get("author_name") or ""
                        if title:
                            title = normalize_unicode_text(html.unescape(title))
                            if "- topic" in author.lower():
                                artist = re.sub(r"\s*-\s*Topic$", "", author, flags=re.IGNORECASE).strip()
                                if artist and artist.lower() not in title.lower():
                                    return f"{title.strip()} {artist}"
                            return title.strip()
        except Exception as e:
            logger.debug(f"YouTube oEmbed fetch error: {e}")

        # hTML scrape fallback for title tag
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(youtube_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        html_text = await resp.text()
                        m = re.search(r"<title>(.*?)</title>", html_text)
                        if m:
                            t = html.unescape(m.group(1))
                            t = re.sub(r"\s*-\s*YouTube$", "", t, flags=re.IGNORECASE).strip()
                            t = normalize_unicode_text(t)
                            if t:
                                return t
        except Exception as e:
            logger.debug(f"YouTube HTML scrape error: {e}")

        # fallback to flat yt-dlp extract
        try:
            def _get_title():
                opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "extract_flat": True,
                    "socket_timeout": 8,
                    "extractor_args": {"youtube": {"player_client": ["android", "ios"]}},
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(youtube_url, download=False)
                    if info:
                        raw_t = info.get("title")
                        return normalize_unicode_text(raw_t) if raw_t else None
                return None

            return await asyncio.to_thread(_get_title)
        except Exception as e:
            logger.debug(f"YouTube title extract error: {e}")
        return None

    @classmethod
    async def extract_playlist(
        cls,
        url: str,
        requester: str = "DJ / AutoPlay",
    ) -> Optional[PlaylistResult]:
        """Unified playlist extraction for Spotify, YouTube, and SoundCloud."""
        clean_u = url.strip()
        if clean_u.startswith("<") and clean_u.endswith(">"):
            clean_u = clean_u[1:-1].strip()

        # spotify Playlist or Album (Do not fallback to yt-dlp to avoid DRM errors)
        if "spotify.com/" in clean_u or "spotify.link/" in clean_u:
            return await cls._extract_spotify_playlist(clean_u, requester=requester)

        # youTube Playlist
        if any(d in clean_u for d in ("youtube.com/", "youtu.be/", "music.youtube.com/")):
            return await asyncio.to_thread(cls._sync_extract_youtube_playlist, clean_u, requester)

        # soundCloud / Generic Fallback via yt-dlp
        return await asyncio.to_thread(cls._sync_extract_youtube_playlist, clean_u, requester)

    @classmethod
    async def _extract_spotify_playlist(
        cls,
        url: str,
        requester: str = "DJ / AutoPlay",
    ) -> Optional[PlaylistResult]:
        """Extract all tracks from a Spotify playlist or album via embed data."""
        # Follow redirects for short spotify mobile share URLs (spotify.link, spotify.app.link, spoti.fi)
        if any(sp in url for sp in ("spotify.link/", "spotify.app.link/", "spoti.fi/")):
            try:
                hdr = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
                async with aiohttp.ClientSession(headers=hdr) as s:
                    async with s.get(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=6)) as r:
                        url = str(r.url)
            except Exception as e:
                logger.debug(f"Spotify short link redirect resolve notice: {e}")

        m = re.search(r"spotify\.com/(?:intl-[a-zA-Z\-]+/)?(playlist|album)/([a-zA-Z0-9]+)", url)
        if not m:
            return None
        entity_type, entity_id = m.group(1), m.group(2)
        embed_url = f"https://open.spotify.com/embed/{entity_type}/{entity_id}"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        # Tier 0: spotifyscraper (Universal public scraper - 0% rate limits, no Premium requirement)
        try:
            from spotify_scraper import SpotifyClient
            def _scrape_sync():
                with SpotifyClient() as client:
                    if entity_type == "album":
                        alb = client.get_album(url)
                        items = alb.tracks
                        t_name = alb.name
                        t_author = ", ".join(a.name for a in alb.artists)
                    else:
                        pl = client.get_playlist(url)
                        items = [it.track for it in pl.tracks]
                        t_name = pl.name
                        t_author = "Spotify"
                    res_tracks = []
                    for t in items:
                        t_title = t.name
                        t_art = ", ".join(a.name for a in t.artists) if hasattr(t, "artists") else ""
                        q_str = f"{t_title} {t_art}".strip() if t_art else t_title
                        res_tracks.append(PlaylistTrackItem(
                            title=t_title,
                            author=t_art or "Spotify Artist",
                            query=q_str,
                            duration=int(getattr(t, "duration_ms", 0) // 1000) if hasattr(t, "duration_ms") else 180,
                            url=getattr(t, "url", None),
                        ))
                    return t_name, t_author, res_tracks

            res = await asyncio.to_thread(_scrape_sync)
            if res and res[2]:
                pl_title, pl_author, tracks = res
                return PlaylistResult(
                    title=clean_track_title(pl_title),
                    author=pl_author,
                    url=url,
                    tracks=tracks,
                    thumbnail=None,
                    requester=requester,
                )
        except Exception as e:
            logger.debug(f"spotifyscraper extraction notice: {e}")

        try:
            html_text: Optional[str] = None
            async with aiohttp.ClientSession() as session:
                # Tier 0: Official Spotify Web API (Fastest, 100% accurate, no scraping blocks)
                sp_token = await cls._get_spotify_token(session)
                if sp_token:
                    sp_api_url = f"https://api.spotify.com/v1/{entity_type}s/{entity_id}"
                    sp_headers = {"Authorization": f"Bearer {sp_token}"}
                    async with session.get(sp_api_url, headers=sp_headers, timeout=aiohttp.ClientTimeout(total=8)) as sp_resp:
                        if sp_resp.status == 200:
                            sp_data = await sp_resp.json()
                            pl_title = sp_data.get("name") or "Spotify Playlist"
                            pl_author = sp_data.get("owner", {}).get("display_name") if entity_type == "playlist" else ", ".join(a.get("name", "") for a in sp_data.get("artists", []))
                            images = sp_data.get("images") or []
                            thumbnail = images[0].get("url") if images else None

                            raw_items = (sp_data.get("tracks", {}).get("items") or []) if entity_type == "playlist" else (sp_data.get("tracks", {}).get("items") or [])
                            tracks: List[PlaylistTrackItem] = []
                            for it in raw_items:
                                trk = it.get("track") if entity_type == "playlist" else it
                                if not trk or not trk.get("name"):
                                    continue
                                t_title = trk.get("name", "").strip()
                                t_author = ", ".join(a.get("name", "") for a in trk.get("artists", []) if a.get("name"))
                                dur_ms = int(trk.get("duration_ms") or 0)
                                dur_sec = max(0, dur_ms // 1000)
                                t_id = trk.get("id")
                                t_url = f"https://open.spotify.com/track/{t_id}" if t_id else None
                                q_str = f"{t_title} {t_author}".strip() if t_author else t_title
                                tracks.append(PlaylistTrackItem(
                                    title=t_title,
                                    author=t_author or "Spotify Artist",
                                    query=q_str,
                                    duration=dur_sec,
                                    url=t_url,
                                ))

                            if tracks:
                                return PlaylistResult(
                                    title=clean_track_title(pl_title),
                                    author=pl_author or "Spotify",
                                    url=url,
                                    tracks=tracks,
                                    thumbnail=thumbnail,
                                    requester=requester,
                                )

                # Primary Fallback: Spotify Embed scraper
                async with session.get(embed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        html_text = await resp.text()

            if not html_text:
                return None

            next_data = re.search(r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.DOTALL)
            if not next_data:
                return None

            data = json.loads(next_data.group(1))
            props = data.get("props", {}).get("pageProps", {})
            state = props.get("state", {}).get("data", {})
            entity = state.get("entity", {})
            if not entity:
                return None

            pl_title = entity.get("title") or entity.get("name") or "Spotify Playlist"
            pl_author = entity.get("subtitle") or "Spotify"
            raw_track_list = entity.get("trackList", [])
            if not raw_track_list:
                return None

            tracks: List[PlaylistTrackItem] = []
            for item in raw_track_list:
                if not item:
                    continue
                t_title = (item.get("title") or "").strip()
                t_author = (item.get("subtitle") or "").strip().replace("\xa0", " ")
                if not t_title:
                    continue

                duration_ms = int(item.get("duration") or 0)
                dur_sec = max(0, duration_ms // 1000)
                t_uri = item.get("uri") or ""
                t_url = f"https://open.spotify.com/track/{t_uri.split(':')[-1]}" if t_uri.startswith("spotify:track:") else None

                query_str = f"{t_title} {t_author}".strip() if t_author else t_title
                tracks.append(PlaylistTrackItem(
                    title=t_title,
                    author=t_author or "Spotify Artist",
                    query=query_str,
                    duration=dur_sec,
                    url=t_url,
                ))

            if not tracks:
                return None

            cover_art = entity.get("coverArt", {}).get("sources", [])
            thumbnail = cover_art[0].get("url") if cover_art else None

            return PlaylistResult(
                title=clean_track_title(pl_title),
                author=pl_author,
                url=url,
                tracks=tracks,
                thumbnail=thumbnail,
                requester=requester,
            )
        except Exception as e:
            logger.error(f"Spotify playlist extraction error: {e}")
            return None

    @classmethod
    def _sync_extract_youtube_playlist(
        cls,
        url: str,
        requester: str = "DJ / AutoPlay",
    ) -> Optional[PlaylistResult]:
        """Synchronous yt-dlp flat playlist extraction."""
        m = re.search(r"[?&]list=([a-zA-Z0-9_-]+)", url)
        target_url = f"https://www.youtube.com/playlist?list={m.group(1)}" if m else url

        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "skip_download": True,
            "ignoreerrors": True,
            "socket_timeout": 12,
            "source_address": "0.0.0.0",
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios"],
                }
            },
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target_url, download=False)
                if not info:
                    return None

                pl_title = info.get("title") or "YouTube Playlist"
                pl_author = info.get("uploader") or info.get("channel") or "YouTube"
                entries = info.get("entries") or []
                if not entries:
                    return None

                # Titles that indicate unavailable/deleted/private videos
                _SKIP_TITLES = {"[deleted video]", "[private video]", "[unavailable]"}

                tracks: List[PlaylistTrackItem] = []
                for e in entries:
                    if not e:
                        continue
                    v_id = e.get("id") or e.get("url")
                    v_title = e.get("title") or "Unknown Video"
                    v_author = e.get("uploader") or e.get("channel") or "YouTube Artist"
                    v_dur = int(e.get("duration") or 0)

                    if not v_id:
                        continue

                    # Skip deleted/private/unavailable videos — they cause consecutive failures
                    if v_title.strip().lower() in _SKIP_TITLES:
                        logger.debug(f"Skipping unavailable YouTube playlist entry: {v_title!r}")
                        continue

                    if str(v_id).startswith("http"):
                        v_url = str(v_id)
                    else:
                        v_url = f"https://www.youtube.com/watch?v={v_id}"

                    tracks.append(PlaylistTrackItem(
                        title=clean_track_title(v_title),
                        author=v_author,
                        query=v_url,
                        duration=v_dur,
                        url=v_url,
                    ))

                if not tracks:
                    return None

                thumbnails = info.get("thumbnails") or []
                thumb_url = thumbnails[-1].get("url") if thumbnails else None

                return PlaylistResult(
                    title=clean_track_title(pl_title),
                    author=pl_author,
                    url=url,
                    tracks=tracks,
                    thumbnail=thumb_url,
                    requester=requester,
                )
        except Exception as e:
            logger.error(f"YouTube playlist extraction error: {e}")
            return None
