from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import (
    execute_punishment,
    disarm_dangerous_permissions,
    dispatch_antinuke_log,
    resolve_audit_perpetrator,
    DANGEROUS_PERMISSIONS,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiEveryone")


class AntiEveryoneCog(commands.Cog):
    """Anti-Everyone protection: Detects and disarms dangerous permission escalations on @everyone."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        """Disarm dangerous permissions if escalated on @everyone or roles."""
        guild = after.guild
        if not self.bot.antinuke_mgr.is_enabled(guild.id):
            return

        is_everyone = after.is_default()
        if is_everyone and not self.bot.antinuke_mgr.is_module_enabled(guild.id, "everyone"):
            return
        if not is_everyone and not self.bot.antinuke_mgr.is_module_enabled(guild.id, "role"):
            return

        escalated = []
        for perm in DANGEROUS_PERMISSIONS:
            if not getattr(before.permissions, perm, False) and getattr(after.permissions, perm, False):
                escalated.append(perm)

        if not escalated:
            return

        perpetrator = await resolve_audit_perpetrator(
            guild, discord.AuditLogAction.role_update, target_id=after.id
        )

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "everyone" if is_everyone else "role"):
            return

        # Immediate disarm
        disarmed = await disarm_dangerous_permissions(after)

        action_title = "Anti-Everyone" if is_everyone else "Anti-Role"
        punish_res = await execute_punishment(
            self.bot,
            guild,
            perpetrator,
            action_title,
            f"Escalated [{', '.join(escalated)}] on @{after.name}",
        )

        recovery_msg = f"Disarmed permissions: {', '.join(escalated)}" if disarmed else "Disarm Failed"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            action_title,
            perpetrator,
            punish_res,
            recovery_msg,
            extra=f"Role: `@{after.name}` • Escalated Perms: `{', '.join(escalated)}`",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntiEveryoneCog."""
    await bot.add_cog(AntiEveryoneCog(bot))
