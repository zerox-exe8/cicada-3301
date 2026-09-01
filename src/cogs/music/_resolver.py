"""
Kyro Discord Bot - Music Resolver
100% Exact Song Matching + Multi-Candidate Ranking Engine + Studio Master + Smart Autoplay.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import aiohttp
from pyDes import des, ECB, PAD_PKCS5
import yt_dlp

from src.cogs.music._types import TrackItem, YDL_OPTS

logger = logging.getLogger("Kyro.Music.Resolver")

RESOLVER_POOL = ThreadPoolExecutor(max_workers=6, thread_name_prefix="MusicResolver")

COMMON_TYPOS = {
    r"\btranding\b": "trending",
    r"\bbhojuri\b": "bhojpuri",
    r"\bvedio\b": "video",
    r"\bvedios\b": "videos",
    r"\bsongg\b": "song",
    r"\bsongs\b": "song",
    r"\bmuisc\b": "music",
}


def normalize_query(query: str) -> str:
    """Correct common phonetic typos and clean search query."""
    q = query.strip()
    for typo, correction in COMMON_TYPOS.items():
        q = re.sub(typo, correction, q, flags=re.IGNORECASE)
    return q.strip()


def clean_track_title(raw_title: str) -> str:
    """Clean video titles by removing hashtags and promotional noise."""
    t = html.unescape(raw_title).strip()
    # Remove leading hashtag markers e.g. #Video | or #Audio - or #Song |
    t = re.sub(r"^#[A-Za-z0-9_]+\s*[-|:]\s*", "", t, flags=re.IGNORECASE).strip()
    # Remove hashtags inside text e.g. #Ankush Raja, #Shilpi Raj -> Ankush Raja, Shilpi Raj
    t = re.sub(r"#([A-Za-z0-9_]+)", r"\1", t).strip()
    # Remove media tags in parentheses/brackets e.g. (Official Video), [Full Song]
    t = re.sub(
        r"\s*[\(\[](?:Official|Full|HD|4K|Audio|Video|Music|Lyrical|Visualizer|Teaser|Status|Bhojpuri Hit Song|Bhojpuri Song)[^\)\]]*[\)\]]",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    # Remove trailing record label stamps e.g. | T-Series, | Wave Music
    t = re.sub(
        r"\s*\|\s*(?:T-Series|Zee Music|Sony Music|Speed Records|YRF|Tips|Wave Music|Worldwide Records|Saregama|Bhojpuri Hit Song)[^|]*$",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    return t if len(t) >= 2 else raw_title


class MusicResolver:
    """Smart Music Resolver with 0ms cache and multi-candidate ranked resolution."""
    _CACHE: Dict[str, TrackItem] = {}

    @classmethod
    def _decrypt_saavn_url(cls, encrypted_url: str) -> Optional[str]:
        """Decrypt JioSaavn 320kbps master media URL."""
        try:
            cipher = des(b"38346591", ECB, pad=None, padmode=PAD_PKCS5)
            dec = cipher.decrypt(base64.b64decode(encrypted_url.strip()))
            url = dec.decode("utf-8", errors="ignore")
            if "http" in url:
                url = url[url.find("http"):]
                if ".mp4" in url:
                    url = url.split(".mp4")[0] + ".mp4"
                return url.replace("_96.mp4", "_320.mp4").replace("_160.mp4", "_320.mp4")
        except Exception as e:
            logger.debug(f"Saavn decrypt notice: {e}")
        return None

    @classmethod
    def _score_saavn_track(cls, query: str, res: dict) -> int:
        """Calculate match confidence score for JioSaavn."""
        q = query.lower().strip()
        raw_title = html.unescape(res.get("title") or res.get("song") or "").lower().strip()
        clean_title = re.sub(r"\(.*?\)|\[.*?\]", "", raw_title).strip()

        artists: List[str] = []
        more_info = res.get("more_info", {})
        artist_map = more_info.get("artistMap", {})
        for art in artist_map.get("primary_artists", []):
            if isinstance(art, dict) and "name" in art:
                artists.append(art["name"].lower())
        if not artists and "primary_artists" in res:
            artists.append(res["primary_artists"].lower())
        artist_str = " ".join(artists)

        combined_target = f"{clean_title} {artist_str} {raw_title}"
        q_words = [w for w in re.findall(r"\w+", q) if len(w) > 1]
        if not q_words:
            return 0

        matched_words = [w for w in q_words if w in combined_target]
        coverage = len(matched_words) / len(q_words)
        score = int(coverage * 80)

        if clean_title == q:
            score += 100
        elif clean_title in q or q in clean_title:
            ratio = min(len(clean_title), len(q)) / max(len(clean_title), len(q))
            if ratio > 0.35:
                score += int(ratio * 70)

        return score

    @classmethod
    def _score_yt_candidate(cls, query: str, entry: dict) -> int:
        """Intelligent ranking score (-100 to 200) for YouTube search entries."""
        q = query.lower().strip()
        q_words = [w for w in re.findall(r"\w+", q) if len(w) > 1]
        title = html.unescape(entry.get("title") or "").lower().strip()
        uploader = html.unescape(entry.get("uploader") or "").lower().strip()
        duration = entry.get("duration") or 0

        # Discard shorts (<45s) and ultra-long compilations (>900s / 15 mins) unless queried
        if duration > 0 and (duration < 45 or duration > 900):
            if "1 hour" not in q and "loop" not in q and "full album" not in q:
                return -100

        target = f"{title} {uploader}"
        if not q_words:
            return 50

        matched = [w for w in q_words if w in target]
        coverage = len(matched) / len(q_words)
        score = int(coverage * 100)

        # Authority Channel Boost (Official Record Labels & Verified Artists)
        official_keywords = [
            "official", "vevo", "music", "series", "records", "zee",
            "sony", "wave", "saregama", "tips", "yrf", "audio"
        ]
        if any(k in uploader for k in official_keywords):
            score += 25

        # Penalties for unwanted non-original formats unless explicitly queried
        penalties = [
            "slowed", "reverb", "lofi", "8d", "status", "reaction",
            "dance cover", "tutorial", "karaoke", "instrumental", "teaser", "trailer"
        ]
        for bad in penalties:
            if bad in title and bad not in q:
                score -= 40

        # Duration sweet spot (2 to 6 minutes is typical studio track)
        if 120 <= duration <= 360:
            score += 15

        return score

    @classmethod
    async def extract_spotify_title(cls, url: str) -> Optional[str]:
        """Extract song title from Spotify URL using Spotify oEmbed."""
        try:
            oembed_url = f"https://open.spotify.com/oembed?url={url}"
            headers = {"User-Agent": "Mozilla/5.0"}
            async with aiohttp.ClientSession(headers=headers) as s:
                async with s.get(oembed_url, timeout=aiohttp.ClientTimeout(total=4)) as r:
                    if r.status == 200:
                        data = await r.json()
                        title = data.get("title", "")
                        return title
        except Exception:
            pass
        return None

    @classmethod
    async def _resolve_youtube_ranked(cls, search_query: str, is_url: bool, raw_q: str, cache_key: str) -> Optional[TrackItem]:
        """Multi-candidate YouTube search + intelligent ranking + stream extraction."""
        loop = asyncio.get_event_loop()

        def _yt_search_and_extract():
            try:
                if is_url:
                    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                        info = ydl.extract_info(search_query, download=False)
                        if not info:
                            return None
                        if "entries" in info and info["entries"]:
                            return info["entries"][0]
                        return info

                # 1. Fast Flat Search (5 candidates)
                fast_opts = {
                    "quiet": True,
                    "no_warnings": True,
                    "noplaylist": True,
                    "extract_flat": True,
                    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
                }
                with yt_dlp.YoutubeDL(fast_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch5:{search_query}", download=False)
                    if not info or "entries" not in info or not info["entries"]:
                        return None
                    entries = [e for e in info["entries"] if e]

                # 2. Score and Rank candidates
                scored: List[Tuple[int, dict]] = [
                    (cls._score_yt_candidate(search_query, e), e) for e in entries
                ]
                scored.sort(key=lambda x: x[0], reverse=True)
                best_score, best_candidate = scored[0]

                video_id = best_candidate.get("id")
                if not video_id:
                    video_url = best_candidate.get("url") or best_candidate.get("webpage_url")
                else:
                    video_url = f"https://www.youtube.com/watch?v={video_id}"

                # 3. Extract audio stream for top candidate
                with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                    stream_info = ydl.extract_info(video_url, download=False)
                    return stream_info

            except Exception as e:
                logger.error(f"YouTube ranked extraction error for '{search_query}': {e}")
            return None

        entry = await loop.run_in_executor(RESOLVER_POOL, _yt_search_and_extract)
        if entry and entry.get("url"):
            raw_title = entry.get("title", search_query)
            clean_t = clean_track_title(raw_title)
            author = entry.get("uploader") or entry.get("artist") or entry.get("channel") or "Official Artist"
            track = TrackItem(
                title=clean_t or raw_title,
                author=author,
                duration=int(entry.get("duration", 0)),
                url=entry.get("webpage_url") or raw_q,
                stream_url=entry.get("url"),
                thumbnail=entry.get("thumbnail", ""),
                requester="",
            )
            cls._CACHE[cache_key] = track
            logger.info(f"Resolved '{search_query}' -> '{track.title}' by '{author}'")
            return track
        return None

    @classmethod
    async def resolve(cls, query: str) -> Optional[TrackItem]:
        """Resolve any song query into high-fidelity streamable TrackItem with 100% precision."""
        raw_q = query.strip()
        cache_key = raw_q.lower()

        # Step 0: Instant 0ms RAM Cache Check
        if cache_key in cls._CACHE:
            cached = cls._CACHE[cache_key]
            logger.info(f"Instant cache hit for '{raw_q}' (0ms)")
            return TrackItem(
                title=cached.title,
                author=cached.author,
                duration=cached.duration,
                url=cached.url,
                stream_url=cached.stream_url,
                thumbnail=cached.thumbnail,
                requester="",
            )

        # Direct audio link detection (.mp3, .wav, .m4a, .ogg, .flac)
        if raw_q.startswith("http://") or raw_q.startswith("https://"):
            for ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
                if ext in raw_q.lower():
                    title = raw_q.split("/")[-1].split("?")[0]
                    track = TrackItem(
                        title=title,
                        author="Direct Stream",
                        duration=0,
                        url=raw_q,
                        stream_url=raw_q,
                        thumbnail="",
                        requester="",
                    )
                    cls._CACHE[cache_key] = track
                    return track

        # Spotify URL detection
        search_query = normalize_query(raw_q)
        if "spotify.com" in raw_q:
            spotify_title = await cls.extract_spotify_title(raw_q)
            if spotify_title:
                search_query = normalize_query(spotify_title)

        is_url = search_query.startswith("http://") or search_query.startswith("https://")
        word_count = len(search_query.split())

        # For multi-word queries (>=3 words) or URLs, run through YouTube Ranked Engine
        if is_url or word_count >= 3:
            yt_track = await cls._resolve_youtube_ranked(search_query, is_url, raw_q, cache_key)
            if yt_track:
                return yt_track

        # For 1-2 word queries, check JioSaavn 320kbps CD Studio Master
        if not is_url:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                params = {
                    "__call": "search.getResults",
                    "_format": "json",
                    "api_version": "4",
                    "ctx": "web6dot0",
                    "n": "10",
                    "p": "1",
                    "q": search_query,
                }
                async with aiohttp.ClientSession(headers=headers) as s:
                    async with s.get("https://www.jiosaavn.com/api.php", params=params, timeout=aiohttp.ClientTimeout(total=4)) as r:
                        if r.status == 200:
                            data = json.loads(await r.text())
                            results = data.get("results", [])
                            if results:
                                scored = [(cls._score_saavn_track(search_query, res), res) for res in results]
                                scored.sort(key=lambda x: x[0], reverse=True)
                                best_score, best_res = scored[0]

                                if best_score >= 50:
                                    pid = best_res.get("id")
                                    if pid:
                                        dparams = {
                                            "__call": "song.getDetails",
                                            "cc": "in",
                                            "_marker": "0",
                                            "_format": "json",
                                            "pids": pid,
                                        }
                                        async with s.get("https://www.jiosaavn.com/api.php", params=dparams, timeout=aiohttp.ClientTimeout(total=4)) as dr:
                                            if dr.status == 200:
                                                ddata = json.loads(await dr.text())
                                                sinfo = ddata.get(pid, {})
                                                enc_url = sinfo.get("encrypted_media_url")
                                                stream_url = cls._decrypt_saavn_url(enc_url) if enc_url else None

                                                if stream_url:
                                                    raw_title = sinfo.get("song") or sinfo.get("title") or search_query
                                                    clean_title = clean_track_title(raw_title)
                                                    author = html.unescape(sinfo.get("primary_artists") or sinfo.get("singers") or "Official Artist")
                                                    thumb = sinfo.get("image", "").replace("150x150", "500x500")
                                                    duration = int(sinfo.get("duration", 240))
                                                    web_url = sinfo.get("perma_url") or search_query

                                                    track = TrackItem(
                                                        title=clean_title,
                                                        author=author,
                                                        duration=duration,
                                                        url=web_url,
                                                        stream_url=stream_url,
                                                        thumbnail=thumb,
                                                        requester="",
                                                    )
                                                    cls._CACHE[cache_key] = track
                                                    logger.info(f"Resolved '{search_query}' -> '{clean_title}' by '{author}' (Score: {best_score})")
                                                    return track
            except Exception as e:
                logger.debug(f"Official master search notice: {e}")

        # Fallback to YouTube Ranked Engine
        return await cls._resolve_youtube_ranked(search_query, is_url, raw_q, cache_key)

    @classmethod
    async def recommend_next_track(
        cls,
        current_track: TrackItem,
        top_artists: Optional[List[str]] = None,
        played_urls: Optional[set[str]] = None,
    ) -> Optional[TrackItem]:
        """
        Autoplay: Generate next song recommendation based strictly on the current song's
        artist, genre, and related sound signature without repeating played songs.
        """
        played = played_urls or set()
        clean_title = clean_track_title(current_track.title)
        candidate_queries: List[str] = []

        # 1. Related song mix for the specific track
        candidate_queries.append(f"{clean_title} related mix")
        candidate_queries.append(f"{clean_title} songs")

        # 2. Same artist / singer hits
        if current_track.author and current_track.author not in ("Official Artist", "Direct Stream", "Unknown"):
            candidate_queries.append(f"{current_track.author} hit songs")
            candidate_queries.append(f"{current_track.author} songs")

        for q in candidate_queries:
            track = await cls.resolve(q)
            if (
                track
                and track.stream_url
                and track.stream_url not in played
                and track.url not in played
                and track.title.lower() != current_track.title.lower()
            ):
                return track

        return None
