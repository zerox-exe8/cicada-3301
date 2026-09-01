"""
Kyro Discord Bot - Server Auto-Events Manager
Handles database persistence and in-memory caching for Welcome, Leave, and Boost event bindings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyro.EventManager")


class EventManager:
    """Manages server welcome, farewell/leave, and boost configurations."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # Cache keyed by (guild_id, event_type) -> config dict
        self._cache: dict[tuple[int, str], dict[str, Any]] = {}

    async def get_event_config(self, guild_id: int, event_type: str) -> dict[str, Any] | None:
        """Fetch event configuration from memory cache or database."""
        cache_key = (guild_id, event_type.lower())
        if cache_key in self._cache:
            return self._cache[cache_key]

        query = """
            SELECT guild_id, event_type, channel_id, embed_name, message_content,
                   is_enabled, dm_enabled, dm_embed_name, updated_at
            FROM server_events
            WHERE guild_id = $1 AND event_type = $2;
        """
        row = await self.db.fetch_one(query, guild_id, event_type.lower())
        if row:
            data = dict(row)
            self._cache[cache_key] = data
            return data
        return None

    async def save_event_config(
        self,
        guild_id: int,
        event_type: str,
        channel_id: int | None = None,
        embed_name: str | None = None,
        message_content: str | None = None,
        is_enabled: bool = True,
        dm_enabled: bool = False,
        dm_embed_name: str | None = None,
    ) -> bool:
        """Save or update event configuration in database and cache."""
        event_type = event_type.lower()
        query = """
            INSERT INTO server_events (
                guild_id, event_type, channel_id, embed_name, message_content,
                is_enabled, dm_enabled, dm_embed_name, updated_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, CURRENT_TIMESTAMP)
            ON CONFLICT (guild_id, event_type) DO UPDATE SET
                channel_id = EXCLUDED.channel_id,
                embed_name = EXCLUDED.embed_name,
                message_content = EXCLUDED.message_content,
                is_enabled = EXCLUDED.is_enabled,
                dm_enabled = EXCLUDED.dm_enabled,
                dm_embed_name = EXCLUDED.dm_embed_name,
                updated_at = CURRENT_TIMESTAMP;
        """
        try:
            await self.db.execute(
                query,
                guild_id,
                event_type,
                channel_id,
                embed_name,
                message_content,
                is_enabled,
                dm_enabled,
                dm_embed_name,
            )
            self._cache[(guild_id, event_type)] = {
                "guild_id": guild_id,
                "event_type": event_type,
                "channel_id": channel_id,
                "embed_name": embed_name,
                "message_content": message_content,
                "is_enabled": is_enabled,
                "dm_enabled": dm_enabled,
                "dm_embed_name": dm_embed_name,
            }
            logger.info(f"Saved {event_type} event config for guild {guild_id} (embed: '{embed_name}', channel: {channel_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to save {event_type} config for guild {guild_id}: {e}", exc_info=e)
            return False

    async def toggle_event(self, guild_id: int, event_type: str) -> bool | None:
        """Toggle an event's active state. Returns new state, or None if no config exists."""
        event_type = event_type.lower()
        config = await self.get_event_config(guild_id, event_type)
        if not config:
            return None

        new_state = not config.get("is_enabled", True)
        query = """
            UPDATE server_events
            SET is_enabled = $1, updated_at = CURRENT_TIMESTAMP
            WHERE guild_id = $2 AND event_type = $3;
        """
        try:
            await self.db.execute(query, new_state, guild_id, event_type)
            config["is_enabled"] = new_state
            self._cache[(guild_id, event_type)] = config
            return new_state
        except Exception as e:
            logger.error(f"Failed to toggle {event_type} for guild {guild_id}: {e}", exc_info=e)
            return None

    async def delete_event_config(self, guild_id: int, event_type: str) -> bool:
        """Remove event configuration completely."""
        event_type = event_type.lower()
        query = "DELETE FROM server_events WHERE guild_id = $1 AND event_type = $2;"
        try:
            await self.db.execute(query, guild_id, event_type)
            self._cache.pop((guild_id, event_type), None)
            logger.info(f"Deleted {event_type} config for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {event_type} config for guild {guild_id}: {e}", exc_info=e)
            return False
