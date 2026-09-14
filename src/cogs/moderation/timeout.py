"""
Kyro Discord Bot - Timeout & Unmute Moderation Module
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import check_hierarchy, parse_duration, dispatch_mod_log
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class TimeoutCog(commands.Cog):
    """Server timeout and unmute moderation tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="timeout",
        aliases=["mute"],
        description="Timeout a member for a specified duration (e.g., 10m, 1h, 1d).",
    )
    @app_commands.describe(
        member="Member to timeout",
        duration="Duration (e.g. 10m, 1h, 1d, max 28d)",
        reason="Reason for timeout",
    )
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def timeout(
        self,
        ctx: CustomContext,
        member: discord.Member,
        duration: str = "10m",
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Timeout/mute a member."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err_msg}")
            await send_container_response(ctx, container)
            return

        delta = parse_duration(duration)
        if not delta:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Invalid Duration Format**\n"
                    "> Please use format: `10s`, `15m`, `2h`, or `7d` (Max: `28d`)."
                )
            )
            await send_container_response(ctx, container)
            return

        if delta > datetime.timedelta(days=28):
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Duration Exceeded**\n"
                    "> Discord maximum timeout duration is 28 days."
                )
            )
            await send_container_response(ctx, container)
            return

        until = discord.utils.utcnow() + delta
        await member.timeout(until, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await dispatch_mod_log(self.bot, ctx.guild, "Member Timeout", member, ctx.author, reason, extra=f"Duration: {duration}")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Member Timed Out**\n"
                f"> **{member}** has been timed out."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** {member.mention} (`{member.id}`)\n"
            f"{dot} **Duration:** `{duration}` (Expires: <t:{int(until.timestamp())}:R>)\n"
            f"{dot} **Moderator:** {ctx.author.mention}\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="unmute",
        aliases=["untimeout"],
        description="Remove timeout from a member.",
    )
    @app_commands.describe(member="Member to remove timeout from", reason="Reason for removing timeout")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def unmute(
        self,
        ctx: CustomContext,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Remove timeout/unmute a member."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err_msg}")
            await send_container_response(ctx, container)
            return

        await member.timeout(None, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await dispatch_mod_log(self.bot, ctx.guild, "Timeout Removed", member, ctx.author, reason)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Timeout Removed**\n"
                f"> **{member}** is no longer timed out."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** {member.mention} (`{member.id}`)\n"
            f"{dot} **Moderator:** {ctx.author.mention}\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load the TimeoutCog into KyroBot."""
    await bot.add_cog(TimeoutCog(bot))
