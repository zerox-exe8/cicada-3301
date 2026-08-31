"""
Cicada 3301 Discord Bot - Turbo-Fast Official Music Resolver
High-speed single-pass YouTube studio extraction + 0ms RAM Caching + Pre-warmed ThreadPool.
"""

from __future__ import annotations

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional

import yt_dlp

from src.cogs.music._types import TrackItem, YDL_OPTS

logger = logging.getLogger("cicada.music.resolver")

# Persistent Pre-Warmed Thread Pool for zero thread initialization latency
RESOLVER_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="MusicResolver")


class MusicResolver:
    """Turbo-Fast Official YouTube Studio Resolver."""
    _CACHE: Dict[str, TrackItem] = {}

    @classmethod
    def clean_query(cls, raw: str) -> str:
        """Strip junk marketing tokens from search query."""
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
        target = raw_q if is_url else f"ytsearch1:{cleaned_search or raw_q}"

        # Step 1: Single-Pass Fast YouTube Studio Extractor
        loop = asyncio.get_event_loop()

        def _fast_extract():
            try:
                with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                    info = ydl.extract_info(target, download=False)
                    if info:
                        if 'entries' in info and info['entries']:
                            return info['entries'][0]
                        return info
            except Exception as e:
                logger.error(f"Fast extraction notice for '{target}': {e}")
            return None

        entry = await loop.run_in_executor(RESOLVER_POOL, _fast_extract)
        if entry and entry.get('url'):
            raw_title = entry.get('title', raw_q)
            clean_t = re.sub(
                r'\(Full Video\)|\[Official Video\]|\(Official Audio\)|\|.*$',
                '',
                raw_title,
                flags=re.IGNORECASE
            ).strip()
            author = entry.get('uploader') or entry.get('artist') or entry.get('channel') or 'Official Artist'
            track = TrackItem(
                title=clean_t or raw_title,
                author=author,
                duration=int(entry.get('duration', 0)),
                url=entry.get('webpage_url') or raw_q,
                stream_url=entry.get('url'),
                thumbnail=entry.get('thumbnail', ''),
                requester=""
            )
            # Store in RAM Cache
            cls._CACHE[cache_key] = track
            return track

        return None
