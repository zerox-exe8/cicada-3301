from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, dispatch_antinuke_log

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.AntiWebhook")


class AntiWebhookCog(commands.Cog):
    """Anti-Webhook protection: Instant rogue webhook killer."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        """Instant rogue webhook killer."""
        guild = channel.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "webhook"):
            return

        await asyncio.sleep(0.3)
        try:
            now = discord.utils.utcnow()
            async for entry in guild.audit_logs(action=discord.AuditLogAction.webhook_create, limit=6):
                if (now - entry.created_at).total_seconds() > 10.0:
                    continue

                perpetrator = entry.user
                if not perpetrator:
                    continue

                if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "webhook"):
                    continue

                # Kill the webhook immediately
                target_webhook = entry.target
                killed = False
                if target_webhook and isinstance(target_webhook, discord.Webhook):
                    try:
                        await target_webhook.delete(reason="Kyro Antinuke: Instant Webhook Killer")
                        killed = True
                    except Exception:
                        pass
                else:
                    try:
                        whs = await channel.webhooks()
                        for wh in whs:
                            if wh.user and wh.user.id == perpetrator.id:
                                await wh.delete(reason="Kyro Antinuke: Instant Webhook Killer")
                                killed = True
                    except Exception:
                        pass

                # Punish attacker
                punish_res = await execute_punishment(
                    self.bot, guild, perpetrator, "Anti-Webhook", f"Created rogue webhook in #{channel.name}"
                )

                mitigation = "Rogue Webhook Eliminated" if killed else "Webhook Neutralized"

                await dispatch_antinuke_log(
                    self.bot,
                    guild,
                    "Anti-Webhook",
                    perpetrator,
                    punish_res,
                    mitigation,
                    extra=f"Channel: `#{channel.name}` `「{channel.id}」`",
                )
                break
        except Exception as e:
            logger.debug(f"Notice handling webhook update: {e}")


async def setup(bot: KyroBot) -> None:
    """Load AntiWebhookCog."""
    await bot.add_cog(AntiWebhookCog(bot))
