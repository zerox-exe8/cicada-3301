from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

import discord
from discord.ext import commands

from src.core.config import Config

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Kyro.PermissionManager")


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
                self.bot.owner_ids = {app_info.owner.id}
        except Exception as e:
            logger.warning(f"Could not load application info from Discord API: {e}")

        if not hasattr(self.bot, "owner_ids") or not self.bot.owner_ids:
            self.bot.owner_ids = set()
        if Config.OWNER_IDS:
            self.bot.owner_ids.update(Config.OWNER_IDS)
        else:
            logger.warning("OWNER_IDS environment variable is empty. Owner privileges default strictly to Discord application owner/team.")

        if not self.bot.owner_ids:
            logger.warning("No owner IDs configured or detected! Owner privileges and developer execution tools are completely disabled.")

        records = await self.db.fetch_all("SELECT user_id FROM system_developers;")
        self._developer_ids = {row["user_id"] for row in records}
        if Config.DEVELOPER_IDS:
            self._developer_ids.update(Config.DEVELOPER_IDS)
        logger.info(
            f"Loaded {len(self._developer_ids)} developer ID(s) and {len(self.bot.owner_ids)} owner ID(s) into memory."
        )

    def is_owner_sync(self, user_id: int) -> bool:
        """Fast, synchronous in-memory owner check (0ns latency, zero API calls)."""
        if not user_id:
            return False
        if user_id in Config.OWNER_IDS:
            return True
        owner_ids = getattr(self.bot, "owner_ids", None)
        if owner_ids and user_id in owner_ids:
            return True
        owner_id = getattr(self.bot, "owner_id", None)
        if owner_id and user_id == owner_id:
            return True
        return False

    def is_developer_sync(self, user_id: int) -> bool:
        """Fast, synchronous in-memory developer check (0ns latency, zero API calls)."""
        if not user_id:
            return False
        if self.is_owner_sync(user_id):
            return True
        if user_id in Config.DEVELOPER_IDS:
            return True
        if user_id in self._developer_ids:
            return True
        return False

    async def is_owner(self, user_id: int) -> bool:
        """Check if a user is the primary Bot Owner in memory."""
        return self.is_owner_sync(user_id)

    async def is_developer(self, user_id: int) -> bool:
        """Check if a user is either a Bot Owner or registered Developer."""
        return self.is_developer_sync(user_id)

    async def add_developer(self, user_id: int, added_by: int) -> None:
        """Add a developer to memory cache and database."""
        self._developer_ids.add(user_id)
        await self.db.execute(
            "INSERT INTO system_developers (user_id, added_by) VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING;",
            user_id,
            added_by,
        )
        logger.info(f"Added developer ID: {user_id}")

    async def remove_developer(self, user_id: int) -> None:
        """Remove a developer from memory cache and database."""
        self._developer_ids.discard(user_id)
        await self.db.execute(
            "DELETE FROM system_developers WHERE user_id = $1;",
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
