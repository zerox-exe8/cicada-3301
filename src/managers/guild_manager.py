"""
Kyro Discord Bot - Guild Manager
Handles per-server custom prefixes and settings with in-memory caching.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from src.core.config import Config
from src.core.cache import MicrosecondCache

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Kyro.GuildManager")


class GuildManager:
    """Manages guild-specific configurations with zero-latency in-memory cache."""

    def __init__(self, db: BaseDatabase, cache: MicrosecondCache | None = None) -> None:
        self.db = db
        self.cache = cache or MicrosecondCache()

    async def load_cache(self) -> None:
        """Load all guild settings into memory on bot startup."""
        records = await self.db.fetch_all("SELECT guild_id, prefix, disabled_commands FROM guild_settings;")
        for row in records:
            g_id = row["guild_id"]
            if row.get("prefix"):
                self.cache.set_prefix(g_id, row["prefix"])

            disabled = row.get("disabled_commands") or ""
            if disabled:
                self.cache.set_disabled_commands(g_id, set(disabled.split(",")))

        logger.info(f"Loaded {len(self.cache.prefixes)} guild prefix(es) into L1 microsecond cache.")

    def get_prefix(self, guild_id: int | None) -> str:
        """Retrieve prefix from L1 memory cache (<0.01ms)."""
        return self.cache.get_prefix(guild_id, Config.DEFAULT_PREFIX)

    async def set_prefix(self, guild_id: int, new_prefix: str) -> None:
        """Update guild prefix in database and L1 memory cache immediately."""
        self.cache.set_prefix(guild_id, new_prefix)
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
        self.cache.reset_prefix(guild_id)
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
        """Check if a command is disabled in a guild (<0.01ms)."""
        return self.cache.is_command_disabled(guild_id, command_name)
