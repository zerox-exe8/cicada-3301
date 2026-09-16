"""
Kyro Discord Bot - Secret Developer Status Command
Live updates the bot's presence and activity across all Discord shards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_owner
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class StatusCog(commands.Cog, name="Developer-Status"):
    """Live bot presence modifier suite."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="setstatus", aliases=["activity", "changestatus"], hidden=True)
    @is_owner()
    async def change_status(self, ctx: CustomContext, activity_type: str, *, status_text: str) -> None:
        """
        Live update bot presence activity from chat.
        Usage:
          ?setstatus playing <text>
          ?setstatus listening <text>
          ?setstatus watching <text>
          ?setstatus competing <text>
          ?setstatus streaming <text>
        """
        act_lower = activity_type.lower()
        activity: discord.BaseActivity

        if act_lower in ("playing", "play"):
            activity = discord.Game(name=status_text)
        elif act_lower in ("streaming", "stream"):
            activity = discord.Streaming(name=status_text, url="https://twitch.tv/discord")
        elif act_lower in ("listening", "listen"):
            activity = discord.Activity(type=discord.ActivityType.listening, name=status_text)
        elif act_lower in ("watching", "watch"):
            activity = discord.Activity(type=discord.ActivityType.watching, name=status_text)
        elif act_lower in ("competing", "compete"):
            activity = discord.Activity(type=discord.ActivityType.competing, name=status_text)
        else:
            activity = discord.CustomActivity(name=f"{activity_type} {status_text}")

        await self.bot.change_presence(status=discord.Status.dnd, activity=activity)

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Presence Activity Updated**\n"
                f"> **Type:** `{act_lower.title()}`\n"
                f"> **Activity:** `{status_text}`\n"
                f"> **Status:** `Live Across All Shards`"
            )
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(StatusCog(bot))
