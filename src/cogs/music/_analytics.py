"""
Kyro Discord Bot - Music Analytics & User Taste Engine
Tracks listening habits, Spotify Rich Presence, and cross-bot activity to personalize AI Autoplay.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, List, Optional

import discord

if TYPE_CHECKING:
    from src.core.bot import KyroBot
    from src.cogs.music._types import TrackItem

logger = logging.getLogger("Kyro.Music.Analytics")

MUSIC_BOT_PREFIXES = (
    "-p ", "-play ", "!play ", "!p ", ",play ", ",p ", ";play ", ";p ",
    "/play ", ".play ", ".p ", ">play ", ">p "
)


class MusicAnalytics:
    """Music analytics and taste profiler."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    async def record_play(
        self,
        user_id: int,
        guild_id: Optional[int],
        track_title: str,
        artist: str,
        genre: str = "general",
        source: str = "bot",
    ) -> None:
        """Record track play or Spotify listening activity into database."""
        if not track_title or not artist or user_id == self.bot.user.id:
            return

        clean_title = track_title.strip()[:200]
        clean_artist = artist.strip()[:200]

        query = """
        INSERT INTO user_music_history (user_id, guild_id, track_title, artist, genre, source, play_count, last_played_at)
        VALUES ($1, $2, $3, $4, $5, $6, 1, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id, track_title, artist)
        DO UPDATE SET 
            play_count = user_music_history.play_count + 1,
            last_played_at = CURRENT_TIMESTAMP,
            source = EXCLUDED.source;
        """
        try:
            if hasattr(self.bot, "db") and self.bot.db and getattr(self.bot.db, "pool", None):
                await self.bot.db.execute(
                    query,
                    user_id,
                    guild_id,
                    clean_title,
                    clean_artist,
                    genre,
                    source,
                )
        except Exception as e:
            logger.debug(f"Music analytics record notice: {e}")

    async def get_top_artists(self, user_ids: List[int], limit: int = 6) -> List[str]:
        """Fetch top artists listened to by a group of users."""
        if not user_ids or not hasattr(self.bot, "db") or not self.bot.db or not getattr(self.bot.db, "pool", None):
            return []

        query = f"""
        SELECT artist, SUM(play_count) as total_plays
        FROM user_music_history
        WHERE user_id = ANY($1::BIGINT[]) AND artist != 'Official Artist' AND artist != 'Unknown'
        GROUP BY artist
        ORDER BY total_plays DESC
        LIMIT {limit};
        """
        try:
            rows = await self.bot.db.fetch_all(query, user_ids)
            return [r["artist"] for r in rows if r.get("artist")]
        except Exception as e:
            logger.debug(f"Error fetching top artists: {e}")
            return []

    async def get_user_taste_summary(self, user_id: int) -> dict:
        """Get a summary of a user's listening profile."""
        if not hasattr(self.bot, "db") or not self.bot.db or not getattr(self.bot.db, "pool", None):
            return {"total_plays": 0, "top_artists": [], "top_tracks": []}

        try:
            artist_rows = await self.bot.db.fetch_all(
                """
                SELECT artist, SUM(play_count) as plays
                FROM user_music_history
                WHERE user_id = $1
                GROUP BY artist
                ORDER BY plays DESC
                LIMIT 5;
                """,
                user_id,
            )
            track_rows = await self.bot.db.fetch_all(
                """
                SELECT track_title, artist, play_count
                FROM user_music_history
                WHERE user_id = $1
                ORDER BY play_count DESC
                LIMIT 5;
                """,
                user_id,
            )
            total = sum(r["plays"] for r in artist_rows) if artist_rows else 0
            return {
                "total_plays": total,
                "top_artists": [r["artist"] for r in artist_rows],
                "top_tracks": [f"{r['track_title']} - {r['artist']}" for r in track_rows],
            }
        except Exception as e:
            logger.debug(f"User taste summary error: {e}")
            return {"total_plays": 0, "top_artists": [], "top_tracks": []}

    async def ingest_spotify_presence(self, member: discord.Member, spotify: discord.Spotify) -> None:
        """Capture live Spotify track from member presence."""
        if not member or member.bot or not spotify:
            return
        title = getattr(spotify, "title", None)
        artist = getattr(spotify, "artist", None)
        if title and artist:
            await self.record_play(
                user_id=member.id,
                guild_id=member.guild.id if member.guild else None,
                track_title=title,
                artist=artist,
                source="spotify_presence",
            )

    async def ingest_message_activity(self, message: discord.Message) -> None:
        """Detect and analyze music queries typed for other bots."""
        if not message.guild or message.author.bot:
            return

        content = message.content.strip()
        lowered = content.lower()

        for prefix in MUSIC_BOT_PREFIXES:
            if lowered.startswith(prefix):
                raw_song = content[len(prefix):].strip()
                if raw_song and len(raw_song) > 2 and not raw_song.startswith("http"):
                    # Record as generic taste discovery
                    await self.record_play(
                        user_id=message.author.id,
                        guild_id=message.guild.id,
                        track_title=raw_song,
                        artist="Discovery Track",
                        source="other_bot",
                    )
                break
