"""
Kyro Discord Bot - Kick Moderation Module
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


class KickCog(commands.Cog):
    """Server kick moderation tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="kick",
        description="Kick a member from the server.",
    )
    @app_commands.describe(member="Member to kick", reason="Reason for kicking")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx: CustomContext, member: discord.Member, *, reason: str = "No reason provided") -> None:
        """Kick a member from the server."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err_msg}")
            await send_container_response(ctx, container)
            return

        try:
            dm_container = KyroContainer(accent_color=None)
            dm_container.add_section(
                content=(
                    f"**You were kicked from {ctx.guild.name}**\n"
                    f"> Moderator: **{ctx.author}**\n"
                    f"> Reason: `{reason}`"
                )
            )
            await send_container_response(member, dm_container)
        except Exception:
            pass

        await member.kick(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await dispatch_mod_log(self.bot, ctx.guild, "Member Kick", member, ctx.author, reason)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Member Kicked**\n"
                f"> **{member}** has been kicked from the server."
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
    """Load the KickCog into KyroBot."""
    await bot.add_cog(KickCog(bot))
