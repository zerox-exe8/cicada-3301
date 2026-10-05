from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, dispatch_antinuke_log

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.MemberEvents")


class AntinukeMemberCog(commands.Cog):
    """Event listeners for unauthorized bans, rogue kicks, prune raids, and unauthorized bot additions."""

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

        # Rollback: Unban victim
        unbanned = False
        try:
            await guild.unban(user, reason="Kyro Antinuke: Unauthorized Ban Revert")
            unbanned = True
        except Exception as e:
            logger.error(f"Guild {guild.id}: Failed to unban victim {user.id}: {e}")

        # Punish attacker
        punish_res = await execute_punishment(
            self.bot, guild, perpetrator, "Unauthorized Ban", f"Banned {user.name}"
        )

        recovery_msg = f"Auto-Unbanned {user.name}" if unbanned else "Unban Revert Failed"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Unauthorized Ban Intercepted",
            perpetrator,
            punish_res,
            recovery_msg,
            extra=f"Victim: **{user.name}** `「{user.id}」`",
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Intercept unauthorized member kick or prune."""
        guild = member.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "kick"):
            return

        await asyncio.sleep(0.3)
        perpetrator: discord.Member | discord.User | None = None
        is_prune = False

        try:
            # Check for kick action
            async for entry in guild.audit_logs(action=discord.AuditLogAction.kick, limit=1):
                if entry.target and entry.target.id == member.id:
                    perpetrator = entry.user
                    break

            # If not kick, check for prune
            if not perpetrator and self.bot.antinuke_mgr.is_module_enabled(guild.id, "prune"):
                async for entry in guild.audit_logs(action=discord.AuditLogAction.member_prune, limit=1):
                    # Prune within 3 seconds
                    if (discord.utils.utcnow() - entry.created_at).total_seconds() < 5.0:
                        perpetrator = entry.user
                        is_prune = True
                        break
        except Exception:
            pass

        if not perpetrator:
            # Regular voluntary leave
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "prune" if is_prune else "kick"):
            return

        action_name = "Prune Attack" if is_prune else "Unauthorized Kick"
        punish_res = await execute_punishment(
            self.bot, guild, perpetrator, action_name, f"Kicked/Pruned {member.name}"
        )

        await dispatch_antinuke_log(
            self.bot,
            guild,
            f"{action_name} Intercepted",
            perpetrator,
            punish_res,
            "Perpetrator Neutralized",
            extra=f"Affected Member: **{member.name}** `「{member.id}」`",
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Anti-Bot: Detect and kick/ban unauthorized invited bots."""
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

        # Unauthorized bot detected!
        # Step 1: Kick/Ban the unauthorized bot
        bot_banned = False
        try:
            await member.ban(reason="Kyro Antinuke: Unauthorized Bot Addition", delete_message_seconds=0)
            bot_banned = True
        except Exception:
            try:
                await member.kick(reason="Kyro Antinuke: Unauthorized Bot Addition")
            except Exception:
                pass

        # Step 2: Punish the inviter
        punish_res = await execute_punishment(
            self.bot, guild, inviter, "Unauthorized Bot Addition", f"Invited rogue bot {member.name}"
        )

        mitigation = "Rogue Bot Banned" if bot_banned else "Rogue Bot Kicked"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Unauthorized Bot Addition Intercepted",
            inviter,
            punish_res,
            mitigation,
            extra=f"Rogue Bot: **{member.name}** `「{member.id}」`",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntinukeMemberCog."""
    await bot.add_cog(AntinukeMemberCog(bot))
