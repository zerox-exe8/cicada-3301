from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, restore_channel, dispatch_antinuke_log

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiChannel")


class AntiChannelCog(commands.Cog):
    """Anti-Channel protection: Intercepts channel deletions and mass channel spam."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        """Intercept unauthorized channel deletion and auto-recreate."""
        guild = channel.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "channel"):
            return

        cached = self.bot.antinuke_mgr.get_cached_channel(guild.id, channel.id)

        await asyncio.sleep(0.3)
        perpetrator: discord.Member | discord.User | None = None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.channel_delete, limit=1):
                if entry.target and entry.target.id == channel.id:
                    perpetrator = entry.user
                    break
        except Exception:
            pass

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "channel"):
            return

        punish_res = await execute_punishment(
            self.bot, guild, perpetrator, "Anti-Channel", f"Deleted #{channel.name}"
        )

        recreated = None
        if cached:
            recreated = await restore_channel(guild, cached)

        recovery_msg = f"Auto-Recreated #{recreated.name}" if recreated else "Recreation Failed"

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "Anti-Channel",
            perpetrator,
            punish_res,
            recovery_msg,
            extra=f"Target: `#{channel.name}` `「{channel.id}」`",
        )

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        """Catch mass channel creation attacks."""
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

        is_raid = self.bot.antinuke_mgr.check_rate_limit(
            guild.id, perpetrator.id, "channel_create", max_allowed=2, window_seconds=8.0
        )

        if is_raid:
            try:
                await channel.delete(reason="Kyro Antinuke: Mass Channel Raid Cleanup")
            except Exception:
                pass

            punish_res = await execute_punishment(
                self.bot, guild, perpetrator, "Anti-Channel", f"Mass channel spam #{channel.name}"
            )

            await dispatch_antinuke_log(
                self.bot,
                guild,
                "Anti-Channel",
                perpetrator,
                punish_res,
                "Spam Channel Deleted",
                extra=f"Channel: `#{channel.name}`",
            )


async def setup(bot: KyroBot) -> None:
    """Load AntiChannelCog."""
    await bot.add_cog(AntiChannelCog(bot))
