from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, dispatch_antinuke_log

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiBot")


class AntiBotCog(commands.Cog):
    """Anti-Bot protection: Detects and eliminates unauthorized bot additions."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Intercept unauthorized bot addition."""
        if not member.bot:
            return

        guild = member.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "bot"):
            return

        await asyncio.sleep(0.4)
        inviter: discord.Member | discord.User | None = None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=1):
                if entry.target and entry.target.id == member.id:
                    inviter = entry.user
                    break
        except Exception:
            pass

        if not inviter:
            return

        if self.bot.antinuke_mgr.is_immune(guild, inviter.id, "bot"):
            return

        # 1. Eliminate the unauthorized bot
        bot_banned = False
        try:
            await member.ban(reason="Kyro Antinuke: Unauthorized Bot Addition", delete_message_seconds=0)
            bot_banned = True
        except Exception:
            try:
                await member.kick(reason="Kyro Antinuke: Unauthorized Bot Addition")
            except Exception:
                pass

        # 2. Punish the inviter
        punish_res = await execute_punishment(
            self.bot, guild, inviter, "Anti-Bot", f"Invited rogue bot {member.name}"
        )

        mitigation = "Rogue Bot Banned" if bot_banned else "Rogue Bot Kicked"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Anti-Bot",
            inviter,
            punish_res,
            mitigation,
            extra=f"Rogue Bot: **{member.name}** `「{member.id}」`",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntiBotCog."""
    await bot.add_cog(AntiBotCog(bot))
