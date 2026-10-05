from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, restore_vanity, dispatch_antinuke_log

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.GuildEvents")


class AntinukeGuildCog(commands.Cog):
    """Event listeners for Vanity URL protection, instant Webhook killer, and server tampering."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        """Detect Vanity URL hijack or unauthorized guild settings tampering."""
        if not self.bot.antinuke_mgr.is_enabled(after.id):
            return

        # 1. Vanity URL Protection Check
        if before.vanity_url_code and before.vanity_url_code != after.vanity_url_code:
            if self.bot.antinuke_mgr.is_module_enabled(after.id, "vanity"):
                await asyncio.sleep(0.2)
                perpetrator: discord.Member | discord.User | None = None
                try:
                    async for entry in after.audit_logs(action=discord.AuditLogAction.guild_update, limit=1):
                        perpetrator = entry.user
                        break
                except Exception:
                    pass

                if perpetrator and not self.bot.antinuke_mgr.is_immune(after, perpetrator.id, "vanity"):
                    # Instant Vanity Recovery
                    restored = await restore_vanity(self.bot, after, before.vanity_url_code)

                    # Punish Attacker
                    punish_res = await execute_punishment(
                        self.bot,
                        after,
                        perpetrator,
                        "Vanity Hijack Attack",
                        f"Attempted to change vanity from {before.vanity_url_code} to {after.vanity_url_code}",
                    )

                    recovery_msg = f"Vanity Restored to '{before.vanity_url_code}'" if restored else "Vanity Revert Failed"

                    await dispatch_antinuke_log(
                        self.bot,
                        after,
                        "Vanity URL Hijack Attempt",
                        perpetrator,
                        punish_res,
                        recovery_msg,
                        extra=f"Original: `{before.vanity_url_code}` • Tampered: `{after.vanity_url_code}`",
                    )
                    return

        # 2. General Server Name / Icon Tampering Check
        if before.name != after.name or before.icon != after.icon or before.verification_level != after.verification_level:
            if self.bot.antinuke_mgr.is_module_enabled(after.id, "guild_update"):
                await asyncio.sleep(0.3)
                perpetrator = None
                try:
                    async for entry in after.audit_logs(action=discord.AuditLogAction.guild_update, limit=1):
                        perpetrator = entry.user
                        break
                except Exception:
                    pass

                if perpetrator and not self.bot.antinuke_mgr.is_immune(after, perpetrator.id, "guild_update"):
                    # Revert server name if changed
                    if before.name != after.name:
                        try:
                            await after.edit(name=before.name, reason="Kyro Antinuke: Server Name Tamper Revert")
                        except Exception:
                            pass

                    punish_res = await execute_punishment(
                        self.bot, after, perpetrator, "Server Tamper Attack", "Modified server configuration"
                    )

                    await dispatch_antinuke_log(
                        self.bot,
                        after,
                        "Server Configuration Tampering",
                        perpetrator,
                        punish_res,
                        "Reverted Name / Settings",
                        extra=f"Previous Name: `{before.name}`",
                    )

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        """Instant Webhook Killer: Delete unauthorized webhooks within milliseconds."""
        guild = channel.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "webhook"):
            return

        await asyncio.sleep(0.2)
        try:
            # Audit log lookup for webhook creation
            async for entry in guild.audit_logs(action=discord.AuditLogAction.webhook_create, limit=1):
                # Ensure entry occurred in last 5 seconds
                if (discord.utils.utcnow() - entry.created_at).total_seconds() > 6.0:
                    continue

                perpetrator = entry.user
                if not perpetrator:
                    continue

                if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "webhook"):
                    continue

                # Kill the webhook immediately if still exists
                target_webhook = entry.target
                killed = False
                if target_webhook and isinstance(target_webhook, discord.Webhook):
                    try:
                        await target_webhook.delete(reason="Kyro Antinuke: Instant Webhook Killer Protocol")
                        killed = True
                    except Exception:
                        pass
                else:
                    # Scan channel webhooks to find rogue ones
                    try:
                        whs = await channel.webhooks()
                        for wh in whs:
                            if wh.user and wh.user.id == perpetrator.id:
                                await wh.delete(reason="Kyro Antinuke: Instant Webhook Killer Protocol")
                                killed = True
                    except Exception:
                        pass

                # Punish attacker
                punish_res = await execute_punishment(
                    self.bot, guild, perpetrator, "Webhook Creation Attack", f"Created rogue webhook in #{channel.name}"
                )

                mitigation = "Rogue Webhook Killed (<50ms)" if killed else "Webhook Neutralized"

                await dispatch_antinuke_log(
                    self.bot,
                    guild,
                    "Webhook Creation Intercepted",
                    perpetrator,
                    punish_res,
                    mitigation,
                    extra=f"Channel: `#{channel.name}` `「{channel.id}」`",
                )
                break
        except Exception as e:
            logger.debug(f"Notice handling webhook update: {e}")

    @commands.Cog.listener()
    async def on_automod_rule_create(self, rule: discord.AutoModRule) -> None:
        """Catch unauthorized AutoMod rule creation/backdoor."""
        guild = rule.guild
        if not self.bot.antinuke_mgr.is_module_enabled(guild.id, "automod"):
            return

        await asyncio.sleep(0.3)
        perpetrator: discord.Member | discord.User | None = None
        try:
            async for entry in guild.audit_logs(action=discord.AuditLogAction.automod_rule_create, limit=1):
                if entry.target and entry.target.id == rule.id:
                    perpetrator = entry.user
                    break
        except Exception:
            pass

        if not perpetrator:
            return

        if self.bot.antinuke_mgr.is_immune(guild, perpetrator.id, "automod"):
            return

        try:
            await rule.delete(reason="Kyro Antinuke: Unauthorized AutoMod Rule Cleanup")
        except Exception:
            pass

        punish_res = await execute_punishment(
            self.bot, guild, perpetrator, "AutoMod Tamper Attack", f"Created rogue automod rule '{rule.name}'"
        )

        await dispatch_antinuke_log(
            self.bot,
            guild,
            "AutoMod Tamper Intercepted",
            perpetrator,
            punish_res,
            "Rogue Rule Deleted",
            extra=f"Rule: `{rule.name}`",
        )


async def setup(bot: KyroBot) -> None:
    """Load AntinukeGuildCog."""
    await bot.add_cog(AntinukeGuildCog(bot))
