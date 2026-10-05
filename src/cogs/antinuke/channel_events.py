from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, restore_channel, dispatch_antinuke_log

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.ChannelEvents")


class AntinukeChannelCog(commands.Cog):
    """Event listeners for channel deletion, mass channel spam, and permission tampering."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """Intercept unauthorized channel deletion and instantly restore."""
        guild = channel.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "channel"):
            return

        # Snapshot retrieval before deletion wipe
        cached = self.bot.antinuke_mgr.get_cached_channel(guild.id, channel.id)

        # Audit log resolution
        await asyncio.sleep(0.3)  # Small yield for Discord audit log propagation
        perpetrator: discord.Member | discord.User | None = None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
                if entry.target and entry.target.id == channel.id:
                    perpetrator = entry.user
                    break
        except Exception as e:
            logger.debug(f"Audit log check failed on channel delete: {e}")

        if not perpetrator:
            return

        # Immunity check (Owner, Bot, Whitelist)
        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "channel"):
            return

        # Attack detected: Punish offender
        punish_res = await execute_punishment(
            self.bot, guild, perpetrator, "Channel Delete", f"Deleted #{channel.name}"
        )

        # Self-healing: Recreate channel
        recreated = None
        if cached:
            recreated = await restore_channel(guild, cached)

        recovery_msg = f"Auto-Recreated #{recreated.name}" if recreated else "Recreation Failed"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Channel Deletion Intercepted",
            perpetrator,
            punish_res,
            recovery_msg,
            extra=f"Target: `#{channel.name}` `「{channel.id}」`",
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """Catch mass channel creation attacks (e.g. 50 channels created in 5 sec)."""
        guild = channel.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "channel"):
            return

        await asyncio.sleep(0.3)
        perpetrator: discord.Member | discord.User | None = None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_create, limit=1):
                if entry.target and entry.target.id == channel.id:
                    perpetrator = entry.user
                    break
        except Exception:
            pass

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "channel"):
            return

        # Check rate limit (mass channel spam > 2 in 8 seconds)
        is_raid = self.bot.antinuke_mgr.check_rate_limit(
            guild.id, perpetrator.id, "channel_create", max_allowed=2, window_seconds=8.0
        )

        if is_raid:
            # Delete spam channel
            try:
                await channel.delete(reason="Kyro Antinuke: Mass Channel Raid Cleanup")
            except Exception:
                pass

            punish_res = await execute_punishment(
                self.bot, guild, perpetrator, "Mass Channel Creation", f"Created spam channel #{channel.name}"
            )

            await dispatch_antinuke_log(
                self.bot,
                guild,
                "Mass Channel Creation Raid",
                perpetrator,
                punish_res,
                "Spam Channel Deleted",
                extra=f"Channel: `#{channel.name}`",
            )


async def setup(bot: KyroBot) -> None:
    """Load AntinukeChannelCog."""
    await bot.add_cog(AntinukeChannelCog(bot))
