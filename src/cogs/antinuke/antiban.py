from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, dispatch_antinuke_log

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiBan")


class AntiBanCog(commands.Cog):
    """Anti-Ban protection: Intercepts unauthorized bans and auto-unbans victims."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User | discord.Member) -> None:
        """Intercept unauthorized member ban and revert."""
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "ban"):
            return

        await asyncio.sleep(0.3)
        perpetrator: discord.Member | discord.User | None = None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.ban_add, limit=1):
                if entry.target and entry.target.id == user.id:
                    perpetrator = entry.user
                    break
        except Exception:
            pass

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "ban"):
            return

        # Auto-revert unauthorized ban
        unbanned = False
        try:
            await guild.unban(user, reason="Kyro Antinuke: Unauthorized Ban Revert")
            unbanned = True
        except Exception as e:
            logger.error(f"Guild {guild.id}: Failed to unban victim {user.id}: {e}")

        # Punish attacker
        punish_res = await execute_punishment(
            self.bot, guild, perpetrator, "Anti-Ban", f"Banned {user.name}"
        )

        recovery_msg = f"Auto-Unbanned {user.name}" if unbanned else "Unban Revert Failed"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Anti-Ban",
            perpetrator,
            punish_res,
            recovery_msg,
            extra=f"Victim: **{user.name}** `「{user.id}」`",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntiBanCog."""
    await bot.add_cog(AntiBanCog(bot))
