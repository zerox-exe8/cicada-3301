from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, dispatch_antinuke_log, resolve_audit_perpetrator

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiServer")


class AntiServerCog(commands.Cog):
    """Anti-Server protection: Prevents unauthorized guild configuration and identity tampering."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        """Detect and revert unauthorized server tampering."""
        if not self.bot.antinuke_mgr.is_module_enabled(after.id, "guild_update"):
            return

        if before.name == after.name and before.icon == after.icon and before.verification_level == after.verification_level:
            return

        perpetrator = await resolve_audit_perpetrator(
            after, discord.AuditLogAction.guild_update, max_age_seconds=10.0
        )

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(after, perpetrator.id, "guild_update"):
            return

        # Revert server name if changed
        if before.name != after.name:
            try:
                await after.edit(name=before.name, reason="Kyro Antinuke: Server Name Tamper Revert")
            except Exception:
                pass

        punish_res = await execute_punishment(
            self.bot, after, perpetrator, "Anti-Server", "Modified server configuration"
        )

        await dispatch_antinuke_log(
            self.bot,
            after,
            "Anti-Server",
            perpetrator,
            punish_res,
            "Reverted Settings",
            extra=f"Previous Name: `{before.name}`",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntiServerCog."""
    await bot.add_cog(AntiServerCog(bot))
