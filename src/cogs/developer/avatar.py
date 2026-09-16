"""
Kyro Discord Bot - Secret Developer Avatar Command
Live updates the bot's profile avatar from URL or attachment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import aiohttp
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_owner
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class AvatarCog(commands.Cog, name="Developer-Avatar"):
    """Live bot avatar modifier suite."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="setavatar", aliases=["changeavatar"], hidden=True)
    @is_owner()
    async def change_avatar(self, ctx: CustomContext, url: Optional[str] = None) -> None:
        """
        Live update bot profile avatar image.
        Usage:
          ?setavatar <image_url>
          ?setavatar (with image attachment)
        """
        image_url = url
        if not image_url and ctx.message.attachments:
            image_url = ctx.message.attachments[0].url

        if not image_url:
            await ctx.send_error("Please supply an image URL or attach an image to change avatar.")
            return

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        await ctx.send_error(f"Failed to fetch image: HTTP {resp.status}")
                        return
                    img_data = await resp.read()
            except Exception as e:
                await ctx.send_error(f"Error downloading image: {e}")
                return

        try:
            await self.bot.user.edit(avatar=img_data)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content="**Bot Avatar Updated Successfully**\n> New profile photo is now live."
            )
            await send_container_response(ctx, container)
        except discord.HTTPException as err:
            await ctx.send_error(f"Failed to update avatar: {err}")


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(AvatarCog(bot))
