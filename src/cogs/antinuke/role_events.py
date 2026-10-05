from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import (
    execute_punishment,
    restore_role,
    disarm_dangerous_permissions,
    dispatch_antinuke_log,
    DANGEROUS_PERMISSIONS,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.RoleEvents")


class AntinukeRoleCog(commands.Cog):
    """Event listeners for role deletion, dangerous permission escalation, and role spam."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        """Intercept unauthorized role deletion and restore."""
        guild = role.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "role"):
            return

        cached = self.bot.antinuke_mgr.get_cached_role(guild.id, role.id)

        await asyncio.sleep(0.3)
        perpetrator: discord.Member | discord.User | None = None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.role_delete, limit=1):
                if entry.target and entry.target.id == role.id:
                    perpetrator = entry.user
                    break
        except Exception:
            pass

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "role"):
            return

        punish_res = await execute_punishment(
            self.bot, guild, perpetrator, "Role Delete", f"Deleted @{role.name}"
        )

        recreated = None
        if cached:
            recreated = await restore_role(guild, cached)

        recovery_msg = f"Auto-Recreated @{recreated.name}" if recreated else "Recreation Failed"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Role Deletion Intercepted",
            perpetrator,
            punish_res,
            recovery_msg,
            extra=f"Target: `@{role.name}` `「{role.id}」`",
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        """Catch mass role creation attacks."""
        guild = role.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "role"):
            return

        await asyncio.sleep(0.3)
        perpetrator: discord.Member | discord.User | None = None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.role_create, limit=1):
                if entry.target and entry.target.id == role.id:
                    perpetrator = entry.user
                    break
        except Exception:
            pass

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
                self.bot, guild, perpetrator, "Mass Role Creation", f"Created spam role @{role.name}"
            )

            await dispatch_antinuke_log(
                self.bot,
                guild,
                "Mass Role Creation Raid",
                perpetrator,
                punish_res,
                "Spam Role Deleted",
                extra=f"Role: `@{role.name}`",
            )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        """Intercept dangerous permission escalation (especially on @everyone)."""
        guild = after.guild
        if not self.bot.antinuke_mgr.is_enabled(guild.id):
            return

        # Check if new dangerous permissions were granted
        escalated = []
        for perm in DANGEROUS_PERMISSIONS:
            if not getattr(before.permissions, perm, False) and getattr(after.permissions, perm, False):
                escalated.append(perm)

        if not escalated:
            return

        # Is @everyone escalation?
        is_everyone = after.is_default()
        if is_everyone and not self.bot.antinuke_mgr.is_module_enabled(guild.id, "everyone"):
            return
        if not is_everyone and not self.bot.antinuke_mgr.is_module_enabled(guild.id, "role"):
            return

        await asyncio.sleep(0.3)
        perpetrator: discord.Member | discord.User | None = None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.role_update, limit=1):
                if entry.target and entry.target.id == after.id:
                    perpetrator = entry.user
                    break
        except Exception:
            pass

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "role"):
            return

        # Immediate disarm: Strip dangerous permissions back off
        disarmed = await disarm_dangerous_permissions(after)

        # Punish attacker
        punish_res = await execute_punishment(
            self.bot,
            guild,
            perpetrator,
            "Permission Escalation Attack",
            f"Granted [{', '.join(escalated)}] to @{after.name}",
        )

        recovery_msg = f"Disarmed permissions: {', '.join(escalated)}" if disarmed else "Disarm Failed"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Role Permission Escalation Intercepted",
            perpetrator,
            punish_res,
            recovery_msg,
            extra=f"Target: `@{after.name}` • Escalated Perms: `{', '.join(escalated)}`",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntinukeRoleCog."""
    await bot.add_cog(AntinukeRoleCog(bot))
