"""
Cicada 3301 Discord Bot - Ultra-Strong Multi-Tier Music Resolver
Instant RAM Caching + Apple Music Canonical Graph + Multi-Client YouTube Studio Extractor
"""

from __future__ import annotations

import asyncio
import logging
import re
import aiohttp
from typing import Dict, Optional, List

import yt_dlp

from src.cogs.music._types import TrackItem, YDL_OPTS

logger = logging.getLogger("cicada.music.resolver")


class MusicResolver:
    """Ultra-Strong Multi-Tier Music Resolver."""
    _client_id = "Pb72ranhoyt6gw7hM7TkzUItXlMWSNSo"
    _CACHE: Dict[str, TrackItem] = {}

    @classmethod
    def clean_query(cls, raw: str) -> str:
        """Sanitize query to extract core song and artist keywords."""
        q = re.sub(
            r'\(.*?\)|\[.*?\]|\|.*$|full audio|full video|official video|official audio|lyrics|hd|4k|remix|slowed|reverb',
            '',
            raw,
            flags=re.IGNORECASE
        )
        return " ".join(q.split()).strip()

    @classmethod
    async def resolve(cls, query: str) -> Optional[TrackItem]:
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
                requester=""
            )

        is_url = raw_q.startswith("http://") or raw_q.startswith("https://")
        cleaned_search = cls.clean_query(raw_q) if not is_url else raw_q

        # Step 1: Canonical Apple Music / iTunes Resolution (< 60ms)
        canonical_t = cleaned_search or raw_q
        canonical_a = "Official Artist"
        canonical_art = ""
        duration_s = 240

        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        if not is_url:
            async with aiohttp.ClientSession(headers=headers) as s:
                try:
                    itunes_url = f"https://itunes.apple.com/search?term={canonical_t}&entity=song&limit=1"
                    async with s.get(itunes_url, timeout=aiohttp.ClientTimeout(total=3)) as ir:
                        if ir.status == 200:
                            idata = await ir.json(content_type=None)
                            res = idata.get("results", [])
                            if res:
                                canonical_t = res[0].get("trackName", canonical_t)
                                canonical_a = res[0].get("artistName", "Official Artist")
                                canonical_art = res[0].get("artworkUrl100", "").replace("100x100bb", "600x600bb")
                                duration_s = int(res[0].get("trackTimeMillis", 240000) / 1000)
                except Exception:
                    pass

        # Step 2: Multi-Client YouTube Studio Search (Tier 1)
        loop = asyncio.get_event_loop()

        def _yt_extract():
            search_targets: List[str] = []
            if is_url:
                search_targets = [raw_q]
            else:
                search_targets = [
                    f"ytsearch1:{canonical_t} {canonical_a}",
                    f"ytsearch1:{raw_q}",
                    f"ytsearch1:{cleaned_search}"
                ]

            for target in search_targets:
                try:
                    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                        info = ydl.extract_info(target, download=False)
                        if info:
                            entry = info['entries'][0] if ('entries' in info and info['entries']) else info
                            if entry and entry.get('url'):
                                return entry
                except Exception as e:
                    logger.warning(f"yt-dlp candidate notice for '{target}': {e}")
            return None

        entry = await loop.run_in_executor(None, _yt_extract)
        if entry and entry.get('url'):
            raw_title = entry.get('title', canonical_t)
            clean_t = re.sub(
                r'\(Full Video\)|\[Official Video\]|\(Official Audio\)|\|.*$',
                '',
                raw_title,
                flags=re.IGNORECASE
            ).strip()
            author = entry.get('uploader') or entry.get('artist') or canonical_a
            track = TrackItem(
                title=clean_t or raw_title,
                author=author,
                duration=int(entry.get('duration', duration_s)),
                url=entry.get('webpage_url') or raw_q,
                stream_url=entry.get('url'),
                thumbnail=entry.get('thumbnail') or canonical_art,
                requester=""
            )
            cls._CACHE[cache_key] = track
            return track

        # Step 3: Fast Lossless CDN Fallback (Tier 2) - With Bootleg & Duration Filters
        async with aiohttp.ClientSession(headers=headers) as s:
            search_candidates = [
                f"{canonical_t} {canonical_a}",
                canonical_t,
                raw_q
            ]
            for term in search_candidates:
                params = {"q": term, "client_id": cls._client_id, "limit": 6}
                try:
                    async with s.get(
                        "https://api-v2.soundcloud.com/search/tracks",
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=4)
                    ) as sr:
                        if sr.status == 200:
                            sdata = await sr.json()
                            items = sdata.get("collection", [])
                            if items:
                                for item in items:
                                    it_title = item.get("title", "").lower()
                                    # Filter out slowed/reverb/bass boosted
                                    if any(k in it_title for k in ["slowed", "reverb", "bass boosted", "8d"]):
                                        continue

                                    # Filter out short previews (< 45s)
                                    dur_item = item.get("duration", 0) // 1000
                                    if dur_item < 45:
                                        continue

                                    trans = item.get("media", {}).get("transcodings", [])
                                    sorted_trans = sorted(
                                        trans,
                                        key=lambda x: 0 if x.get("format", {}).get("protocol") == "progressive" else 1
                                    )
                                    for t in sorted_trans:
                                        meta_url = t.get("url")
                                        async with s.get(meta_url, params={"client_id": cls._client_id}, timeout=2) as mr:
                                            if mr.status == 200:
                                                mdata = await mr.json()
                                                direct_url = mdata.get("url")
                                                if direct_url:
                                                    track = TrackItem(
                                                        title=canonical_t,
                                                        author=canonical_a,
                                                        duration=dur_item or duration_s,
                                                        url=item.get("permalink_url", raw_q),
                                                        stream_url=direct_url,
                                                        thumbnail=canonical_art or item.get("artwork_url", ""),
                                                        requester=""
                                                    )
                                                    cls._CACHE[cache_key] = track
                                                    return track
                except Exception:
                    continue

        return None
