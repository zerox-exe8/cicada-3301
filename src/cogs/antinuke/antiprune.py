from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, dispatch_antinuke_log, resolve_audit_perpetrator

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiPrune")


class AntiPruneCog(commands.Cog):
    """Anti-Prune protection: Intercepts server member prune raids."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Intercept member prune raid."""
        guild = member.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "prune"):
            return

        perpetrator = await resolve_audit_perpetrator(
            guild, discord.AuditLogAction.member_prune, max_age_seconds=10.0
        )

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "prune"):
            return

        punish_res = await execute_punishment(
            self.bot, guild, perpetrator, "Anti-Prune", "Triggered unauthorized member prune"
        )

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Anti-Prune",
            perpetrator,
            punish_res,
            "Perpetrator Neutralized",
            extra="Unauthorized prune attack detected",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntiPruneCog."""
    await bot.add_cog(AntiPruneCog(bot))
