from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import (
    execute_punishment,
    dispatch_antinuke_log,
    resolve_audit_perpetrator,
    DANGEROUS_PERMISSIONS,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiMemberRole")


class AntiMemberRoleCog(commands.Cog):
    """Anti-Member Role protection: Intercepts unauthorized assignment of dangerous administrative roles."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Detect and revert unauthorized assignment of dangerous roles to members or bots."""
        guild = after.guild
        if not self.bot.antinuke_mgr.is_enabled(guild.id):
            return

        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "member_role"):
            return

        # Check if roles were added
        added_roles = [r for r in after.roles if r not in before.roles]
        if not added_roles:
            return

        # Check if any added role possesses dangerous permissions
        dangerous_added = [
            r for r in added_roles
            if any(getattr(r.permissions, p, False) for p in DANGEROUS_PERMISSIONS)
        ]
        if not dangerous_added:
            return

        # Resolve perpetrator who granted the dangerous role(s)
        perpetrator = await resolve_audit_perpetrator(
            guild, discord.AuditLogAction.member_role_update, target_id=after.id, retries=3, max_age_seconds=15.0
        )

        # If perpetrator is identified and immune (Server Owner, Extra Owner, or Whitelisted for member_role):
        if perpetrator and self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "member_role"):
            return

        # Unauthorized dangerous role assignment!
        # Step 1: Immediately strip the dangerous added roles from the recipient
        stripped = False
        try:
            strip_targets = [
                r for r in dangerous_added
                if not r.managed and r < guild.me.top_role
            ]
            if strip_targets:
                await after.remove_roles(
                    *strip_targets,
                    reason="Kyro Antinuke: Unauthorized Dangerous Role Assignment Revert"
                )
                stripped = True
        except Exception as e:
            logger.warning(f"Guild {guild.id}: Could not strip unauthorized roles from {after.id}: {e}")

        # Step 2: Punish the perpetrator if identified
        action_title = "Anti-Member Role"
        punish_res = "Roles Reverted (Perpetrator Unresolved)"
        if perpetrator:
            punish_res = await execute_punishment(
                self.bot,
                guild,
                perpetrator,
                action_title,
                f"Assigned dangerous role(s) to {after.name}",
            )

        role_names = ", ".join(f"`@{r.name}`" for r in dangerous_added)
        mitigation = f"Reverted {len(dangerous_added)} Role(s)" if stripped else "Revert Failed"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            action_title,
            perpetrator or after,
            punish_res,
            mitigation,
            extra=f"Target: **{after.name}** `「{after.id}」`\n> • **Dangerous Roles:** {role_names}",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntiMemberRoleCog."""
    await bot.add_cog(AntiMemberRoleCog(bot))
