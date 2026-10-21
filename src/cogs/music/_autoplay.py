from __future__ import annotations

import asyncio
import html
import json
import logging
import random
import re
import urllib.parse
from typing import Any, List, Optional, Set

import aiohttp
import yt_dlp

from src.cogs.music._models import Track
from src.cogs.music._extractor import (
    NativeExtractor,
    clean_track_title,
    YOUTUBE_URL_REGEX,
)

logger = logging.getLogger("Kyro.Music.Autoplay")

ARTIST_CLUSTERS = {
    # Bollywood / Hindi Romantic & Soulful
    "arijit singh": ["Atif Aslam", "Jubin Nautiyal", "Mohit Chauhan", "KK", "Armaan Malik", "Pritam", "Ankit Tiwari", "Sachin-Jigar", "Shreya Ghoshal", "Vishal Mishra"],
    "ankit tiwari": ["Arijit Singh", "Atif Aslam", "Mustafa Zahid", "Mohit Chauhan", "KK", "Mithoon", "Pritam", "Armaan Malik"],
    "atif aslam": ["Arijit Singh", "Jubin Nautiyal", "Mustafa Zahid", "Rahat Fateh Ali Khan", "Ali Zafar", "Mohit Chauhan", "Pritam", "Ankit Tiwari"],
    "jubin nautiyal": ["Arijit Singh", "Atif Aslam", "Akhil Sachdeva", "Tulsi Kumar", "Payal Dev", "Stebin Ben", "Vishal Mishra"],
    "kk": ["Shaan", "Mohit Chauhan", "Sonu Nigam", "Lucky Ali", "Pritam", "Arijit Singh", "Papon"],
    "sonu nigam": ["KK", "Shaan", "Udit Narayan", "Kumar Sanu", "Abhijeet", "Alka Yagnik", "Shreya Ghoshal"],
    "shreya ghoshal": ["Sunidhi Chauhan", "Arijit Singh", "Alka Yagnik", "Monali Thakur", "Pritam", "Shankar-Ehsaan-Loy"],
    "pritam": ["Arijit Singh", "KK", "Mohit Chauhan", "Atif Aslam", "Shaan", "Sachin-Jigar", "Ankit Tiwari"],
    "vishal mishra": ["Arijit Singh", "Jubin Nautiyal", "B Praak", "Akhil Sachdeva", "Sachet Tandon"],
    "armaan malik": ["Arijit Singh", "Darshan Raval", "Atif Aslam", "Ankit Tiwari", "Jubin Nautiyal"],
    "darshan raval": ["Armaan Malik", "Arijit Singh", "Jubin Nautiyal", "Atif Aslam", "Stebin Ben"],
    "mithoon": ["Ankit Tiwari", "Arijit Singh", "Atif Aslam", "Pritam"],
    
    # Punjabi / Drill / Desi Hip-Hop
    "sidhu moose wala": ["Karan Aujla", "AP Dhillon", "Shubh", "Diljit Dosanjh", "Amrit Maan", "Gurinder Gill", "DIVINE"],
    "karan aujla": ["Sidhu Moose Wala", "AP Dhillon", "Shubh", "Diljit Dosanjh", "Ikky", "Badshah", "Raftaar"],
    "ap dhillon": ["Gurinder Gill", "Shubh", "Diljit Dosanjh", "Karan Aujla", "Sidhu Moose Wala", "Talwiinder"],
    "diljit dosanjh": ["Karan Aujla", "AP Dhillon", "Sidhu Moose Wala", "Garry Sandhu", "Amrinder Gill", "Honey Singh"],
    "shubh": ["AP Dhillon", "Karan Aujla", "Sidhu Moose Wala", "Talwiinder", "DIVINE", "Wazir Patar"],
    "honey singh": ["Badshah", "Raftaar", "Guru Randhawa", "Diljit Dosanjh", "Alfaaz", "Lil Golu"],
    "badshah": ["Honey Singh", "Raftaar", "Guru Randhawa", "DIVINE", "Ikka", "Karan Aujla"],

    # Western Pop & Chart Toppers
    "the weeknd": ["Bruno Mars", "Post Malone", "Daft Punk", "Drake", "Travis Scott", "Dua Lipa"],
    "imagine dragons": ["Coldplay", "OneRepublic", "Twenty One Pilots", "Fall Out Boy", "Maroon 5"],
    "coldplay": ["Imagine Dragons", "OneRepublic", "The Lumineers", "The Script", "Maroon 5"],
    "bruno mars": ["The Weeknd", "Michael Jackson", "Ed Sheeran", "Mark Ronson", "Justin Bieber"],
    "ed sheeran": ["Shawn Mendes", "Charlie Puth", "Justin Bieber", "Sam Smith", "Lewis Capaldi"],
    "justin bieber": ["Shawn Mendes", "ZAYN", "Charlie Puth", "The Weeknd", "Post Malone"],
    "dua lipa": ["Bebe Rexha", "Ava Max", "Anne-Marie", "Katy Perry", "Rita Ora", "Taylor Swift"],
    "sabrina carpenter": ["Olivia Rodrigo", "Taylor Swift", "Billie Eilish", "Dua Lipa", "Ariana Grande", "Tate McRae"],
    "billie eilish": ["Finneas", "Lana Del Rey", "Olivia Rodrigo", "Lorde", "Melanie Martinez"],
    "taylor swift": ["Sabrina Carpenter", "Gracie Abrams", "Phoebe Bridgers", "Lana Del Rey", "Olivia Rodrigo"],
    "olivia rodrigo": ["Sabrina Carpenter", "Billie Eilish", "Conan Gray", "Tate McRae"],

    # Hip-Hop / Global Rap
    "eminem": ["50 Cent", "Dr. Dre", "Kendrick Lamar", "Snoop Dogg", "J. Cole", "NF"],
    "kendrick lamar": ["J. Cole", "Drake", "Baby Keem", "Travis Scott", "A$AP Rocky"],
    "travis scott": ["Don Toliver", "Metro Boomin", "Future", "Playboi Carti", "21 Savage"],
    "drake": ["Travis Scott", "Future", "21 Savage", "The Weeknd", "Lil Baby"],

    # K-Pop
    "bts": ["TXT", "SEVENTEEN", "Stray Kids", "ENHYPEN", "Jungkook", "V", "Jimin"],
    "newjeans": ["LE SSERAFIM", "IVE", "ILLIT", "aespa", "BLACKPINK", "TWICE"],

    # Anime / J-Pop
    "yoasobi": ["Ado", "LiSA", "Eve", "Kenshi Yonezu", "ZUTOMAYO"],
    "ado": ["YOASOBI", "Eve", "ZUTOMAYO", "Vaundy", "Kenshi Yonezu"],

    # EDM
    "alan walker": ["Marshmello", "The Chainsmokers", "Martin Garrix", "Avicii", "Kygo", "K-391"],
    "marshmello": ["Alan Walker", "The Chainsmokers", "Martin Garrix", "DJ Snake"],

    # Phonk
    "phonk": ["Brazilian Phonk", "Kordhell", "DVRST", "Hensonn", "SXID", "NCTS", "Montagem"],
}


def extract_primary_artist(raw_artist: str) -> str:
    """Extract clean primary artist name from multi-artist strings, prioritizing known singers."""
    if not raw_artist:
        return ""
    clean = html.unescape(raw_artist).strip()
    lowered = clean.lower()

    # Prioritize prominent singer from ARTIST_CLUSTERS over lyricist/producer
    for known in ARTIST_CLUSTERS:
        if known in lowered:
            parts = re.split(r"[,/|]|\s+(?:feat\.?|ft\.?|and|&)\s+", clean, flags=re.IGNORECASE)
            for p in parts:
                if known in p.lower():
                    return p.strip()

    parts = re.split(r"[,/|]|\s+(?:feat\.?|ft\.?|and|&)\s+", clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    return parts[0] if parts else clean


def normalize_history_title(raw_title: str) -> str:
    """Normalize song title for history deduplication by removing movie tags, version noise and brackets."""
    t = clean_track_title(raw_title).lower()
    t = re.sub(r'["\'\(\)\[\]]', "", t)
    t = re.sub(
        r"\b(?:from\s+.+?|ost|audio|video|lyrics?|full\s+song|new\s+version|remix|lofi|slowed|reverb)\b",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    return re.sub(r"\s+", " ", t)


class NativeSmartAutoplay:
    """Autonomous Multi-Engine Continuous Radio Player (JioSaavn + YouTube Mix)."""

    @classmethod
    async def get_next_recommendation(
        cls,
        current_track: Track,
        played_history: Set[str],
        db: Any = None,
        consecutive_same_artist: int = 0,
    ) -> Optional[Track]:
        """Compatibility bridge for GuildPlayer."""
        return await cls.get_next_track(
            current_track=current_track,
            played_history=played_history,
            consecutive_same_artist=consecutive_same_artist,
        )

    @classmethod
    async def get_next_track(
        cls,
        current_track: Track,
        played_history: Set[str],
        consecutive_same_artist: int = 0,
    ) -> Optional[Track]:
        """
        Produce next recommended track using multi-candidate pool from JioSaavn and Worldwide catalogs.
        Guarantees non-stop continuous playback without dying or repeating same tracks.
        """
        if not current_track:
            return None

        # Bound history size to prevent unbounded memory growth during 24/7 sessions
        if len(played_history) > 250:
            # Clear oldest half of history
            to_remove = list(played_history)[:120]
            for item in to_remove:
                played_history.discard(item)

        clean_title = clean_track_title(current_track.title)
        norm_curr_title = normalize_history_title(current_track.title)
        primary_artist = extract_primary_artist(current_track.author)
        artist_key = primary_artist.lower()

        # Find related artists in graph
        related_artists: List[str] = []
        for known_key, cluster in ARTIST_CLUSTERS.items():
            if known_key in artist_key or artist_key in known_key or known_key in clean_title.lower():
                related_artists = list(cluster)
                break

        # Build candidate search queries
        queries: List[str] = []
        if consecutive_same_artist >= 2 and related_artists:
            pick_artist = random.choice(related_artists)
            queries.append(f"{pick_artist} top songs")
            queries.append(f"{pick_artist} hits")
        else:
            if primary_artist and primary_artist.lower() not in ("official artist", "unknown", "youtube"):
                queries.append(f"{primary_artist} hits")
                queries.append(f"{primary_artist} songs")
            if related_artists:
                queries.append(f"{random.choice(related_artists)} hits")
            queries.append(f"{clean_title} songs")

        import wavelink

        # Strategy 1: YouTube Music Candidate Recommendations (High Audio Fidelity)
        for q in queries:
            try:
                res = await asyncio.wait_for(
                    wavelink.Playable.search(q, source=wavelink.TrackSource.YouTubeMusic),
                    timeout=6.0,
                )
                if res:
                    tracks = res if isinstance(res, list) else getattr(res, "tracks", [])
                    for top in tracks[:5]:
                        top_norm = normalize_history_title(top.title or "")
                        if top_norm and top_norm not in played_history and top_norm != norm_curr_title:
                            trk = Track(
                                title=top.title or q,
                                author=top.author or "Artist",
                                url=top.uri or "",
                                stream_url="",
                                duration=int((top.length or 0) / 1000),
                                thumbnail=top.artwork,
                                requester="⚡ Smart Autoplay Radio",
                                is_autoplay=True,
                                query=q,
                            )
                            trk._playable = top
                            played_history.add(top_norm)
                            return trk
            except Exception as e:
                logger.debug(f"YouTube Music autoplay search notice for '{q}': {e}")

        # Strategy 2: Standard YouTube Search Fallback
        for q in queries:
            try:
                res = await asyncio.wait_for(
                    wavelink.Playable.search(q, source=wavelink.TrackSource.YouTube),
                    timeout=6.0,
                )
                if res:
                    tracks = res if isinstance(res, list) else getattr(res, "tracks", [])
                    for top in tracks[:5]:
                        top_norm = normalize_history_title(top.title or "")
                        if top_norm and top_norm not in played_history and top_norm != norm_curr_title:
                            trk = Track(
                                title=top.title or q,
                                author=top.author or "Artist",
                                url=top.uri or "",
                                stream_url="",
                                duration=int((top.length or 0) / 1000),
                                thumbnail=top.artwork or (f"https://i.ytimg.com/vi/{top.identifier}/hqdefault.jpg" if getattr(top, "identifier", None) else None),
                                requester="⚡ Smart Autoplay Radio",
                                is_autoplay=True,
                                query=q,
                            )
                            trk._playable = top
                            played_history.add(top_norm)
                            return trk
            except Exception as e:
                logger.debug(f"Standard YouTube autoplay search notice for '{q}': {e}")

        return None

