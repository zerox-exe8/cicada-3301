from __future__ import annotations

from typing import Any, Optional
from src.repositories.base import BaseRepository


class SystemRepository(BaseRepository):
    """Repository managing bot-wide system state, developer access, and blacklists."""

    # ─── SYSTEM STATE ──────────────────────────────────────────────────────────

    async def get_state(self, key: str) -> Optional[str]:
        """Fetch system state value for key."""
        row = await self.fetch_one("SELECT value FROM system_state WHERE key = ?;", key)
        return row.get("value") if row else None

    async def set_state(self, key: str, value: str) -> None:
        """Upsert system state key-value."""
        query = """
            INSERT INTO system_state (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
        """
        await self.execute(query, key, value)

    # ─── BLACKLISTS ────────────────────────────────────────────────────────────

    async def get_all_blacklists(self) -> list[dict[str, Any]]:
        """Fetch all blacklist records."""
        return await self.fetch_all("SELECT target_id, target_type, reason, added_by, created_at FROM system_blacklists;")

    async def add_blacklist(self, target_id: int, target_type: str, reason: str, added_by: int) -> None:
        """Upsert blacklist record."""
        query = """
            INSERT INTO system_blacklists (target_id, target_type, reason, added_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(target_id) DO UPDATE SET reason = excluded.reason;
        """
        await self.execute(query, target_id, target_type, reason, added_by)

    async def remove_blacklist(self, target_id: int) -> None:
        """Delete blacklist record."""
        await self.execute("DELETE FROM system_blacklists WHERE target_id = ?;", target_id)

    # ─── DEVELOPERS ────────────────────────────────────────────────────────────

    async def get_all_developers(self) -> list[dict[str, Any]]:
        """Fetch all system developers."""
        return await self.fetch_all("SELECT user_id, added_by, created_at FROM system_developers;")

    async def add_developer(self, user_id: int, added_by: int) -> None:
        """Add developer record."""
        query = """
            INSERT INTO system_developers (user_id, added_by)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO NOTHING;
        """
        await self.execute(query, user_id, added_by)

    async def remove_developer(self, user_id: int) -> None:
        """Remove developer record."""
        await self.execute("DELETE FROM system_developers WHERE user_id = ?;", user_id)

    # ─── NO-PREFIX ─────────────────────────────────────────────────────────────

    async def get_all_no_prefix_users(self) -> list[dict[str, Any]]:
        """Fetch all users authorized for no-prefix invocation."""
        return await self.fetch_all("SELECT user_id, added_by, created_at FROM system_no_prefix;")

    async def add_no_prefix_user(self, user_id: int, added_by: int) -> None:
        """Authorize user for no-prefix invocation."""
        query = """
            INSERT INTO system_no_prefix (user_id, added_by)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO NOTHING;
        """
        await self.execute(query, user_id, added_by)

    async def remove_no_prefix_user(self, user_id: int) -> None:
        """Revoke user no-prefix authorization."""
        await self.execute("DELETE FROM system_no_prefix WHERE user_id = ?;", user_id)
