"""
Kyro Discord Bot - Modular Log Manager
Handles server audit log channel mapping and ultra-fast in-memory caching.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Kyro.LogManager")

LOG_TYPES = ["all", "mod", "message", "member", "server", "voice"]


class LogManager:
    """Manages guild audit logging configurations with memory cache."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        self._cache: dict[int, dict[str, int | None]] = {}

    async def load_cache(self) -> None:
        """Load all guild logging channel settings into memory."""
        records = await self.db.fetch_all("SELECT * FROM guild_logs;")
        for row in records:
            g_id = row["guild_id"]
            self._cache[g_id] = {
                "all": row.get("all_channel_id"),
                "mod": row.get("mod_channel_id"),
                "message": row.get("message_channel_id"),
                "member": row.get("member_channel_id"),
                "server": row.get("server_channel_id"),
                "voice": row.get("voice_channel_id"),
            }
        logger.info(f"Loaded logging settings for {len(self._cache)} guild(s) into memory cache.")

    def get_log_channel(self, guild: discord.Guild, log_type: str) -> discord.TextChannel | None:
        """
        Resolve the target TextChannel for a given log event.
        Falls back to the 'all' channel if specific log type is not individually set.
        """
        settings = self._cache.get(guild.id, {})
        target_id = settings.get(log_type) or settings.get("all")
        if not target_id:
            return None
        return guild.get_channel(target_id)  # Fast in-memory guild cache lookup

    def get_guild_settings(self, guild_id: int) -> dict[str, int | None]:
        """Get copy of all log channel settings for a guild."""
        return self._cache.get(guild_id, {t: None for t in LOG_TYPES})

    async def set_log_channel(self, guild_id: int, log_type: str, channel_id: int | None) -> None:
        """Set or update a specific log channel in cache and SQLite."""
        if log_type not in LOG_TYPES:
            raise ValueError(f"Invalid log type '{log_type}'. Allowed: {', '.join(LOG_TYPES)}")

        if guild_id not in self._cache:
            self._cache[guild_id] = {t: None for t in LOG_TYPES}

        self._cache[guild_id][log_type] = channel_id
        col_name = f"{log_type}_channel_id"

        await self.db.execute(
            f"""
            INSERT INTO guild_logs (guild_id, {col_name})
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET {col_name} = excluded.{col_name};
            """,
            guild_id,
            channel_id,
        )
        logger.info(f"Guild {guild_id}: set {log_type} log channel to {channel_id}")

    async def reset_logs(self, guild_id: int, log_type: str | None = None) -> None:
        """Reset specific log channel or all log channels for a guild."""
        if log_type and log_type != "all_logs":
            if log_type in LOG_TYPES:
                await self.set_log_channel(guild_id, log_type, None)
        else:
            self._cache.pop(guild_id, None)
            await self.db.execute("DELETE FROM guild_logs WHERE guild_id = ?;", guild_id)
            logger.info(f"Guild {guild_id}: cleared all logging channels.")
