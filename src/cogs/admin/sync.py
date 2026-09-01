"""
Kyro Discord Bot - Tree Synchronization Command
Allows the bot owner to sync slash commands globally or clear duplicate guild-level commands.
"""

from __future__ import annotations

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response


class Sync(commands.Cog):
    """Developer and Admin command synchronization tools."""
    category: str = "Admin"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(
        name="sync",
        description="Sync application commands globally and remove duplicate guild commands.",
        hidden=True,
    )
    @is_developer()
    async def sync_tree(
        self, ctx: CustomContext, scope: str = "global"
    ) -> None:
        """
        Clean & Sync slash commands.
        Usage:
          ?sync         -> Eliminates 2-2 duplicate commands and syncs all slash commands globally.
          ?sync clear   -> Clears guild-specific commands in this server.
          ?sync guild   -> Forces instant guild-only copy.
        """
        scope_clean = scope.lower().strip()
        guild = ctx.guild

        if scope_clean in ["guild", "local"]:
            if guild:
                self.bot.tree.copy_global_to(guild=guild)
                synced_guild = await self.bot.tree.sync(guild=guild)
                msg = f"Synced `{len(synced_guild)}` commands locally to **{guild.name}**."
            else:
                msg = "Guild not found."
        else:
            # Default ?sync: clear local guild commands to eliminate duplicates, and sync global commands
            if guild:
                self.bot.tree.clear_commands(guild=guild)
                await self.bot.tree.sync(guild=guild)

            synced_global = await self.bot.tree.sync()
            msg = (
                f"Successfully synced `{len(synced_global)}` slash commands globally.\n"
                f"> Removed 2-2 duplicate guild commands in **{guild.name if guild else 'this server'}**."
            )

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Slash Commands Synchronized**\n"
                f"> {msg}"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @commands.command(
        name="syncemojis",
        aliases=["emojisync", "uploademojis"],
        description="Scan assets folders and sync custom application emojis to Discord.",
        hidden=True,
    )
    @is_developer()
    async def sync_emojis(self, ctx: CustomContext) -> None:
        """Sync custom emojis from assets folder directly to Discord Application Emojis."""
        status_msg = await ctx.send("Scanning assets and uploading application emojis...")
        uploaded, total = await self.bot.custom_emojis.sync_from_assets()

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Application Emojis Synchronized**\n"
                f"> Successfully uploaded `{uploaded}` new emoji(s).\n"
                f"> Total cached custom emojis: `{total}`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Sync(bot))
