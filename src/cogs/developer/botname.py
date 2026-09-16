"""
Kyro Discord Bot - Secret Developer Bot Name Command
Live updates the bot's Discord username.
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


class BotNameCog(commands.Cog, name="Developer-BotName"):
    """Live bot username modifier suite."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="setname", aliases=["changename", "botname"], hidden=True)
    @is_owner()
    async def change_bot_name(self, ctx: CustomContext, *, new_name: str) -> None:
        """
        Live update bot username.
        Usage:
          ?setname NewBotName
        """
        try:
            await self.bot.user.edit(username=new_name.strip())
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=f"**Bot Name Updated**\n> Username changed to `{new_name.strip()}`."
            )
            await send_container_response(ctx, container)
        except discord.HTTPException as err:
            await ctx.send_error(f"Failed to update bot name: {err}")


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(BotNameCog(bot))
