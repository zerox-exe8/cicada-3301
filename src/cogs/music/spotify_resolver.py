"""
Cicada 3301 Discord Bot - Spotify & Canonical Music Metadata Resolver
Parses Spotify Track, Playlist, and Album links without requiring developer API keys.
Resolves raw user search queries to canonical official artist + track titles.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
import aiohttp

logger = logging.getLogger("cicada.spotify")

SPOTIFY_REGEX = re.compile(r"https?://open\.spotify\.com/(track|playlist|album)/([a-zA-Z0-9]+)")


class SpotifyResolver:
    """Async resolver for Spotify URLs and canonical music queries."""

    @staticmethod
    async def resolve_url(url: str) -> dict[str, Any] | None:
        """Resolve Spotify track, playlist, or album into clean track names and artwork."""
        match = SPOTIFY_REGEX.search(url)
        if not match:
            return None

        stype, sid = match.group(1), match.group(2)
        embed_url = f"https://open.spotify.com/embed/{stype}/{sid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(embed_url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status != 200:
                        return None
                    text = await resp.text()

            json_match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', text)
            if not json_match:
                return None

            data = json.loads(json_match.group(1))
            entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})

            if stype == "track":
                title = entity.get("title") or entity.get("name")
                artists = ", ".join([a.get("name", "") for a in entity.get("artists", [])]) if entity.get("artists") else ""
                sources = entity.get("coverArt", {}).get("sources", [])
                artwork = sources[0].get("url") if sources else None
                return {
                    "type": "track",
                    "query": f"{title} {artists}".strip(),
                    "title": title,
                    "artist": artists,
                    "artwork": artwork,
                }
            elif stype in ("playlist", "album"):
                name = entity.get("name") or entity.get("title") or f"Spotify {stype.capitalize()}"
                track_list = entity.get("trackList", [])
                tracks: list[str] = []
                for t in track_list:
                    t_title = t.get("title") or t.get("name")
                    t_artists = ", ".join([a.get("name", "") for a in t.get("artists", [])]) if t.get("artists") else ""
                    if t_title:
                        tracks.append(f"{t_title} {t_artists}".strip())
                return {
                    "type": stype,
                    "name": name,
                    "tracks": tracks,
                    "count": len(tracks),
                }
        except Exception as e:
            logger.debug(f"Failed to resolve Spotify URL {url}: {e}")
            return None

    @staticmethod
    async def resolve_canonical(query: str) -> str:
        """Resolve a loose search string into a precise canonical 'Track - Artist' query."""
        if query.startswith("http://") or query.startswith("https://"):
            return query

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://itunes.apple.com/search",
                    params={"term": query, "media": "music", "limit": "1"},
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        results = data.get("results", [])
                        if results:
                            track_name = results[0].get("trackName")
                            artist_name = results[0].get("artistName")
                            if track_name and artist_name:
                                return f"{track_name} {artist_name}"
        except Exception:
            pass

        return query
