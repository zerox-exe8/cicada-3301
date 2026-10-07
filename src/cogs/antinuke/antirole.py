from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import (
    execute_punishment,
    restore_role,
    dispatch_antinuke_log,
    resolve_audit_perpetrator,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiRole")


class AntiRoleCog(commands.Cog):
    """Anti-Role protection: Intercepts role deletions and mass role spam."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Intercept unauthorized role deletion and auto-recreate."""
        guild = role.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "role_delete"):
            return

        cached = self.bot.antinuke_mgr.get_cached_role(guild.id, role.id)

        perpetrator = await resolve_audit_perpetrator(
            guild, discord.AuditLogAction.role_delete, target_id=role.id
        )

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "role"):
            return

        punish_res = await execute_punishment(
            self.bot, guild, perpetrator, "Anti-Role", f"Deleted @{role.name}"
        )

        recreated = None
        if cached:
            recreated = await restore_role(guild, cached)

        recovery_msg = f"Auto-Recreated @{recreated.name}" if recreated else "Recreation Failed"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Anti-Role",
            perpetrator,
            punish_res,
            recovery_msg,
            extra=f"Target: `@{role.name}` `「{role.id}」`",
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        """Catch mass role creation attacks."""
        guild = role.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "role_create"):
            return

        perpetrator = await resolve_audit_perpetrator(
            guild, discord.AuditLogAction.role_create, target_id=role.id
        )

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "role"):
            return

        is_raid = self.bot.antinuke_mgr.check_rate_limit(
            guild.id, perpetrator.id, "role_create", max_allowed=2, window_seconds=8.0
        )

        if is_raid:
            try:
                await role.delete(reason="Kyro Antinuke: Mass Role Creation Raid Cleanup")
            except Exception:
                pass

            punish_res = await execute_punishment(
                self.bot, guild, perpetrator, "Anti-Role", f"Mass role spam @{role.name}"
            )

            await dispatch_antinuke_log(
                self.bot,
                guild,
                "Anti-Role",
                perpetrator,
                punish_res,
                "Spam Role Deleted",
                extra=f"Role: `@{role.name}`",
            )


async def setup(bot: KyroBot) -> None:
    """Load AntiRoleCog."""
    await bot.add_cog(AntiRoleCog(bot))
