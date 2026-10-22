from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.repositories.system_repo import SystemRepository

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Kyro.SystemManager")


class SystemManager:
    """Controls bot-wide maintenance mode and command enablement via SystemRepository."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        self.repo: SystemRepository = SystemRepository(db)
        self.maintenance_mode: bool = False
        self.maintenance_reason: str = "System maintenance in progress."
        self._disabled_commands: set[str] = set()

    async def load_cache(self) -> None:
        """Load maintenance state and disabled commands from DB via repository."""
        m_val = await self.repo.get_state("maintenance")
        if m_val:
            self.maintenance_mode = m_val == "1"

        r_val = await self.repo.get_state("maintenance_reason")
        if r_val:
            self.maintenance_reason = r_val

        d_val = await self.repo.get_state("disabled_commands")
        if d_val:
            self._disabled_commands = set(d_val.split(","))

        logger.info(
            f"System State Loaded: Maintenance={self.maintenance_mode}, "
            f"Disabled Commands={len(self._disabled_commands)}"
        )

    async def set_maintenance(self, enabled: bool, reason: str = "System maintenance in progress.") -> None:
        """Toggle maintenance mode on or off via repository."""
        self.maintenance_mode = enabled
        self.maintenance_reason = reason

        val = "1" if enabled else "0"
        await self.repo.set_state("maintenance", val)
        await self.repo.set_state("maintenance_reason", reason)
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
        await self.repo.set_state("disabled_commands", val)
