"""
Cicada 3301 Discord Bot - Permission Manager
Handles Owner and Developer authorization levels and custom decorators.
"""

from __future__ import annotations

import logging
from typing import Callable, TYPE_CHECKING
import discord
from discord.ext import commands

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Cicada.PermissionManager")


class PermissionManager:
    """Manages bot developers and owner authorization checks."""

    def __init__(self, bot: commands.Bot, db: BaseDatabase) -> None:
        self.bot = bot
        self.db = db
        self._developer_ids: set[int] = set()

    async def load_cache(self) -> None:
        """Load registered developer IDs and owner ID into memory."""
        try:
            app_info = await self.bot.application_info()
            if app_info.team:
                self.bot.owner_ids = {m.id for m in app_info.team.members}
            else:
                self.bot.owner_id = app_info.owner.id
        except Exception:
            pass

        records = await self.db.fetch_all("SELECT user_id FROM system_developers;")
        self._developer_ids = {row["user_id"] for row in records}
        logger.info(f"Loaded {len(self._developer_ids)} developer ID(s) into memory cache.")

    async def is_owner(self, user_id: int) -> bool:
        """Check if a user is the primary Bot Owner."""
        if not self.bot.owner_id and not self.bot.owner_ids:
            try:
                app_info = await self.bot.application_info()
                if app_info.team:
                    self.bot.owner_ids = {m.id for m in app_info.team.members}
                else:
                    self.bot.owner_id = app_info.owner.id
            except Exception:
                pass

        if self.bot.owner_ids:
            return user_id in self.bot.owner_ids
        return user_id == self.bot.owner_id

    async def is_developer(self, user_id: int) -> bool:
        """Check if a user is either a Bot Owner or registered Developer."""
        if await self.is_owner(user_id):
            return True
        return user_id in self._developer_ids

    async def add_developer(self, user_id: int, added_by: int) -> None:
        """Add a developer to memory cache and database."""
        self._developer_ids.add(user_id)
        await self.db.execute(
            "INSERT OR IGNORE INTO system_developers (user_id, added_by) VALUES (?, ?);",
            user_id,
            added_by,
        )
        logger.info(f"Added developer ID: {user_id}")

    async def remove_developer(self, user_id: int) -> None:
        """Remove a developer from memory cache and database."""
        self._developer_ids.discard(user_id)
        await self.db.execute(
            "DELETE FROM system_developers WHERE user_id = ?;",
            user_id,
        )
        logger.info(f"Removed developer ID: {user_id}")


# ==========================================
# Custom Command Check Decorators
# ==========================================

def is_owner() -> Callable:
    """Command check: Only accessible by Bot Owner(s)."""
    async def predicate(ctx: commands.Context) -> bool:
        bot: Any = ctx.bot
        perm_mgr: PermissionManager = bot.perm_mgr
        if not await perm_mgr.is_owner(ctx.author.id):
            raise commands.NotOwner("This command is restricted to the Bot Owner.")
        return True
    return commands.check(predicate)


def is_developer() -> Callable:
    """Command check: Accessible by Bot Owners and registered Developers."""
    async def predicate(ctx: commands.Context) -> bool:
        bot: Any = ctx.bot
        perm_mgr: PermissionManager = bot.perm_mgr
        if not await perm_mgr.is_developer(ctx.author.id):
            raise commands.CheckFailure("This command is restricted to Bot Developers.")
        return True
    return commands.check(predicate)
