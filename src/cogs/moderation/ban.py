"""
Kyro Discord Bot - Ban & Unban Moderation Module
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import check_hierarchy, dispatch_mod_log
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class BanCog(commands.Cog):
    """Server ban and unban moderation tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="ban",
        description="Ban a member from the server.",
    )
    @app_commands.describe(member="Member to ban", reason="Reason for the ban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self, ctx: CustomContext, member: discord.Member, *, reason: str = "No reason provided") -> None:
        """Ban a member from the server."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err_msg}")
            await send_container_response(ctx, container)
            return

        # Attempt DM notification
        try:
            dm_container = KyroContainer(accent_color=None)
            dm_container.add_section(
                content=(
                    f"**You were banned from {ctx.guild.name}**\n"
                    f"> Moderator: **{ctx.author}**\n"
                    f"> Reason: `{reason}`"
                )
            )
            await send_container_response(member, dm_container)
        except Exception:
            pass

        await ctx.guild.ban(member, reason=f"{ctx.author} ({ctx.author.id}): {reason}", delete_message_days=0)
        await dispatch_mod_log(self.bot, ctx.guild, "Member Ban", member, ctx.author, reason)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Member Banned**\n"
                f"> **{member}** has been banned from the server."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** **{member.display_name}** (`{member.id}`)\n"
            f"{dot} **Moderator:** **{ctx.author.display_name}**\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="unban",
        description="Unban a user by their user ID or tag.",
    )
    @app_commands.describe(user="User ID or mention to unban", reason="Reason for unbanning")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(self, ctx: CustomContext, user: discord.User, *, reason: str = "No reason provided") -> None:
        """Unban a previously banned user."""
        try:
            await ctx.guild.unban(user, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        except discord.NotFound:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Not Found**\n> This user is not currently banned in this server.")
            await send_container_response(ctx, container)
            return

        await dispatch_mod_log(self.bot, ctx.guild, "Member Unban", user, ctx.author, reason)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Member Unbanned**\n"
                f"> **{user}** has been unbanned from the server."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** **{user}** (`{user.id}`)\n"
            f"{dot} **Moderator:** **{ctx.author.display_name}**\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load the BanCog into KyroBot."""
    await bot.add_cog(BanCog(bot))
