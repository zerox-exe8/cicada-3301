"""
Kyro Discord Bot - Moderators & Staff Discovery Module
Lists all staff and moderators possessing moderation privileges.
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

logger = logging.getLogger("Kyro.Moderation.Mods")


class Mods(commands.Cog, name="Moderation-Mods"):
    """Server moderation team explorer."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="mods",
        aliases=["listmods", "staff"],
        description="List all active staff and moderators possessing moderation privileges.",
    )
    @commands.guild_only()
    async def mods(self, ctx: CustomContext) -> None:
        """List all moderators in this server."""
        guild = ctx.guild
        if not guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        mods_list: list[discord.Member] = []
        for m in guild.members:
            if m.bot:
                continue
            perms = m.guild_permissions
            if (
                perms.administrator
                or perms.ban_members
                or perms.kick_members
                or perms.moderate_members
                or perms.manage_messages
                or perms.manage_guild
            ):
                mods_list.append(m)

        mods_list.sort(key=lambda m: (m.id != guild.owner_id, m.top_role.position), reverse=True)

        if not mods_list:
            await ctx.send_warning("No moderators or staff members found in this server.")
            return

        lines = []
        for m in mods_list[:20]:
            top_role_str = m.top_role.mention if m.top_role != guild.default_role else "No Role"
            lines.append(f"• {m.mention} (`{m.name}`) — {top_role_str}")

        if len(mods_list) > 20:
            lines.append(f"-# ...and `{len(mods_list) - 20}` more staff members")

        container = KyroContainer(accent_color=discord.Color.blue().value)
        container.add_section(
            content=(
                f"### Active Staff & Moderation Team ({len(mods_list)})\n"
                f"> Members with Kick, Ban, Timeout, or Message Management:\n\n"
                + "\n".join(lines)
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Mods(bot))
