"""
Cicada 3301 Discord Bot - Hyper-Fast Multi-Tier Stream Resolver
Instant RAM Caching + Official YouTube Android/iOS Studio Streams + Apple Music Graph
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, Optional

import aiohttp
import yt_dlp

from src.cogs.music._types import TrackItem, YDL_OPTS

logger = logging.getLogger("cicada.music.resolver")


class MusicResolver:
    """Hyper-Fast Multi-Tier Stream Resolver with Instant RAM Caching."""
    _client_id = "Pb72ranhoyt6gw7hM7TkzUItXlMWSNSo"
    _CACHE: Dict[str, TrackItem] = {}

    @classmethod
    async def resolve(cls, query: str) -> Optional[TrackItem]:
        clean_q = query.strip()
        cache_key = clean_q.lower()

        # Step 0: Instant 0ms RAM Cache Check
        if cache_key in cls._CACHE:
            cached = cls._CACHE[cache_key]
            logger.info(f"Instant cache hit for '{clean_q}' (0ms)")
            return TrackItem(
                title=cached.title,
                author=cached.author,
                duration=cached.duration,
                url=cached.url,
                stream_url=cached.stream_url,
                thumbnail=cached.thumbnail,
                requester=""
            )

        is_url = clean_q.startswith("http://") or clean_q.startswith("https://")
        
        # Tier 1: yt-dlp Android Fast Studio Client
        loop = asyncio.get_event_loop()
        def _yt_extract():
            target = clean_q if is_url else f"ytsearch1:{clean_q}"
            try:
                with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                    info = ydl.extract_info(target, download=False)
                    if info:
                        if 'entries' in info and info['entries']:
                            return info['entries'][0]
                        return info
            except Exception as e:
                logger.warning(f"yt-dlp Tier 1 notice for '{clean_q}': {e}")
            return None

        entry = await loop.run_in_executor(None, _yt_extract)
        if entry and entry.get('url'):
            raw_title = entry.get('title', clean_q)
            clean_t = re.sub(r'\(Full Video\)|\[Official Video\]|\(Official Audio\)|\|.*$', '', raw_title, flags=re.IGNORECASE).strip()
            author = entry.get('uploader') or entry.get('artist') or entry.get('channel') or 'Official Artist'
            track = TrackItem(
                title=clean_t or raw_title,
                author=author,
                duration=int(entry.get('duration', 0)),
                url=entry.get('webpage_url') or clean_q,
                stream_url=entry.get('url'),
                thumbnail=entry.get('thumbnail', ''),
                requester=""
            )
            cls._CACHE[cache_key] = track
            return track

        # Tier 2: Apple Music / iTunes Canonical Resolution + High-Speed Direct Stream
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with aiohttp.ClientSession(headers=headers) as s:
            canonical_t = clean_q
            canonical_a = "Official Artist"
            canonical_art = ""
            duration_s = 240
            
            try:
                itunes_url = f"https://itunes.apple.com/search?term={clean_q}&entity=song&limit=1"
                async with s.get(itunes_url, timeout=aiohttp.ClientTimeout(total=3)) as ir:
                    if ir.status == 200:
                        idata = await ir.json(content_type=None)
                        res = idata.get("results", [])
                        if res:
                            canonical_t = res[0].get("trackName", clean_q)
                            canonical_a = res[0].get("artistName", "Official Artist")
                            canonical_art = res[0].get("artworkUrl100", "").replace("100x100bb", "600x600bb")
                            duration_s = int(res[0].get("trackTimeMillis", 240000) / 1000)
            except Exception:
                pass

            # Multi-Candidate Fast Stream Search
            search_variations = [f"{canonical_t} {canonical_a}", canonical_t, clean_q]
            for term in search_variations:
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
                                                        duration=duration_s,
                                                        url=item.get("permalink_url", clean_q),
                                                        stream_url=direct_url,
                                                        thumbnail=canonical_art or item.get("artwork_url", ""),
                                                        requester=""
                                                    )
                                                    cls._CACHE[cache_key] = track
                                                    return track
                except Exception:
                    continue
        return None
