"""
Kyro Discord Bot - Temp Voice Manager
High-performance database persistence and memory caching for Dynamic Temp Voice channels (Join-to-Create).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional
from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyro.Managers.TempVoice")


class TempVoiceManager:
    """Manager handling join-to-create voice settings and active temporary channel lifecycle."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # guild_id -> settings dict
        self._guild_settings: dict[int, dict[str, Any]] = {}
        # master_channel_id -> guild_id
        self._master_to_guild: dict[int, int] = {}
        # channel_id -> active channel metadata dict
        self._active_channels: dict[int, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load all guild temp voice settings and active channels into memory."""
        try:
            settings_rows = await self.db.fetch_all("SELECT * FROM guild_temp_voice_settings;")
            channels_rows = await self.db.fetch_all("SELECT * FROM active_temp_voice_channels;")

            async with self._lock:
                self._guild_settings.clear()
                self._master_to_guild.clear()
                for r in settings_rows:
                    gid = int(r["guild_id"])
                    mid = int(r["master_channel_id"])
                    self._guild_settings[gid] = {
                        "category_id": int(r["category_id"]),
                        "master_channel_id": mid,
                        "default_name_format": str(r.get("default_name_format") or "{user}'s Room"),
                        "default_user_limit": int(r.get("default_user_limit") or 0),
                    }
                    self._master_to_guild[mid] = gid

                self._active_channels.clear()
                for c in channels_rows:
                    cid = int(c["channel_id"])
                    self._active_channels[cid] = {
                        "guild_id": int(c["guild_id"]),
                        "owner_id": int(c["owner_id"]),
                        "control_message_id": int(c["control_message_id"]) if c.get("control_message_id") else None,
                        "is_locked": bool(c.get("is_locked", False)),
                        "is_hidden": bool(c.get("is_hidden", False)),
                    }

            logger.info(
                f"Loaded {len(self._guild_settings)} temp voice guild configuration(s) and "
                f"{len(self._active_channels)} active temp voice channel(s)."
            )
        except Exception as e:
            logger.error(f"Failed to load temp voice cache: {e}", exc_info=e)

    def get_settings(self, guild_id: int) -> Optional[dict[str, Any]]:
        """Retrieve guild temp voice configuration from memory."""
        return self._guild_settings.get(guild_id)

    def get_guild_by_master(self, master_channel_id: int) -> Optional[int]:
        """Check if channel ID is a registered master Join-to-Create voice channel."""
        return self._master_to_guild.get(master_channel_id)

    def is_temp_channel(self, channel_id: int) -> bool:
        """Check if a voice channel is an active temporary room."""
        return channel_id in self._active_channels

    def get_channel_data(self, channel_id: int) -> Optional[dict[str, Any]]:
        """Get state of an active temporary voice channel."""
        return self._active_channels.get(channel_id)

    def get_all_active_channels(self) -> list[tuple[int, dict[str, Any]]]:
        """Return all active temp channels for startup audits."""
        return list(self._active_channels.items())

    async def set_settings(
        self,
        guild_id: int,
        category_id: int,
        master_channel_id: int,
        default_name_format: str = "{user}'s Room",
        default_user_limit: int = 0,
    ) -> None:
        """Save or update guild temp voice configuration."""
        query = """
        INSERT INTO guild_temp_voice_settings (guild_id, category_id, master_channel_id, default_name_format, default_user_limit)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (guild_id) DO UPDATE SET
            category_id = EXCLUDED.category_id,
            master_channel_id = EXCLUDED.master_channel_id,
            default_name_format = EXCLUDED.default_name_format,
            default_user_limit = EXCLUDED.default_user_limit;
        """
        await self.db.execute(query, guild_id, category_id, master_channel_id, default_name_format, default_user_limit)

        async with self._lock:
            # Clean old master mapping if changed
            old_conf = self._guild_settings.get(guild_id)
            if old_conf and old_conf["master_channel_id"] in self._master_to_guild:
                del self._master_to_guild[old_conf["master_channel_id"]]

            self._guild_settings[guild_id] = {
                "category_id": category_id,
                "master_channel_id": master_channel_id,
                "default_name_format": default_name_format,
                "default_user_limit": default_user_limit,
            }
            self._master_to_guild[master_channel_id] = guild_id

    async def disable_settings(self, guild_id: int) -> None:
        """Remove temp voice configuration for a guild."""
        await self.db.execute("DELETE FROM guild_temp_voice_settings WHERE guild_id = $1;", guild_id)
        async with self._lock:
            old = self._guild_settings.pop(guild_id, None)
            if old and old["master_channel_id"] in self._master_to_guild:
                del self._master_to_guild[old["master_channel_id"]]

    async def register_temp_channel(
        self,
        channel_id: int,
        guild_id: int,
        owner_id: int,
        control_message_id: Optional[int] = None,
    ) -> None:
        """Register newly created temporary channel."""
        query = """
        INSERT INTO active_temp_voice_channels (channel_id, guild_id, owner_id, control_message_id)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (channel_id) DO NOTHING;
        """
        await self.db.execute(query, channel_id, guild_id, owner_id, control_message_id)
        async with self._lock:
            self._active_channels[channel_id] = {
                "guild_id": guild_id,
                "owner_id": owner_id,
                "control_message_id": control_message_id,
                "is_locked": False,
                "is_hidden": False,
            }

    async def update_control_message(self, channel_id: int, message_id: int) -> None:
        """Save message ID of the interactive control panel."""
        await self.db.execute(
            "UPDATE active_temp_voice_channels SET control_message_id = $1 WHERE channel_id = $2;",
            message_id, channel_id
        )
        async with self._lock:
            if channel_id in self._active_channels:
                self._active_channels[channel_id]["control_message_id"] = message_id

    async def update_channel_state(
        self,
        channel_id: int,
        is_locked: Optional[bool] = None,
        is_hidden: Optional[bool] = None,
    ) -> None:
        """Update locked or hidden flags in database and cache."""
        async with self._lock:
            if channel_id not in self._active_channels:
                return
            curr = self._active_channels[channel_id]
            if is_locked is not None:
                curr["is_locked"] = is_locked
            if is_hidden is not None:
                curr["is_hidden"] = is_hidden

        query = """
        UPDATE active_temp_voice_channels
        SET is_locked = $1, is_hidden = $2
        WHERE channel_id = $3;
        """
        await self.db.execute(query, curr["is_locked"], curr["is_hidden"], channel_id)

    async def transfer_ownership(self, channel_id: int, new_owner_id: int) -> None:
        """Transfer room ownership to a new member."""
        await self.db.execute(
            "UPDATE active_temp_voice_channels SET owner_id = $1 WHERE channel_id = $2;",
            new_owner_id, channel_id
        )
        async with self._lock:
            if channel_id in self._active_channels:
                self._active_channels[channel_id]["owner_id"] = new_owner_id

    async def unregister_temp_channel(self, channel_id: int) -> None:
        """Remove temporary channel from database and cache when deleted."""
        await self.db.execute("DELETE FROM active_temp_voice_channels WHERE channel_id = $1;", channel_id)
        async with self._lock:
            self._active_channels.pop(channel_id, None)
