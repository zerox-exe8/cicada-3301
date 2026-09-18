"""
Kyro Discord Bot - Sticky Message Manager
Database persistence, in-memory caching, and asynchronous lock control for auto-pinned live notices.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyro.Managers.Sticky")


class StickyManager:
    """Manages channel sticky messages, state persistence, and anti-race locks."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # channel_id -> sticky dict
        self._stickies: dict[int, dict[str, Any]] = {}
        # channel_id -> asyncio.Lock
        self._locks: dict[int, asyncio.Lock] = {}
        # channel_id -> last_dispatched_timestamp
        self._last_post_time: dict[int, float] = {}
        # channel_id -> messages_since_last_post
        self._message_counts: dict[int, int] = {}
        self._global_lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load all enabled sticky messages into memory."""
        try:
            rows = await self.db.fetch_all("SELECT * FROM guild_sticky_messages WHERE is_enabled = TRUE;")
            async with self._global_lock:
                self._stickies.clear()
                for r in rows:
                    cid = int(r["channel_id"])
                    self._stickies[cid] = {
                        "guild_id": int(r["guild_id"]),
                        "content": str(r["content"]),
                        "embed_title": r.get("embed_title"),
                        "embed_color": r.get("embed_color"),
                        "last_message_id": int(r["last_message_id"]) if r.get("last_message_id") else None,
                        "is_enabled": bool(r.get("is_enabled", True)),
                        "created_by": int(r["created_by"]) if r.get("created_by") else None,
                    }
                    if cid not in self._locks:
                        self._locks[cid] = asyncio.Lock()
                    self._message_counts[cid] = 0
                    self._last_post_time[cid] = 0.0

            logger.info(f"Loaded {len(self._stickies)} active sticky message(s) into memory cache.")
        except Exception as e:
            logger.error(f"Failed to load sticky message cache: {e}", exc_info=e)

    def get_sticky(self, channel_id: int) -> Optional[dict[str, Any]]:
        """Retrieve sticky message data for a channel."""
        return self._stickies.get(channel_id)

    def has_sticky(self, channel_id: int) -> bool:
        """Check if channel has an active sticky notice."""
        s = self._stickies.get(channel_id)
        return bool(s and s.get("is_enabled", True))

    def get_guild_stickies(self, guild_id: int) -> list[tuple[int, dict[str, Any]]]:
        """Return all stickies registered in a guild."""
        return [(cid, data) for cid, data in self._stickies.items() if data.get("guild_id") == guild_id]

    def get_lock(self, channel_id: int) -> asyncio.Lock:
        """Get or initialize lock for channel sticky updates."""
        if channel_id not in self._locks:
            self._locks[channel_id] = asyncio.Lock()
        return self._locks[channel_id]

    def increment_and_check_debounce(self, channel_id: int, min_messages: int = 1, min_seconds: float = 2.0) -> bool:
        """
        Rate limit check: returns True if enough time and messages have passed to repost sticky message.
        Prevents Discord 429 gateway rate-limiting during fast typing.
        """
        now = time.time()
        count = self._message_counts.get(channel_id, 0) + 1
        self._message_counts[channel_id] = count
        last_time = self._last_post_time.get(channel_id, 0.0)

        if count >= min_messages and (now - last_time) >= min_seconds:
            return True
        return False

    def reset_debounce(self, channel_id: int) -> None:
        """Reset message count and update post timestamp."""
        self._message_counts[channel_id] = 0
        self._last_post_time[channel_id] = time.time()

    async def set_sticky(
        self,
        channel_id: int,
        guild_id: int,
        content: str,
        embed_title: Optional[str] = None,
        embed_color: Optional[str] = None,
        created_by: Optional[int] = None,
    ) -> None:
        """Create or update a channel sticky notice."""
        query = """
        INSERT INTO guild_sticky_messages (channel_id, guild_id, content, embed_title, embed_color, is_enabled, created_by, updated_at)
        VALUES ($1, $2, $3, $4, $5, TRUE, $6, CURRENT_TIMESTAMP)
        ON CONFLICT (channel_id) DO UPDATE SET
            content = EXCLUDED.content,
            embed_title = EXCLUDED.embed_title,
            embed_color = EXCLUDED.embed_color,
            is_enabled = TRUE,
            created_by = EXCLUDED.created_by,
            updated_at = CURRENT_TIMESTAMP;
        """
        await self.db.execute(query, channel_id, guild_id, content, embed_title, embed_color, created_by)

        async with self._global_lock:
            self._stickies[channel_id] = {
                "guild_id": guild_id,
                "content": content,
                "embed_title": embed_title,
                "embed_color": embed_color,
                "last_message_id": None,
                "is_enabled": True,
                "created_by": created_by,
            }
            if channel_id not in self._locks:
                self._locks[channel_id] = asyncio.Lock()
            self._message_counts[channel_id] = 0
            self._last_post_time[channel_id] = 0.0

    async def update_last_message_id(self, channel_id: int, message_id: int) -> None:
        """Store newly posted sticky message ID."""
        await self.db.execute(
            "UPDATE guild_sticky_messages SET last_message_id = $1 WHERE channel_id = $2;",
            message_id, channel_id
        )
        if channel_id in self._stickies:
            self._stickies[channel_id]["last_message_id"] = message_id

    async def remove_sticky(self, channel_id: int) -> bool:
        """Delete sticky notice from channel."""
        await self.db.execute("DELETE FROM guild_sticky_messages WHERE channel_id = $1;", channel_id)
        async with self._global_lock:
            removed = self._stickies.pop(channel_id, None)
            self._message_counts.pop(channel_id, None)
            self._last_post_time.pop(channel_id, None)
            return removed is not None

    async def toggle_sticky(self, channel_id: int) -> bool:
        """Toggle active status of a sticky message."""
        curr = self._stickies.get(channel_id)
        if not curr:
            return False

        new_status = not curr["is_enabled"]
        await self.db.execute(
            "UPDATE guild_sticky_messages SET is_enabled = $1 WHERE channel_id = $2;",
            new_status, channel_id
        )
        curr["is_enabled"] = new_status
        return new_status
