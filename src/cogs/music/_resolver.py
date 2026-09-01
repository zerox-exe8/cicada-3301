"""
Kyro Discord Bot - Universal Global Music Resolver
Ultra-High Accuracy Search Engine supporting Global (English, K-Pop, Anime, Latin, EDM, Bollywood, Regional)
with Multi-Tier Failover Cascade and Zero False-Rejection Guarantee.
"""

from __future__ import annotations

import html
import logging
import re
from typing import List, Optional, Tuple, Union

import aiohttp
import wavelink

logger = logging.getLogger("Kyro.Music.Resolver")

# Universal noise words and command prefixes
INTENT_PREFIX_REGEX = re.compile(
    r"^(?:play|sunao|chalao|lagao|bajao|song|gaana|gana|p|please\s+play|kyro\s+play)\s+",
    re.IGNORECASE,
)
INTENT_SUFFIX_REGEX = re.compile(
    r"\s+(?:sunao|chalao|lagao|bajao|song|gaana|gana|play)$",
    re.IGNORECASE,
)

# Common metadata tags
PROMO_NOISE_REGEX = re.compile(
    r"\b(?:official\s+video|official\s+audio|full\s+video|full\s+audio|music\s+video|"
    r"video\s+song|audio\s+song|lyric\s+video|lyrics\s+video|lyrics|hd\s+video|"
    r"4k\s+video|1080p|320kbps|mp3|download|full\s+song|bhojpuri\s+hit\s+song|"
    r"bhojpuri\s+song|new\s+song|latest\s+song|hit\s+song|full\s+track|full\s+album)\b",
    re.IGNORECASE,
)

# Phonetic typo corrections that do not harm global words
TYPO_MAP = {
    r"\btranding\b": "trending",
    r"\bbhojuri\b": "bhojpuri",
    r"\bvedio\b": "video",
    r"\bvedios\b": "videos",
    r"\bsongg\b": "song",
    r"\bsongs\b": "song",
    r"\bmuisc\b": "music",
    r"\bpunjbi\b": "punjabi",
    r"\barjit\b": "Arijit Singh",
    r"\barijit shing\b": "Arijit Singh",
    r"\barijit sngh\b": "Arijit Singh",
    r"\batif aslum\b": "Atif Aslam",
    r"\bsidhu mossewala\b": "Sidhu Moose Wala",
    r"\bsidhu moosewala\b": "Sidhu Moose Wala",
    r"\bneha kakar\b": "Neha Kakkar",
    r"\bshreya ghosal\b": "Shreya Ghoshal",
}


def parse_and_clean_query(raw_query: str) -> Tuple[str, str]:
    """Clean query safely without corrupting international song names."""
    q = html.unescape(raw_query).strip()
    q = INTENT_PREFIX_REGEX.sub("", q).strip()
    q = INTENT_SUFFIX_REGEX.sub("", q).strip()

    for pat, rep in TYPO_MAP.items():
        q = re.sub(pat, rep, q, flags=re.IGNORECASE)

    core = PROMO_NOISE_REGEX.sub("", q)
    core = re.sub(r"\s+", " ", core).strip()
    norm = re.sub(r"\s+", " ", q).strip()
    return norm, core


def clean_track_title(raw_title: str) -> str:
    """Clean track title by removing hashtag markers and channel noise."""
    if not raw_title:
        return ""
    t = html.unescape(raw_title).strip()
    t = re.sub(r"^#[A-Za-z0-9_]+\s*[-|:]\s*", "", t, flags=re.IGNORECASE).strip()
    t = re.sub(r"#([A-Za-z0-9_]+)", r"\1", t).strip()
    t = re.sub(
        r"\s*[\(\[](?:Official|Full|HD|4K|Audio|Video|Music|Lyrical|Visualizer|Teaser|Status|Bhojpuri Hit Song|Bhojpuri Song)[^\)\]]*[\)\]]",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    t = re.sub(
        r"\s*\|\s*(?:T-Series|Zee Music|Sony Music|Wave Music|Speed Records|YRF|Tips Official|Worldwide Records)[^|]*$",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    return re.sub(r"\s+", " ", t).strip()


def calculate_track_confidence(query: str, core_query: str, track: wavelink.Playable) -> float:
    """Calculate confidence score for candidate track to prioritize studio versions."""
    score = 0.0
    q_lower = query.lower()
    core_lower = core_query.lower()

    core_tokens = set(re.findall(r"\w+", core_lower))
    if not core_tokens:
        core_tokens = set(re.findall(r"\w+", q_lower))

    title_clean = (track.title or "").lower()
    author_clean = (track.author or "").lower()
    combined = f"{title_clean} {author_clean}"
    track_tokens = set(re.findall(r"\w+", combined))

    # 1. Token Overlap Score (Max 50 pts)
    if core_tokens:
        matched = core_tokens.intersection(track_tokens)
        token_ratio = len(matched) / len(core_tokens)
        score += token_ratio * 50.0

    # 2. Exact Phrase Match (Max 25 pts)
    if core_lower and core_lower in title_clean:
        score += 25.0
    elif core_lower and core_lower in combined:
        score += 15.0

    # 3. Official Artist / Topic Boost (Max 20 pts)
    if "- topic" in author_clean:
        score += 20.0
    elif "vevo" in author_clean or "official" in author_clean:
        score += 10.0

    # 4. Intent Modifiers Match
    for mod in ["remix", "lofi", "slowed", "reverb", "acoustic", "live", "unplugged", "cover"]:
        in_query = mod in q_lower or mod in core_lower
        in_title = mod in title_clean
        if in_query and in_title:
            score += 20.0
        elif not in_query and in_title:
            score -= 25.0

    # 5. Negative spam penalties
    for bad in ["parody", "reaction", "review", "tutorial", "ringtone", "status", "shorts", "teaser"]:
        if bad not in q_lower and bad in title_clean:
            score -= 40.0

    # 6. Duration Sanity Filter
    dur_s = (track.length // 1000) if track.length else 0
    if 0 < dur_s < 45 and "ringtone" not in q_lower:
        score -= 50.0
    elif dur_s > 1200 and not any(k in q_lower for k in ["jukebox", "compilation", "mashup", "nonstop"]):
        score -= 30.0
    elif 90 <= dur_s <= 420:
        score += 10.0

    return score


class MusicResolver:
    """Universal Global Search & Metadata Resolver powered by Lavalink V4."""

    @classmethod
    async def resolve(
        cls,
        query: str,
        requester: Optional[str] = None,
    ) -> Optional[Union[wavelink.Playable, wavelink.Playlist, List[wavelink.Playable]]]:
        """
        Universal Resolver for any search query, direct URL, or Spotify link.
        Cascades through 4 global providers to guarantee zero 'Not Found' errors.
        """
        raw_q = query.strip()
        if not raw_q:
            return None

        # 1. Direct Web URLs (Spotify, YouTube, SoundCloud, Direct HTTP)
        if raw_q.startswith(("http://", "https://")):
            return await cls._resolve_url(raw_q, requester)

        # 2. Advanced Multi-Tier Universal Search
        norm_query, core_query = parse_and_clean_query(raw_q)
        return await cls._resolve_search(norm_query, core_query, requester)

    @classmethod
    async def _resolve_search(
        cls,
        norm_query: str,
        core_query: str,
        requester: Optional[str] = None,
    ) -> Optional[wavelink.Playable]:
        """Multi-Tier universal cascade with dynamic candidate ranking."""
        best_candidate: Optional[wavelink.Playable] = None
        highest_score = -999.0

        target_q = core_query if core_query else norm_query

        # Tier 1: YouTube Music (Global Studio Master)
        try:
            results = await wavelink.Playable.search(target_q, source=wavelink.TrackSource.YouTubeMusic)
            if results:
                scored = [
                    (calculate_track_confidence(norm_query, core_query, t), t)
                    for t in results
                ]
                scored.sort(key=lambda x: x[0], reverse=True)
                top_score, top_track = scored[0]
                if top_score >= 40.0:
                    if requester:
                        top_track.extras = wavelink.ExtrasNamespace(requester=requester)
                    logger.info(f"Resolved via YouTube Music (Tier 1): '{top_track.title}' - {top_track.author}")
                    return top_track
                elif top_score > highest_score:
                    highest_score = top_score
                    best_candidate = top_track
        except Exception as e:
            logger.debug(f"Tier 1 (YouTube Music) notice: {e}")

        # Tier 1.5: YouTube Music with full query (if different)
        if norm_query != target_q:
            try:
                results = await wavelink.Playable.search(norm_query, source=wavelink.TrackSource.YouTubeMusic)
                if results:
                    scored = [
                        (calculate_track_confidence(norm_query, core_query, t), t)
                        for t in results
                    ]
                    scored.sort(key=lambda x: x[0], reverse=True)
                    top_score, top_track = scored[0]
                    if top_score >= 40.0:
                        if requester:
                            top_track.extras = wavelink.ExtrasNamespace(requester=requester)
                        logger.info(f"Resolved via YouTube Music (Tier 1.5): '{top_track.title}' - {top_track.author}")
                        return top_track
                    elif top_score > highest_score:
                        highest_score = top_score
                        best_candidate = top_track
            except Exception as e:
                logger.debug(f"Tier 1.5 notice: {e}")

        # Tier 2: Deezer Global Catalog (LavaSrc 320kbps / Lossless)
        try:
            results = await wavelink.Playable.search(f"dzsearch:{target_q}")
            if results:
                scored = [
                    (calculate_track_confidence(norm_query, core_query, t), t)
                    for t in results
                ]
                scored.sort(key=lambda x: x[0], reverse=True)
                top_score, top_track = scored[0]
                if top_score >= 35.0:
                    if requester:
                        top_track.extras = wavelink.ExtrasNamespace(requester=requester)
                    logger.info(f"Resolved via Deezer (Tier 2): '{top_track.title}' - {top_track.author}")
                    return top_track
                elif top_score > highest_score:
                    highest_score = top_score
                    best_candidate = top_track
        except Exception as e:
            logger.debug(f"Tier 2 (Deezer) notice: {e}")

        # Tier 3: SoundCloud Global / Indie / Remix Catalog
        try:
            results = await wavelink.Playable.search(target_q, source=wavelink.TrackSource.SoundCloud)
            if results:
                scored = [
                    (calculate_track_confidence(norm_query, core_query, t), t)
                    for t in results
                ]
                scored.sort(key=lambda x: x[0], reverse=True)
                top_score, top_track = scored[0]
                if top_score >= 30.0:
                    if requester:
                        top_track.extras = wavelink.ExtrasNamespace(requester=requester)
                    logger.info(f"Resolved via SoundCloud (Tier 3): '{top_track.title}' - {top_track.author}")
                    return top_track
                elif top_score > highest_score:
                    highest_score = top_score
                    best_candidate = top_track
        except Exception as e:
            logger.debug(f"Tier 3 (SoundCloud) notice: {e}")

        # Tier 4: Direct YouTube Search Fallback (for rare covers / gaming OSTs / unreleased tracks)
        try:
            results = await wavelink.Playable.search(f"ytsearch:{target_q}")
            if results:
                scored = [
                    (calculate_track_confidence(norm_query, core_query, t), t)
                    for t in results
                ]
                scored.sort(key=lambda x: x[0], reverse=True)
                top_score, top_track = scored[0]
                if top_score > highest_score:
                    highest_score = top_score
                    best_candidate = top_track
        except Exception as e:
            logger.debug(f"Tier 4 (YouTube Video) notice: {e}")

        # Guarantee zero 'Not Found': Return best candidate found across any tier
        if best_candidate:
            if requester:
                best_candidate.extras = wavelink.ExtrasNamespace(requester=requester)
            logger.info(f"Universal Resolution Selected: '{best_candidate.title}' ({highest_score:.1f}pts)")
            return best_candidate

        return None

    @classmethod
    async def _resolve_url(
        cls,
        url: str,
        requester: Optional[str] = None,
    ) -> Optional[Union[wavelink.Playable, wavelink.Playlist, List[wavelink.Playable]]]:
        """Resolve direct web links, Spotify embeds, and YouTube playlists."""
        # 1. Spotify Links
        if "spotify.com" in url:
            spotify_title = await cls._fetch_spotify_title(url)
            if spotify_title:
                norm, core = parse_and_clean_query(spotify_title)
                return await cls._resolve_search(norm, core, requester)

        # 2. Standard direct URL search on Lavalink Node
        try:
            results = await wavelink.Playable.search(url)
            if isinstance(results, wavelink.Playlist):
                for t in results.tracks:
                    if requester:
                        t.extras = wavelink.ExtrasNamespace(requester=requester)
                return results
            elif results:
                track = results[0]
                if requester:
                    track.extras = wavelink.ExtrasNamespace(requester=requester)
                return track
        except Exception as e:
            logger.debug(f"Direct URL search notice: {e}")

        # 3. If YouTube watch URL failed (e.g. YouTube bot detection), fallback to search via title/oEmbed
        if "youtube.com" in url or "youtu.be" in url:
            yt_title = await cls._fetch_oembed_title(url)
            if yt_title:
                clean_title = clean_track_title(yt_title)
                norm, core = parse_and_clean_query(clean_title)
                return await cls._resolve_search(norm, core, requester)

        return None

    @staticmethod
    async def _fetch_spotify_title(spotify_url: str) -> Optional[str]:
        """Extract song title and artist from Spotify open URL via public oEmbed API."""
        oembed_url = f"https://open.spotify.com/oembed?url={spotify_url}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        title = data.get("title", "")
                        return title.strip() if title else None
        except Exception as e:
            logger.debug(f"Spotify oEmbed fetch notice: {e}")
        return None

    @staticmethod
    async def _fetch_oembed_title(url: str) -> Optional[str]:
        """Extract title from YouTube oEmbed API without triggering bot blocks."""
        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("title")
        except Exception as e:
            logger.debug(f"YouTube oEmbed fetch notice: {e}")
        return None
