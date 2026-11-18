from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.managers.permission_manager import is_owner
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Developer.DM")


class DMCog(commands.Cog, name="Developer-DM"):
    """Official direct messaging tool (Owner-Only)."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="dm", aliases=["directmessage", "pm"], hidden=True)
    @is_owner()
    async def secret_dm(self, ctx: CustomContext, user: discord.User, *, message: str) -> None:
        """
        Send an official Kyro notification DM to a Discord user.
        Owner-only and gated behind ENABLE_DEV_STEALTH_TOOLS.
        Identifies sender to prevent developer impersonation abuse.
        Usage:
          ?dm @user Message text
          ?dm <user_id> Message text
        """
        if not getattr(Config, "ENABLE_DEV_STEALTH_TOOLS", False):
            await ctx.send_warning("Stealth developer tools are disabled in this environment (ENABLE_DEV_STEALTH_TOOLS=false).")
            return

        logger.warning(
            f"SECURITY AUDIT: ?dm used by owner {ctx.author} ({ctx.author.id}) sending message to user {user} ({user.id}): {message[:100]}"
        )

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Incoming Official Message**\n"
                f"> {message}"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Sent by a Kyro developer ({ctx.author.display_name}) via Kyro Core Network")

        try:
            await send_container_response(user, container)
            confirm = KyroContainer(accent_color=None)
            confirm.add_section(
                content=f"Official DM successfully delivered to `{user}` `「{user.id}」`."
            )
            await send_container_response(ctx, confirm)
        except discord.Forbidden:
            await ctx.send_error(f"Cannot deliver DM: User `{user}` has Direct Messages disabled.")
        except discord.HTTPException as err:
            await ctx.send_error(f"Failed to deliver DM: {err}")


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(DMCog(bot))
