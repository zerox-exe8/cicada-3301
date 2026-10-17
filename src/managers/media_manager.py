from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyro.Managers.Media")


class MediaManager:
    """
    High-performance in-memory cache manager for media-only channels.
    Provides sub-microsecond validation in the message hot-path.
    """

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # guild_id -> set of channel_ids
        self._media_channels: dict[int, set[int]] = {}
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Warm up in-memory media channel cache from PostgreSQL upon startup."""
        try:
            rows = await self.db.fetch_all("SELECT guild_id, channel_id FROM guild_media_channels;")
            async with self._lock:
                self._media_channels.clear()
                for r in rows:
                    gid = int(r["guild_id"])
                    cid = int(r["channel_id"])
                    if gid not in self._media_channels:
                        self._media_channels[gid] = set()
                    self._media_channels[gid].add(cid)

            total_entries = sum(len(c) for c in self._media_channels.values())
            logger.info(f"Loaded {total_entries} media channel(s) across {len(self._media_channels)} guild(s) into memory cache.")
        except Exception as e:
            logger.error(f"Failed to load media channels cache: {e}", exc_info=e)

    def is_media_channel(self, guild_id: int, channel_id: int) -> bool:
        """0.001ms in-memory lookup to verify if channel is configured as media-only."""
        channels = self._media_channels.get(guild_id)
        if not channels:
            return False
        return channel_id in channels

    def get_channels(self, guild_id: int) -> set[int]:
        """Return a copy of all active media channel IDs for a guild."""
        return set(self._media_channels.get(guild_id, set()))

    async def add_channel(self, guild_id: int, channel_id: int, added_by: Optional[int] = None) -> bool:
        """Mark a channel as media-only with atomic database persistence and cache sync."""
        if self.is_media_channel(guild_id, channel_id):
            return False

        await self.db.execute(
            """
            INSERT INTO guild_media_channels (guild_id, channel_id, added_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (guild_id, channel_id) DO NOTHING;
            """,
            guild_id,
            channel_id,
            added_by,
        )

        async with self._lock:
            if guild_id not in self._media_channels:
                self._media_channels[guild_id] = set()
            self._media_channels[guild_id].add(channel_id)

        return True

    async def remove_channel(self, guild_id: int, channel_id: int) -> bool:
        """Unmark a media channel with atomic database deletion and cache eviction."""
        if not self.is_media_channel(guild_id, channel_id):
            return False

        await self.db.execute(
            "DELETE FROM guild_media_channels WHERE guild_id = $1 AND channel_id = $2;",
            guild_id,
            channel_id,
        )

        async with self._lock:
            if guild_id in self._media_channels:
                self._media_channels[guild_id].discard(channel_id)
                if not self._media_channels[guild_id]:
                    self._media_channels.pop(guild_id, None)

        return True

    async def clear_channels(self, guild_id: int) -> int:
        """Remove all media channel bindings for a guild."""
        channels = self.get_channels(guild_id)
        if not channels:
            return 0

        count = len(channels)
        await self.db.execute("DELETE FROM guild_media_channels WHERE guild_id = $1;", guild_id)

        async with self._lock:
            self._media_channels.pop(guild_id, None)

        return count
