from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, restore_vanity, dispatch_antinuke_log

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiVanity")


class AntiVanityCog(commands.Cog):
    """Anti-Vanity protection: Defends server vanity URL from hijack and tampering."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        """Detect and restore hijacked Vanity URL."""
        if not self.bot.antinuke_mgr.is_module_enabled(after.id, "vanity"):
            return

        if not before.vanity_url_code or before.vanity_url_code == after.vanity_url_code:
            return

        await asyncio.sleep(0.2)
        perpetrator: discord.Member | discord.User | None = None
        try:
            async for entry in after.audit_logs(action=discord.AuditLogAction.guild_update, limit=1):
                perpetrator = entry.user
                break
        except Exception:
            pass

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(after, perpetrator.id, "vanity"):
            return

        # Restore vanity code
        restored = await restore_vanity(self.bot, after, before.vanity_url_code)

        # Punish attacker
        punish_res = await execute_punishment(
            self.bot,
            after,
            perpetrator,
            "Anti-Vanity",
            f"Changed vanity from {before.vanity_url_code} to {after.vanity_url_code}",
        )

        recovery_msg = f"Vanity Restored to '{before.vanity_url_code}'" if restored else "Vanity Revert Failed"

        await dispatch_antinuke_log(
            self.bot,
            after,
            "Anti-Vanity",
            perpetrator,
            punish_res,
            recovery_msg,
            extra=f"Original: `{before.vanity_url_code}` • Tampered: `{after.vanity_url_code}`",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntiVanityCog."""
    await bot.add_cog(AntiVanityCog(bot))
