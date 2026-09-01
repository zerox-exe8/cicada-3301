"""
Kyro Discord Bot - Native Smart Autoplay AI Engine
Dynamic Genre & Artist Clustering Recommendation Algorithm.
"""

from __future__ import annotations

import html
import logging
import random
import re
from typing import List, Optional, Set

from src.cogs.music._models import Track
from src.cogs.music._extractor import NativeExtractor, clean_track_title

logger = logging.getLogger("Kyro.Music.Autoplay")

ARTIST_CLUSTERS = {
    # Bollywood / Hindi Romantic & Soulful
    "arijit singh": ["Atif Aslam", "Jubin Nautiyal", "Mohit Chauhan", "KK", "Armaan Malik", "Pritam", "Sachin-Jigar", "Shreya Ghoshal"],
    "atif aslam": ["Arijit Singh", "Jubin Nautiyal", "Mustafa Zahid", "Rahat Fateh Ali Khan", "Ali Zafar", "Mohit Chauhan"],
    "jubin nautiyal": ["Arijit Singh", "Atif Aslam", "Akhil Sachdeva", "Tulsi Kumar", "Payal Dev", "Stebin Ben"],
    "kk": ["Shaan", "Mohit Chauhan", "Sonu Nigam", "Lucky Ali", "Pritam", "Arijit Singh"],
    
    # Punjabi / Drill / Desi Hip-Hop
    "sidhu moose wala": ["Karan Aujla", "AP Dhillon", "Shubh", "Diljit Dosanjh", "Amrit Maan", "Gurinder Gill", "DIVINE"],
    "karan aujla": ["Sidhu Moose Wala", "AP Dhillon", "Shubh", "Diljit Dosanjh", "Ikky", "Badshah"],
    "ap dhillon": ["Gurinder Gill", "Shubh", "Diljit Dosanjh", "Karan Aujla", "Sidhu Moose Wala", "Talwiinder"],
    "diljit dosanjh": ["Karan Aujla", "AP Dhillon", "Sidhu Moose Wala", "Garry Sandhu", "Amrinder Gill"],
    "shubh": ["AP Dhillon", "Karan Aujla", "Sidhu Moose Wala", "Talwiinder", "DIVINE"],

    # Western Pop
    "sabrina carpenter": ["Olivia Rodrigo", "Taylor Swift", "Billie Eilish", "Dua Lipa", "Ariana Grande", "Tate McRae"],
    "billie eilish": ["Finneas", "Lana Del Rey", "Olivia Rodrigo", "Lorde", "Melanie Martinez"],
    "taylor swift": ["Sabrina Carpenter", "Gracie Abrams", "Phoebe Bridgers", "Lana Del Rey", "Olivia Rodrigo"],
    "olivia rodrigo": ["Sabrina Carpenter", "Billie Eilish", "Conan Gray", "Tate McRae"],

    # Hip-Hop / Global Rap
    "eminem": ["50 Cent", "Dr. Dre", "Kendrick Lamar", "Snoop Dogg", "J. Cole"],
    "kendrick lamar": ["J. Cole", "Drake", "Baby Keem", "Travis Scott", "A$AP Rocky"],
    "travis scott": ["Don Toliver", "Metro Boomin", "Future", "Playboi Carti", "21 Savage"],

    # K-Pop
    "bts": ["TXT", "SEVENTEEN", "Stray Kids", "ENHYPEN", "Jungkook"],
    "newjeans": ["LE SSERAFIM", "IVE", "ILLIT", "aespa", "BLACKPINK"],

    # Anime / J-Pop
    "yoasobi": ["Ado", "LiSA", "Eve", "Kenshi Yonezu", "ZUTOMAYO"],
    "ado": ["YOASOBI", "Eve", "ZUTOMAYO", "Vaundy", "Kenshi Yonezu"],

    # EDM
    "alan walker": ["Marshmello", "The Chainsmokers", "Martin Garrix", "Avicii", "Kygo"],
    "marshmello": ["Alan Walker", "The Chainsmokers", "Martin Garrix", "DJ Snake"],

    # Phonk
    "phonk": ["Brazilian Phonk", "Kordhell", "DVRST", "Hensonn", "SXID", "NCTS"],
}


def extract_primary_artist(raw_artist: str) -> str:
    """Extract clean primary artist name from multi-artist strings."""
    if not raw_artist:
        return ""
    clean = html.unescape(raw_artist).strip()
    parts = re.split(r"[,/|]|\s+(?:feat\.?|ft\.?|and|&)\s+", clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    return parts[0] if parts else clean


class NativeSmartAutoplay:
    """Autonomous Music Recommendation Engine for Native Player."""

    @classmethod
    async def get_next_track(
        cls,
        current_track: Track,
        played_history: Set[str],
        consecutive_same_artist: int = 0,
    ) -> Optional[Track]:
        """Produce next recommended track using artist clustering and session memory."""
        if not current_track:
            return None

        clean_title = clean_track_title(current_track.title)
        primary_artist = extract_primary_artist(current_track.author)
        artist_key = primary_artist.lower()

        # 1. Determine Related Artists from Cluster Graph
        related_artists: List[str] = []
        for known_key, cluster in ARTIST_CLUSTERS.items():
            if known_key in artist_key or artist_key in known_key or known_key in clean_title.lower():
                related_artists = list(cluster)
                break

        # 2. Build Candidate Queries
        candidates_queries: List[str] = []
        if consecutive_same_artist >= 2 and related_artists:
            pick_artist = random.choice(related_artists)
            candidates_queries.append(f"{pick_artist} top songs")
            candidates_queries.append(f"{pick_artist} hit song")
        else:
            candidates_queries.append(f"{primary_artist} songs")
            candidates_queries.append(f"{clean_title} radio")
            if related_artists:
                candidates_queries.append(f"{random.choice(related_artists)} song")

        # 3. Extract and check against session history
        for query in candidates_queries:
            try:
                candidate = await NativeExtractor.extract(query, requester="⚡ Smart Autoplay Radio", is_autoplay=True)
                if candidate:
                    cand_title = clean_track_title(candidate.title).lower()
                    if cand_title not in played_history and candidate.title != current_track.title:
                        played_history.add(cand_title)
                        return candidate
            except Exception as e:
                logger.debug(f"Autoplay candidate notice for '{query}': {e}")

        return None
