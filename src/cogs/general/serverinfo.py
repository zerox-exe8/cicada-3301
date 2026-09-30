"""
Kyro Discord Bot - Server Information Module
Clean server information card in Components V2 design.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.General.ServerInfo")


class ServerInfo(commands.Cog, name="General-ServerInfo"):
    """Server Information Module."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="serverinfo",
        aliases=["si", "guildinfo"],
        description="View server information and statistics.",
    )
    @commands.guild_only()
    async def serverinfo(self, ctx: CustomContext) -> None:
        """Display server information."""
        guild = ctx.guild
        if not guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        total_members = guild.member_count or len(guild.members)
        bots_count = sum(1 for m in guild.members if m.bot)
        humans_count = total_members - bots_count

        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        stage_channels = len(guild.stage_channels)
        categories = len(guild.categories)
        total_channels = text_channels + voice_channels + stage_channels

        roles_count = len(guild.roles) - 1
        emojis_count = len(guild.emojis)
        stickers_count = len(guild.stickers)

        boost_tier = guild.premium_tier
        boost_count = guild.premium_subscription_count or 0

        verif_level = str(guild.verification_level).replace("_", " ").title()

        created_ts = int(guild.created_at.timestamp())
        owner = guild.owner or await self.bot.fetch_user(guild.owner_id) if guild.owner_id else None
        owner_str = f"{owner.mention} (`{owner.name}`)" if owner else f"ID: `{guild.owner_id}`"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### {guild.name}\n"
                f"> **Owner:** {owner_str} • **ID:** `{guild.id}`\n"
                f"> **Created:** <t:{created_ts}:F> (<t:{created_ts}:R>)"
            )
        )
        container.add_separator(divider=True)

        container.add_section(
            content=(
                f"**Overview**\n"
                f"• **Members:** `{total_members:,}` (`{humans_count:,}` humans, `{bots_count:,}` bots)\n"
                f"• **Channels:** `{total_channels}` (`{text_channels}` text, `{voice_channels}` voice, `{categories}` categories)\n"
                f"• **Roles:** `{roles_count}` • **Emojis:** `{emojis_count}` • **Stickers:** `{stickers_count}`\n"
                f"• **Boosts:** Level `{boost_tier}` (`{boost_count}` boosts) • **Verification:** `{verif_level}`"
            )
        )

        if guild.icon:
            container.add_thumbnail(guild.icon.url)

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        view = discord.ui.View()
        if guild.icon:
            view.add_item(
                discord.ui.Button(
                    label="Icon",
                    url=str(guild.icon.url),
                    style=discord.ButtonStyle.link,
                    emoji="📥",
                )
            )
        if guild.banner:
            view.add_item(
                discord.ui.Button(
                    label="Banner",
                    url=str(guild.banner.url),
                    style=discord.ButtonStyle.link,
                    emoji="📥",
                )
            )

        if len(view.children) > 0:
            await send_container_response(ctx, container, view=view)
        else:
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ServerInfo(bot))
