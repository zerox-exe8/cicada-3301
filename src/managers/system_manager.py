"""
Hertz Discord Bot - System Manager
Handles Maintenance Mode and Global Command Killswitches.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Hertz.SystemManager")


class SystemManager:
    """Controls bot-wide maintenance mode and command enablement."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        self.maintenance_mode: bool = False
        self.maintenance_reason: str = "System maintenance in progress."
        self._disabled_commands: set[str] = set()

    async def load_cache(self) -> None:
        """Load maintenance state and disabled commands from DB."""
        m_state = await self.db.fetch_one("SELECT value FROM system_state WHERE key = 'maintenance';")
        if m_state and m_state.get("value"):
            self.maintenance_mode = m_state["value"] == "1"

        r_state = await self.db.fetch_one("SELECT value FROM system_state WHERE key = 'maintenance_reason';")
        if r_state and r_state.get("value"):
            self.maintenance_reason = r_state["value"]

        d_state = await self.db.fetch_one("SELECT value FROM system_state WHERE key = 'disabled_commands';")
        if d_state and d_state.get("value"):
            self._disabled_commands = set(d_state["value"].split(","))

        logger.info(
            f"System State Loaded: Maintenance={self.maintenance_mode}, "
            f"Disabled Commands={len(self._disabled_commands)}"
        )

    async def set_maintenance(self, enabled: bool, reason: str = "System maintenance in progress.") -> None:
        """Toggle maintenance mode on or off."""
        self.maintenance_mode = enabled
        self.maintenance_reason = reason

        val = "1" if enabled else "0"
        await self.db.execute(
            "INSERT INTO system_state (key, value) VALUES ('maintenance', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
            val,
        )
        await self.db.execute(
            "INSERT INTO system_state (key, value) VALUES ('maintenance_reason', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
            reason,
        )
        logger.warning(f"Maintenance mode set to {enabled}: {reason}")

    async def disable_command(self, command_name: str) -> None:
        """Globally disable a command."""
        self._disabled_commands.add(command_name.lower())
        await self._save_disabled_commands()

    async def enable_command(self, command_name: str) -> None:
        """Globally re-enable a command."""
        self._disabled_commands.discard(command_name.lower())
        await self._save_disabled_commands()

    def is_command_disabled(self, command_name: str) -> bool:
        """Check if a command is globally disabled."""
        return command_name.lower() in self._disabled_commands

    async def _save_disabled_commands(self) -> None:
        val = ",".join(self._disabled_commands)
        await self.db.execute(
            "INSERT INTO system_state (key, value) VALUES ('disabled_commands', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value;",
            val,
        )
