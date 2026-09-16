"""
Kyro Discord Bot - Secret Developer Direct Message Command
Delivers anonymous official container DMs to any Discord user.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class DMCog(commands.Cog, name="Developer-DM"):
    """Stealth anonymous direct messaging suite."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="dm", aliases=["whisper", "secretmsg"], hidden=True)
    @is_developer()
    async def secret_dm(self, ctx: CustomContext, user: discord.User, *, message: str) -> None:
        """
        Anonymously send an official Kyro embed DM to any Discord user.
        Usage:
          ?dm @user Message text
          ?dm <user_id> Message text
        """
        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Incoming Official Message**\n"
                f"> {message}"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Sent via Kyro Core Network")

        try:
            await user.send(embed=container.to_embed())
            confirm = KyroContainer(accent_color=None)
            confirm.add_section(
                content=f"Secret DM successfully delivered to `{user}` (`{user.id}`)."
            )
            await send_container_response(ctx, confirm)
        except discord.Forbidden:
            await ctx.send_error(f"Cannot deliver DM: User `{user}` has Direct Messages disabled.")
        except discord.HTTPException as err:
            await ctx.send_error(f"Failed to deliver DM: {err}")


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(DMCog(bot))
