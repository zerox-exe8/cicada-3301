from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, dispatch_antinuke_log, resolve_audit_perpetrator

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiAutoMod")


class AntiAutoModCog(commands.Cog):
    """Anti-AutoMod protection: Protects AutoMod rules from unauthorized backdoors and tampering."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_automod_rule_create(self, rule: discord.AutoModRule) -> None:
        """Catch unauthorized AutoMod rule creation/backdoor."""
        guild = rule.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "automod"):
            return

        perpetrator = await resolve_audit_perpetrator(
            guild, discord.AuditLogAction.automod_rule_create, target_id=rule.id
        )

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "automod"):
            return

        try:
            await rule.delete(reason="Kyro Antinuke: Unauthorized AutoMod Rule Cleanup")
        except Exception:
            pass

        punish_res = await execute_punishment(
            self.bot, guild, perpetrator, "Anti-AutoMod", f"Created rogue automod rule '{rule.name}'"
        )

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Anti-AutoMod",
            perpetrator,
            punish_res,
            "Rogue Rule Deleted",
            extra=f"Rule: `{rule.name}`",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntiAutoModCog."""
    await bot.add_cog(AntiAutoModCog(bot))
