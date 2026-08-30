import aiohttp
import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("cicada.music.direct_resolver")

class DirectStreamResolver:
    """
    High-resilience Direct CDN Audio Stream Extractor.
    Extracts direct MP3 / AAC stream URLs from high-speed Cloudflare CDNs.
    Bypasses all YouTube BotGuard, OAuth, and datacenter IP rate limits.
    """
    _client_id: Optional[str] = None

    @classmethod
    async def get_client_id(cls, session: aiohttp.ClientSession) -> Optional[str]:
        if cls._client_id:
            return cls._client_id
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with session.get("https://soundcloud.com", headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as r:
                if r.status != 200:
                    return None
                html = await r.text()
                script_urls = re.findall(r'<script crossorigin src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)">', html)
                for surl in script_urls[-10:]:
                    try:
                        async with session.get(surl, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as js_r:
                            if js_r.status == 200:
                                js_text = await js_r.text()
                                client_ids = re.findall(r'client_id:"([a-zA-Z0-9]{32})"', js_text)
                                if client_ids:
                                    cls._client_id = client_ids[0]
                                    return cls._client_id
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"Error fetching dynamic stream client ID: {e}")
        return None

    @classmethod
    async def resolve(cls, query: str) -> Optional[Dict[str, Any]]:
        """Resolves any search query into a direct CDN MP3 stream URL with metadata."""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                cid = await cls.get_client_id(session)
                if not cid:
                    return None
                params = {"q": query, "client_id": cid, "limit": 5}
                async with session.get(
                    "https://api-v2.soundcloud.com/search/tracks",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=6)
                ) as sr:
                    if sr.status != 200:
                        return None
                    sdata = await sr.json()
                    results = sdata.get("collection", [])
                    if not results:
                        return None
                    for item in results:
                        title = item.get("title")
                        author = item.get("user", {}).get("username", "Unknown Artist")
                        artwork = item.get("artwork_url") or item.get("user", {}).get("avatar_url")
                        duration = item.get("duration", 0)
                        for t in item.get("media", {}).get("transcodings", []):
                            if t.get("format", {}).get("protocol") == "progressive":
                                meta_url = t.get("url")
                                async with session.get(
                                    meta_url,
                                    params={"client_id": cid},
                                    timeout=aiohttp.ClientTimeout(total=4)
                                ) as mr:
                                    if mr.status == 200:
                                        mdata = await mr.json()
                                        direct_url = mdata.get("url")
                                        if direct_url:
                                            return {
                                                "title": title,
                                                "author": author,
                                                "artwork": artwork,
                                                "duration": duration,
                                                "stream_url": direct_url
                                            }
        except Exception as e:
            logger.warning(f"Direct stream resolution failed for '{query}': {e}")
        return None
