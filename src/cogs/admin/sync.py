"""
Cicada 3301 Discord Bot - Tree Synchronization Command
Allows the bot owner to instantly sync slash commands to current or all guilds.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import CicadaContainer, send_container_response


class Sync(commands.Cog):
    """Developer and Admin commands."""
    category: str = "Admin"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(
        name="sync",
        description="Sync application commands globally or to current guild.",
        hidden=True,
    )
    @is_developer()
    async def sync_tree(
        self, ctx: CustomContext, scope: str = "guild"
    ) -> None:
        """Sync slash commands immediately. Usage: ?sync or ?sync global"""
        if scope.lower() == "global":
            synced = await self.bot.tree.sync()
            msg = f"Successfully synced `{len(synced)}` application slash commands globally."
        else:
            self.bot.tree.copy_global_to(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
            msg = f"Successfully synced `{len(synced)}` application slash commands instantly to **{ctx.guild.name}**."

        container = CicadaContainer(accent_color=None)
        container.add_text(
            "**Slash Commands Synchronized**\n"
            f"> {msg}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Sync(bot))
