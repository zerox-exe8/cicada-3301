from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, dispatch_antinuke_log, resolve_audit_perpetrator

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

        inviter = await resolve_audit_perpetrator(
            guild, discord.AuditLogAction.bot_add, target_id=member.id
        )

        if not inviter:
            return

        if self.bot.antinuke_mgr.is_immune(guild, inviter.id, "bot"):
            return

        # Check for rapid mass bot flood attack (2+ bots in 30 seconds)
        is_mass_bot_raid = self.bot.antinuke_mgr.check_rate_limit(
            guild.id, inviter.id, "bot_add", max_allowed=2, window_seconds=30.0
        )

        action_title = "Mass Bot Raid" if is_mass_bot_raid else "Anti-Bot"

        # 1. Eliminate the unauthorized bot
        bot_banned = False
        try:
            await member.ban(reason=f"Kyro Antinuke: {action_title}", delete_message_seconds=0)
            bot_banned = True
        except Exception:
            try:
                await member.kick(reason=f"Kyro Antinuke: {action_title}")
            except Exception:
                pass

        # 2. If mass raid, sweep and ban any other unauthorized bots added in the last 60 seconds
        extra_banned = []
        if is_mass_bot_raid:
            now_ts = discord.utils.utcnow()
            for m in list(guild.members):
                if m.bot and m.id != self.bot.user.id and m.id != member.id:
                    if m.joined_at and (now_ts - m.joined_at).total_seconds() <= 60.0:
                        try:
                            await m.ban(reason="Kyro Antinuke: Mass Bot Raid Sweep", delete_message_seconds=0)
                            extra_banned.append(m.name)
                        except Exception:
                            pass

        # 3. Punish the inviter (if mass raid, force ban)
        reason_str = f"Mass Bot Flood ({member.name} + {len(extra_banned)} others)" if is_mass_bot_raid else f"Invited unauthorized bot {member.name}"
        punish_res = await execute_punishment(
            self.bot, guild, inviter, action_title, reason_str
        )

        mitigation = "Unauthorized Bot Banned" if bot_banned else "Unauthorized Bot Kicked"
        if extra_banned:
            mitigation += f" (+{len(extra_banned)} removed)"

        detail_str = f"Unauthorized Bot: **{member.name}** `「{member.id}」`"
        if extra_banned:
            detail_str += f"\n> • **Removed Bots:** {', '.join(f'`{b}`' for b in extra_banned[:5])}"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            action_title,
            inviter,
            punish_res,
            mitigation,
            extra=detail_str,
        )


async def setup(bot: KyroBot) -> None:
    """Load AntiBotCog."""
    await bot.add_cog(AntiBotCog(bot))
