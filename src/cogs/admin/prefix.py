"""
Cicada 3301 Discord Bot - Prefix Management Command
Allows server administrators to set or reset custom server prefixes.
Uses sleek, compact Components V2 Container Cards with clean proportions.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import CicadaContainer, send_container_response


class Prefix(commands.Cog):
    """Server administration and prefix configuration."""
    category: str = "Settings"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="setprefix",
        description="Change the bot command prefix for this server.",
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def set_prefix(self, ctx: CustomContext, new_prefix: str) -> None:
        """Set a new custom prefix for this server. Usage: ?setprefix !"""
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "-"))

        if len(new_prefix) > 5:
            container = CicadaContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Invalid Prefix**\n"
                    "> Prefix length cannot exceed 5 characters."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        await self.bot.guild_mgr.set_prefix(ctx.guild.id, new_prefix)

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                "**Prefix Updated**\n"
                "> Server command prefix has been successfully configured."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **New Prefix:** `{new_prefix}` | **Example:** `{new_prefix}help`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="resetprefix",
        description="Reset the bot command prefix to default '?' for this server.",
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def reset_prefix(self, ctx: CustomContext) -> None:
        """Reset custom prefix back to default '?'."""
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "-"))

        await self.bot.guild_mgr.reset_prefix(ctx.guild.id)

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                "**Prefix Reset**\n"
                "> Server command prefix has been restored to default."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Default Prefix:** `{Config.DEFAULT_PREFIX}` | **Example:** `{Config.DEFAULT_PREFIX}help`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Prefix(bot))
