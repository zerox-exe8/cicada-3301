from __future__ import annotations

from typing import Any, Optional
from src.repositories.base import BaseRepository


class GuildRepository(BaseRepository):
    """Repository managing guild configuration records in PostgreSQL."""

    async def get_all_settings(self) -> list[dict[str, Any]]:
        """Fetch all guild configurations for initial cache hydration."""
        return await self.fetch_all("SELECT guild_id, prefix, disabled_commands FROM guild_settings;")

    async def get_settings(self, guild_id: int) -> Optional[dict[str, Any]]:
        """Fetch single guild configuration."""
        return await self.fetch_one("SELECT * FROM guild_settings WHERE guild_id = ?;", guild_id)

    async def upsert_prefix(self, guild_id: int, prefix: str) -> None:
        """Upsert prefix for a guild."""
        query = """
            INSERT INTO guild_settings (guild_id, prefix)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix;
        """
        await self.execute(query, guild_id, prefix)

    async def update_disabled_commands(self, guild_id: int, disabled_commands: str) -> None:
        """Update disabled commands string for a guild."""
        query = """
            INSERT INTO guild_settings (guild_id, disabled_commands)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET disabled_commands = excluded.disabled_commands;
        """
        await self.execute(query, guild_id, disabled_commands)
