"""
Kyro Discord Bot - User Banner Module
Display a user's high-resolution profile banner or custom accent color.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    KyroContainer,
    send_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.General.Banner")


class Banner(commands.Cog, name="General-Banner"):
    """User Banner Module."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="banner",
        description="Display a user's high-resolution profile banner or accent color.",
    )
    @app_commands.describe(member="Member or user whose banner you wish to view")
    async def banner(
        self,
        ctx: CustomContext,
        member: Optional[discord.Member | discord.User] = None,
    ) -> None:
        """View user profile banner or accent color."""
        target = member or ctx.author

        full_user = target
        try:
            full_user = await self.bot.fetch_user(target.id)
        except Exception as e:
            logger.debug(f"Notice fetching user banner: {e}")

        banner_asset = getattr(full_user, "banner", None)
        accent_color = getattr(full_user, "accent_color", None)

        if banner_asset:
            banner_url = str(banner_asset.url)
            hd_url = f"{banner_url}?size=4096" if "?" not in banner_url else f"{banner_url}&size=4096"
            dl_str = self.bot.custom_emojis.get("icons_download", "📥")

            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**{target.name}** • {dl_str} [Download Banner]({hd_url})")
            container.add_separator(divider=True)
            container.add_media(f"{banner_url}?size=2048" if "?" not in banner_url else banner_url)
            await send_container_response(ctx, container)

        elif accent_color:
            hex_code = f"#{accent_color.value:06X}"
            rgb_str = f"rgb({accent_color.r}, {accent_color.g}, {accent_color.b})"

            container = KyroContainer(accent_color=accent_color.value)
            container.add_section(
                content=(
                    f"**{target.name}**\n"
                    f"Accent Color: `{hex_code}` ({rgb_str})"
                )
            )
            await send_container_response(ctx, container)

        else:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=f"**{target.name}** does not have a profile banner or accent color set."
            )
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Banner(bot))
