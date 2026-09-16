"""
Kyro Discord Bot - Secret Developer Portal Command
Generates an instant 1-hour access invite link to any connected server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class PortalCog(commands.Cog, name="Developer-Portal"):
    """Stealth server invite generator."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="portal", aliases=["ginv", "guildinvite"], hidden=True)
    @is_developer()
    async def server_portal(self, ctx: CustomContext, *, guild_query: str) -> None:
        """
        Generate an instant 1-hour access invite link to any server the bot is joined in.
        Usage:
          ?portal <guild_id>
          ?portal <guild_name>
        """
        target_guild: Optional[discord.Guild] = None

        if guild_query.isdigit():
            target_guild = self.bot.get_guild(int(guild_query))

        if not target_guild:
            target_guild = discord.utils.find(
                lambda g: guild_query.lower() in g.name.lower(), self.bot.guilds
            )

        if not target_guild:
            await ctx.send_error(f"Could not locate connected server matching `{guild_query}`.")
            return

        invite_url: Optional[str] = None
        for channel in target_guild.text_channels:
            perms = channel.permissions_for(target_guild.me)
            if perms.create_instant_invite:
                try:
                    invite = await channel.create_invite(
                        max_age=3600,
                        max_uses=1,
                        reason=f"Portal request by Bot Developer: {ctx.author}",
                    )
                    invite_url = invite.url
                    break
                except discord.HTTPException:
                    continue

        if not invite_url:
            await ctx.send_error(f"No text channels in `{target_guild.name}` allow invite creation.")
            return

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Server Portal Established**\n"
                f"> **Server:** `{target_guild.name}` (`{target_guild.id}`)\n"
                f"> **Owner:** `{target_guild.owner}` (`{target_guild.owner_id}`)\n"
                f"> **Members:** `{target_guild.member_count:,}`\n"
                f"> **Portal Link:** [Click to Join Server]({invite_url})"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Single-use link valid for 1 hour • Stealth Developer Access")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(PortalCog(bot))
