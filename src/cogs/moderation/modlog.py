"""
Kyro Discord Bot - Moderation Audit Log Configuration Module
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class ModLogCog(commands.Cog):
    """Server moderation audit log configuration."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="modlog",
        description="Set or view the moderation audit log channel.",
    )
    @app_commands.describe(channel="Channel for moderation logs (leave empty to view current)")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def modlog(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Set or view the moderation audit log channel."""
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")

        if channel is None:
            current = self.bot.log_mgr.get_log_channel(ctx.guild, "mod")
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Moderation Log Configuration**\n"
                    f"> Current mod log channel: {current.mention if current else '`None (Disabled)`'}"
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"{dot} Use `?modlog #channel` to configure the moderation audit log.")
            await send_container_response(ctx, container)
            return

        await self.bot.log_mgr.set_log_channel(ctx.guild.id, "mod", channel.id)

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Moderation Log Updated**\n"
                f"> Moderation audit logs will now be dispatched to {channel.mention}."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Configured Channel:** {channel.mention}\n"
            f"{dot} **Configured By:** {ctx.author.mention}"
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load the ModLogCog into KyroBot."""
    await bot.add_cog(ModLogCog(bot))
