"""
Kyro Discord Bot - Guild Manager
Handles per-server custom prefixes and settings with in-memory caching.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from src.core.config import Config

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Kyro.GuildManager")


class GuildManager:
    """Manages guild-specific configurations with zero-latency in-memory cache."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        self._prefix_cache: dict[int, str] = {}
        self._disabled_commands_cache: dict[int, set[str]] = {}

    async def load_cache(self) -> None:
        """Load all guild settings into memory on bot startup."""
        records = await self.db.fetch_all("SELECT guild_id, prefix, disabled_commands FROM guild_settings;")
        for row in records:
            g_id = row["guild_id"]
            if row.get("prefix"):
                self._prefix_cache[g_id] = row["prefix"]
            
            disabled = row.get("disabled_commands") or ""
            if disabled:
                self._disabled_commands_cache[g_id] = set(disabled.split(","))

        logger.info(f"Loaded {len(self._prefix_cache)} guild prefix(es) into memory cache.")

    def get_prefix(self, guild_id: int | None) -> str:
        """Retrieve prefix from memory cache (<1ms)."""
        if not guild_id:
            return Config.DEFAULT_PREFIX
        return self._prefix_cache.get(guild_id, Config.DEFAULT_PREFIX)

    async def set_prefix(self, guild_id: int, new_prefix: str) -> None:
        """Update guild prefix in database and memory cache."""
        self._prefix_cache[guild_id] = new_prefix
        await self.db.execute(
            """
            INSERT INTO guild_settings (guild_id, prefix)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix;
            """,
            guild_id,
            new_prefix,
        )
        logger.info(f"Guild {guild_id} prefix updated to '{new_prefix}'")

    async def reset_prefix(self, guild_id: int) -> None:
        """Reset guild prefix to bot default."""
        self._prefix_cache.pop(guild_id, None)
        await self.db.execute(
            """
            INSERT INTO guild_settings (guild_id, prefix)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix;
            """,
            guild_id,
            Config.DEFAULT_PREFIX,
        )
        logger.info(f"Guild {guild_id} prefix reset to default '{Config.DEFAULT_PREFIX}'")

    def is_command_disabled(self, guild_id: int | None, command_name: str) -> bool:
        """Check if a command is disabled in a guild."""
        if not guild_id:
            return False
        return command_name.lower() in self._disabled_commands_cache.get(guild_id, set())
