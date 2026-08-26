"""
Hertz Discord Bot - Blacklist Manager
Handles global blocking of malicious users and servers with in-memory caching.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Hertz.BlacklistManager")


class BlacklistManager:
    """Manages global blacklist of abusive users and guilds."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        self._blacklisted_users: dict[int, str] = {}
        self._blacklisted_guilds: dict[int, str] = {}

    async def load_cache(self) -> None:
        """Load all blacklisted entities into memory."""
        records = await self.db.fetch_all("SELECT target_id, target_type, reason FROM system_blacklists;")
        for row in records:
            t_id = row["target_id"]
            t_type = row.get("target_type", "user")
            reason = row.get("reason", "Violation of bot terms")
            if t_type == "guild":
                self._blacklisted_guilds[t_id] = reason
            else:
                self._blacklisted_users[t_id] = reason

        logger.info(
            f"Loaded {len(self._blacklisted_users)} user(s) and "
            f"{len(self._blacklisted_guilds)} guild(s) into blacklist cache."
        )

    def is_user_blacklisted(self, user_id: int) -> bool:
        """Check if a user is globally blacklisted."""
        return user_id in self._blacklisted_users

    def is_guild_blacklisted(self, guild_id: int | None) -> bool:
        """Check if a server is globally blacklisted."""
        if not guild_id:
            return False
        return guild_id in self._blacklisted_guilds

    def get_blacklist_reason(self, target_id: int) -> str:
        """Retrieve reason for blacklist."""
        return (
            self._blacklisted_users.get(target_id)
            or self._blacklisted_guilds.get(target_id)
            or "Violation of bot usage terms"
        )

    async def add_blacklist(
        self, target_id: int, target_type: str, reason: str, added_by: int
    ) -> None:
        """Add user or guild to blacklist in memory and DB."""
        if target_type == "guild":
            self._blacklisted_guilds[target_id] = reason
        else:
            self._blacklisted_users[target_id] = reason

        await self.db.execute(
            """
            INSERT INTO system_blacklists (target_id, target_type, reason, added_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(target_id) DO UPDATE SET reason = excluded.reason;
            """,
            target_id,
            target_type,
            reason,
            added_by,
        )
        logger.warning(f"Globally blacklisted {target_type} {target_id}: {reason}")

    async def remove_blacklist(self, target_id: int) -> None:
        """Remove user or guild from blacklist."""
        self._blacklisted_users.pop(target_id, None)
        self._blacklisted_guilds.pop(target_id, None)
        await self.db.execute(
            "DELETE FROM system_blacklists WHERE target_id = ?;",
            target_id,
        )
        logger.info(f"Removed {target_id} from blacklist.")
