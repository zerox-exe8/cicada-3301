from __future__ import annotations

from typing import Any, Optional
from src.repositories.base import BaseRepository


class MeetingRepository(BaseRepository):
    """Repository managing meeting configurations and logged intelligence sessions in PostgreSQL."""

    async def get_settings(self, guild_id: int) -> Optional[dict[str, Any]]:
        """Fetch guild meeting configuration."""
        return await self.fetch_one("SELECT * FROM meeting_settings WHERE guild_id = $1;", guild_id)

    async def upsert_settings(
        self,
        guild_id: int,
        enabled: bool = True,
        channel_id: int | None = None,
        privacy_mode: str = "locked",
        modules: str = "",
    ) -> None:
        """Upsert full meeting configuration."""
        query = """
        INSERT INTO meeting_settings (guild_id, enabled, channel_id, privacy_mode, modules)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT(guild_id) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            channel_id = EXCLUDED.channel_id,
            privacy_mode = EXCLUDED.privacy_mode,
            modules = EXCLUDED.modules;
        """
        await self.execute(query, guild_id, enabled, channel_id, privacy_mode, modules)

    async def set_enabled(self, guild_id: int, enabled: bool) -> None:
        """Toggle meeting functionality on or off for a guild."""
        query = """
        INSERT INTO meeting_settings (guild_id, enabled)
        VALUES ($1, $2)
        ON CONFLICT(guild_id) DO UPDATE SET enabled = EXCLUDED.enabled;
        """
        await self.execute(query, guild_id, enabled)

    async def set_channel(self, guild_id: int, channel_id: int | None, privacy_mode: str = "locked") -> None:
        """Ensure designated executive report channel for a guild."""
        query = """
        INSERT INTO meeting_settings (guild_id, enabled, channel_id, privacy_mode)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT(guild_id) DO UPDATE SET
            channel_id = EXCLUDED.channel_id,
            privacy_mode = EXCLUDED.privacy_mode;
        """
        await self.execute(query, guild_id, True, channel_id, privacy_mode)

    async def save_session(
        self,
        guild_id: int,
        channel_id: int,
        host_id: int,
        duration_seconds: int,
        speaker_count: int,
        summary: str,
        decisions: str,
        action_items: str,
    ) -> None:
        """Record meeting summary and actionable intelligence."""
        query = """
        INSERT INTO meeting_sessions (guild_id, channel_id, host_id, duration_seconds, speaker_count, summary, decisions, action_items)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
        """
        await self.execute(
            query,
            guild_id,
            channel_id,
            host_id,
            duration_seconds,
            speaker_count,
            summary,
            decisions,
            action_items,
        )

    async def get_total_sessions_count(self, guild_id: int) -> int:
        """Count total historical meeting sessions logged for a guild."""
        row = await self.fetch_one(
            "SELECT COUNT(*) as count FROM meeting_sessions WHERE guild_id = $1;", guild_id
        )
        return int(row["count"]) if row else 0

    # ── Meeting Schedule Operations ──

    async def add_schedule(
        self,
        guild_id: int,
        voice_channel_id: int,
        start_time: str,
        end_time: str,
        created_by: int | None = None,
    ) -> int:
        """Add a recurring daily meeting schedule for a voice channel."""
        query = """
        INSERT INTO meeting_schedules (guild_id, voice_channel_id, start_time, end_time, created_by)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id;
        """
        row = await self.fetch_one(query, guild_id, voice_channel_id, start_time, end_time, created_by)
        return int(row["id"]) if row else 0

    async def get_schedules(self, guild_id: int) -> list[dict[str, Any]]:
        """Fetch all enabled schedules for a guild."""
        query = "SELECT * FROM meeting_schedules WHERE guild_id = $1 AND enabled = TRUE ORDER BY id ASC;"
        return await self.fetch_all(query, guild_id)

    async def get_all_schedules(self, guild_id: int) -> list[dict[str, Any]]:
        """Fetch all schedules for a guild."""
        query = "SELECT * FROM meeting_schedules WHERE guild_id = $1 ORDER BY id ASC;"
        return await self.fetch_all(query, guild_id)

    async def get_all_active_schedules_global(self) -> list[dict[str, Any]]:
        """Fetch all globally enabled schedules across all guilds."""
        query = "SELECT * FROM meeting_schedules WHERE enabled = TRUE;"
        return await self.fetch_all(query)

    async def delete_schedule(self, schedule_id: int, guild_id: int) -> bool:
        """Delete a schedule entry."""
        query = "DELETE FROM meeting_schedules WHERE id = $1 AND guild_id = $2;"
        await self.execute(query, schedule_id, guild_id)
        return True
