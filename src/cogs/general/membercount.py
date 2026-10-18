from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.General.MemberCount")


class MemberCount(commands.Cog, name="General-MemberCount"):
    """Server population metrics."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="membercount",
        aliases=["mc"],
        description="View live server member count breakdown (humans vs bots).",
    )
    @commands.guild_only()
    async def membercount(self, ctx: CustomContext) -> None:
        """Display quick member count statistics for this server."""
        guild = ctx.guild
        if not guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        total = guild.member_count or len(guild.members)
        bots = sum(1 for m in guild.members if m.bot)
        humans = total - bots

        e_reg = getattr(self.bot, "custom_emojis", None)
        heart_dot = e_reg.get("heart_dot", "") if e_reg else ""
        dot_str = f"{heart_dot} " if heart_dot else ""

        container = KyroContainer(accent_color=None)
        container.add_text(f"### {guild.name}")
        container.add_separator(divider=True)

        body_lines = [
            f"{dot_str}**Total Member:** `{total:,}`",
            f"{dot_str}**Humans:** `{humans:,}`",
            f"{dot_str}**Bot:** `{bots:,}`",
        ]
        container.add_section(content="\n".join(body_lines))

        if guild.icon:
            container.add_thumbnail(guild.icon.url)
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.name}")

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(MemberCount(bot))
