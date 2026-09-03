"""
Kyro Discord Bot - Bot Information & Telemetry Command
Displays clean, enterprise-grade public system metrics with official invite and support actions.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class BotInfoView(discord.ui.View):
    """Components V2 Link Buttons for Invite and Official Support."""

    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Invite Kyro",
                style=discord.ButtonStyle.link,
                url=Config.INVITE_URL,
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Support Server",
                style=discord.ButtonStyle.link,
                url=Config.SUPPORT_URL,
            )
        )


class BotInfo(commands.Cog):
    """Public system telemetry and official bot details."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="botinfo",
        aliases=["bi", "about", "info"],
        description="View Kyro Bot's network metrics, live uptime, and official links.",
    )
    async def botinfo(self, ctx: CustomContext) -> None:
        """Display safe, high-level public bot telemetry."""
        # 1. Calculate Uptime
        now = discord.utils.utcnow()
        uptime_delta = now - self.bot.start_time
        days = uptime_delta.days
        hours, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
        hours = hours % 24
        minutes, _ = divmod(remainder, 60)

        if days > 0:
            uptime_str = f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            uptime_str = f"{hours}h {minutes}m"
        else:
            uptime_str = f"{minutes}m"

        # 2. Network Metrics
        total_guilds = len(self.bot.guilds)
        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        gateway_ping = round(self.bot.latency * 1000) if (self.bot.latency and self.bot.latency == self.bot.latency) else 0
        current_prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)

        # 3. Resolve Developer Name
        owner_str = "zerox.exe"
        if self.bot.owner_id:
            owner_obj = self.bot.get_user(self.bot.owner_id)
            if owner_obj:
                owner_str = owner_obj.name

        # 4. Construct Components V2 Container
        container = KyroContainer(accent_color=None)
        bot_avatar = self.bot.user.display_avatar.url if self.bot.user else None

        container.add_section(
            content=(
                f"### {Config.BOT_NAME} Information\n"
                f"> **Developer** • `{owner_str}`\n"
                f"> **Prefix** • `{current_prefix}` (Supports No-Prefix)\n"
                f"> **Ping** • `{gateway_ping}ms` • **Uptime** • `{uptime_str}`"
            ),
            accessory={"type": 11, "media": {"url": bot_avatar}} if bot_avatar else None,
        )

        container.add_separator(divider=True)

        container.add_text(
            f"> **Servers** • `{total_guilds:,} Guilds`\n"
            f"> **Users** • `{total_members:,} Members`\n"
            f"> **Audio Engine** • `320kbps Studio Master`\n\n"
            f"-# Kyro Core Protocol • High-Performance System"
        )

        view = BotInfoView()
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(BotInfo(bot))
