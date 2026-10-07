from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, dispatch_antinuke_log, resolve_audit_perpetrator

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiKick")


class AntiKickCog(commands.Cog):
    """Anti-Kick protection: Intercepts unauthorized member kicks."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Intercept unauthorized member kick."""
        guild = member.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "kick"):
            return

        perpetrator = await resolve_audit_perpetrator(
            guild, discord.AuditLogAction.kick, target_id=member.id
        )

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "kick"):
            return

        punish_res = await execute_punishment(
            self.bot, guild, perpetrator, "Anti-Kick", f"Kicked {member.name}"
        )

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Anti-Kick",
            perpetrator,
            punish_res,
            "Perpetrator Punished",
            extra=f"Target: **{member.name}** `「{member.id}」`",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntiKickCog."""
    await bot.add_cog(AntiKickCog(bot))
