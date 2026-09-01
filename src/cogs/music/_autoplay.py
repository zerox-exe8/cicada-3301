"""
Kyro Discord Bot - Smart Autoplay AI Engine
Spotify/Apple Music-grade Dynamic Radio Algorithm with Related Artist Clustering,
Gapless RAM Pre-fetching, and Anti-Repetition Guard.
"""

from __future__ import annotations

import html
import logging
import random
import re
from typing import List, Optional, Set

import wavelink

from src.cogs.music._resolver import clean_track_title, calculate_track_confidence

logger = logging.getLogger("Kyro.Music.Autoplay")

# ==========================================
# Dynamic Genre & Artist Compatibility Graph
# ==========================================
ARTIST_CLUSTERS = {
    # Bollywood / Hindi Romantic & Soulful
    "arijit singh": ["Atif Aslam", "Jubin Nautiyal", "Mohit Chauhan", "KK", "Armaan Malik", "Pritam", "Sachin-Jigar", "Shreya Ghoshal"],
    "atif aslam": ["Arijit Singh", "Jubin Nautiyal", "Mustafa Zahid", "Rahat Fateh Ali Khan", "Ali Zafar", "Mohit Chauhan"],
    "jubin nautiyal": ["Arijit Singh", "Atif Aslam", "Akhil Sachdeva", "Tulsi Kumar", "Payal Dev", "Stebin Ben"],
    "kk": ["Shaan", "Mohit Chauhan", "Sonu Nigam", "Lucky Ali", "Pritam", "Arijit Singh"],
    "sonu nigam": ["Udit Narayan", "Kumar Sanu", "Shaan", "Alka Yagnik", "Shreya Ghoshal"],
    
    # Punjabi / Drill / Desi Hip-Hop
    "sidhu moose wala": ["Karan Aujla", "AP Dhillon", "Shubh", "Diljit Dosanjh", "Amrit Maan", "Gurinder Gill", "DIVINE"],
    "karan aujla": ["Sidhu Moose Wala", "AP Dhillon", "Shubh", "Diljit Dosanjh", "Ikky", "Badshah"],
    "ap dhillon": ["Gurinder Gill", "Shubh", "Diljit Dosanjh", "Karan Aujla", "Sidhu Moose Wala", "Talwiinder"],
    "diljit dosanjh": ["Karan Aujla", "AP Dhillon", "Sidhu Moose Wala", "Garry Sandhu", "Amrinder Gill"],
    "shubh": ["AP Dhillon", "Karan Aujla", "Sidhu Moose Wala", "Talwiinder", "DIVINE"],
    "divine": ["KR$NA", "Raftaar", "Seedhe Maut", "MC Stan", "Badshah", "Emiway Bantai"],
    "kr$na": ["Raftaar", "Seedhe Maut", "DIVINE", "Karma", "Yungsta"],
    "seedhe maut": ["KR$NA", "Raftaar", "Yungsta", "Prabh Deep", "Ahmer"],

    # Western Pop
    "sabrina carpenter": ["Olivia Rodrigo", "Taylor Swift", "Billie Eilish", "Dua Lipa", "Ariana Grande", "Tate McRae", "Chappell Roan"],
    "billie eilish": ["Finneas", "Lana Del Rey", "Olivia Rodrigo", "Lorde", "Melanie Martinez", "Gracie Abrams"],
    "taylor swift": ["Sabrina Carpenter", "Gracie Abrams", "Phoebe Bridgers", "Lana Del Rey", "Olivia Rodrigo"],
    "olivia rodrigo": ["Sabrina Carpenter", "Billie Eilish", "Conan Gray", "Tate McRae", "Avril Lavigne"],
    "dua lipa": ["Calvin Harris", "Kylie Minogue", "Ariana Grande", "Ava Max", "Bebe Rexha", "Doja Cat"],

    # Hip-Hop / Global Rap
    "eminem": ["50 Cent", "Dr. Dre", "Kendrick Lamar", "Snoop Dogg", "Royce da 5'9\"", "J. Cole"],
    "kendrick lamar": ["J. Cole", "Drake", "Baby Keem", "Travis Scott", "ScHoolboy Q", "A$AP Rocky"],
    "travis scott": ["Don Toliver", "Metro Boomin", "Future", "Playboi Carti", "21 Savage", "Lil Uzi Vert"],
    "drake": ["Future", "Travis Scott", "21 Savage", "Lil Baby", "The Weeknd", "PARTYNEXTDOOR"],
    "the weeknd": ["Drake", "Post Malone", "Dahe", "SZA", "Lana Del Rey", "Kavinsky"],

    # K-Pop
    "bts": ["TXT", "SEVENTEEN", "Stray Kids", "ENHYPEN", "j-hope", "Jungkook", "Agust D"],
    "newjeans": ["LE SSERAFIM", "IVE", "ILLIT", "aespa", "BLACKPINK", "TWICE", "FIFTY FIFTY"],
    "blackpink": ["NewJeans", "LE SSERAFIM", "aespa", "TWICE", "ITZY", "JENNIE", "LISA"],
    "stray kids": ["ATEEZ", "ENHYPEN", "TXT", "NCT 127", "THE BOYZ", "SEVENTEEN"],

    # Anime / J-Pop
    "yoasobi": ["Ado", "LiSA", "Eve", "Kenshi Yonezu", "ZUTOMAYO", "RADWIMPS", "King Gnu"],
    "ado": ["YOASOBI", "Eve", "ZUTOMAYO", "Vaundy", "Kenshi Yonezu", "Creepy Nuts"],
    "kenshi yonezu": ["King Gnu", "RADWIMPS", "Vaundy", "Eve", "YOASOBI", "Fujii Kaze"],

    # EDM / Electronic
    "alan walker": ["Marshmello", "The Chainsmokers", "Martin Garrix", "Avicii", "Kygo", "K-391"],
    "marshmello": ["Alan Walker", "The Chainsmokers", "Martin Garrix", "DJ Snake", "Slushii"],
    "avicii": ["Kygo", "Martin Garrix", "Calvin Harris", "Alesso", "Swedish House Mafia", "Zedd"],

    # Latin
    "despacito": ["Luis Fonsi", "Daddy Yankee", "J Balvin", "Bad Bunny", "Ozuna", "Maluma"],
    "bad bunny": ["Rauw Alejandro", "J Balvin", "Feid", "Myke Towers", "Anuel AA", "Karol G"],
}


def extract_primary_artist(raw_artist: str) -> str:
    """Extract clean primary artist name from multi-artist strings."""
    if not raw_artist:
        return ""
    clean = html.unescape(raw_artist).strip()
    parts = re.split(r"[,/|]|\s+(?:feat\.?|ft\.?|and|&)\s+", clean, flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]
    return parts[0] if parts else clean


class SmartAutoplayEngine:
    """Autonomous Music Recommendation Engine."""

    @classmethod
    async def get_next_track(
        cls,
        current_track: wavelink.Playable,
        played_history: Set[str],
        consecutive_same_artist: int = 0,
    ) -> Optional[wavelink.Playable]:
        """
        Produce next best seamless recommendation:
        - Prevents repeating tracks in the session history.
        - Rotates compatible artists dynamically to prevent listener fatigue.
        """
        if not current_track:
            return None

        clean_title = clean_track_title(current_track.title or "")
        author_raw = current_track.author or "Official Artist"
        primary_artist = extract_primary_artist(author_raw)
        artist_key = primary_artist.lower()

        logger.info(f"Generating Autoplay recommendation for seed: '{clean_title}' by '{primary_artist}'")

        # 1. Determine Related Artists from Cluster Graph
        related_artists: List[str] = []
        for known_key, cluster in ARTIST_CLUSTERS.items():
            if known_key in artist_key or artist_key in known_key:
                related_artists = list(cluster)
                break

        # Candidate Search Strategies (Multi-Tier Pool)
        search_queries: List[str] = []

        # If played same artist 2 times consecutively, force switch to related artist in cluster
        if consecutive_same_artist >= 2 and related_artists:
            pick_artist = random.choice(related_artists)
            search_queries.append(f"ytmsearch:{pick_artist} top songs")
            search_queries.append(f"dzsearch:{pick_artist}")
            logger.info(f"Anti-Fatigue trigger: Shifting artist from '{primary_artist}' to '{pick_artist}'")
        else:
            # Seed 1: Direct Artist Radio Mix
            search_queries.append(f"ytmsearch:{primary_artist} similar songs")
            search_queries.append(f"ytmsearch:{primary_artist} mix")
            # Seed 2: Song specific Radio
            search_queries.append(f"ytmsearch:{clean_title} radio")
            # Seed 3: Related Cluster Artists
            if related_artists:
                search_queries.append(f"ytmsearch:{random.choice(related_artists)} top songs")
            # Seed 4: Deezer Catalog
            search_queries.append(f"dzsearch:{primary_artist}")

        # Execute candidate search & ranking across queries
        for query in search_queries:
            try:
                results = await wavelink.Playable.search(query)
                if not results:
                    continue

                candidates: List[wavelink.Playable] = []
                if isinstance(results, wavelink.Playlist):
                    candidates = list(results.tracks)
                elif isinstance(results, list):
                    candidates = results

                # Filter against session played history
                unplayed: List[wavelink.Playable] = []
                for t in candidates:
                    t_title_clean = clean_track_title(t.title or "").lower()
                    t_uri = (t.uri or "").lower()
                    if t_title_clean in played_history or t_uri in played_history:
                        continue
                    unplayed.append(t)

                if not unplayed:
                    continue

                # Score unplayed candidates
                scored = [
                    (calculate_track_confidence(clean_title, primary_artist, t), t)
                    for t in unplayed
                ]
                scored.sort(key=lambda x: x[0], reverse=True)

                # Pick top matching candidate
                top_score, best_track = scored[0]
                best_track.extras = wavelink.ExtrasNamespace(requester="⚡ Smart Autoplay Radio")

                # Add to history
                best_title = clean_track_title(best_track.title or "").lower()
                played_history.add(best_title)
                if best_track.uri:
                    played_history.add(best_track.uri.lower())

                logger.info(
                    f"Autoplay Selected: '{best_track.title}' — {best_track.author} (Score: {top_score:.1f}pts)"
                )
                return best_track

            except Exception as e:
                logger.debug(f"Autoplay query '{query}' notice: {e}")

        return None
