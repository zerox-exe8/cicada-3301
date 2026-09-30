"""
Kyro Discord Bot - Server Avatar & Banner Module
Display high-resolution server icon, server banner, and invite splash with direct download.
Uses custom download emoji from assets/emoji.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    KyroContainer,
    send_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.General.ServerAvatar")


class ServerAvatar(commands.Cog, name="General-ServerAvatar"):
    """Server Icon and Server Banner suite."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_group(
        name="server",
        invoke_without_command=True,
        description="Display server media and branding assets.",
    )
    async def server_group(self, ctx: CustomContext) -> None:
        """Display server assets (`?server avatar` or `?server banner`)."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @server_group.command(
        name="avatar",
        aliases=["icon"],
        description="Display this server's high-resolution icon.",
    )
    async def server_avatar(self, ctx: CustomContext) -> None:
        """Display the server's icon (`?server avatar`)."""
        if not ctx.guild or not ctx.guild.icon:
            await ctx.send_warning("This server does not have an icon configured.")
            return

        icon_url = str(ctx.guild.icon.url)
        hd_url = f"{icon_url}?size=4096" if "?" not in icon_url else f"{icon_url}&size=4096"
        dl_emoji = self.bot.custom_emojis.get_emoji_obj("icons_download") or "📥"
        dl_str = self.bot.custom_emojis.get("icons_download", "📥")

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"**{ctx.guild.name}** • {dl_str} [Download Icon]({hd_url})")
        container.add_separator(divider=True)
        container.add_media(f"{icon_url}?size=1024" if "?" not in icon_url else icon_url)

        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Download",
                url=hd_url,
                style=discord.ButtonStyle.link,
                emoji=dl_emoji,
            )
        )
        await send_container_response(ctx, container, view=view)

    @server_group.command(
        name="banner",
        aliases=["splash"],
        description="Display this server's high-resolution banner or invite splash.",
    )
    async def server_banner(self, ctx: CustomContext) -> None:
        """Display the server's banner or splash (`?server banner`)."""
        if not ctx.guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        banner_url = str(ctx.guild.banner.url) if ctx.guild.banner else None
        splash_url = str(ctx.guild.splash.url) if ctx.guild.splash else None

        active_url = banner_url or splash_url
        if not active_url:
            await ctx.send_warning("This server does not have a banner or splash background set.")
            return

        hd_url = f"{active_url}?size=4096" if "?" not in active_url else f"{active_url}&size=4096"
        label = "Server Banner" if banner_url else "Invite Splash"
        dl_emoji = self.bot.custom_emojis.get_emoji_obj("icons_download") or "📥"
        dl_str = self.bot.custom_emojis.get("icons_download", "📥")

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"**{ctx.guild.name}** • {dl_str} [Download {label}]({hd_url})")
        container.add_separator(divider=True)
        container.add_media(f"{active_url}?size=2048" if "?" not in active_url else active_url)

        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Download",
                url=hd_url,
                style=discord.ButtonStyle.link,
                emoji=dl_emoji,
            )
        )
        await send_container_response(ctx, container, view=view)

    @commands.command(name="serveravatar", hidden=True)
    async def serveravatar_shorthand(self, ctx: CustomContext) -> None:
        await self.server_avatar(ctx)

    @commands.command(name="serverbanner", hidden=True)
    async def serverbanner_shorthand(self, ctx: CustomContext) -> None:
        await self.server_banner(ctx)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ServerAvatar(bot))
