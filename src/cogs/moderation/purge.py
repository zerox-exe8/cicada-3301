"""
Kyro Discord Bot - Purge / Message Cleaning Module
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class PurgeCog(commands.Cog):
    """Message bulk deletion and channel cleaning tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="purge",
        aliases=["prune"],
        description="Bulk delete messages in the current channel (1 to 100).",
    )
    @app_commands.describe(
        count="Number of messages to delete (1-100)",
        member="Optional member to filter messages by",
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    @commands.guild_only()
    async def purge(
        self,
        ctx: CustomContext,
        count: int = 10,
        member: Optional[discord.Member] = None,
    ) -> None:
        """Bulk delete messages."""
        if count < 1 or count > 100:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Invalid Count**\n"
                    "> Message purge count must be between 1 and 100."
                )
            )
            await send_container_response(ctx, container)
            return

        # For prefix command, delete invoking message first if possible
        if not ctx.interaction and ctx.message:
            try:
                await ctx.message.delete()
            except Exception:
                pass

        check = (lambda m: m.author.id == member.id) if member else None
        deleted = await ctx.channel.purge(limit=count, check=check)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Messages Purged**\n"
                f"> Successfully cleared **{len(deleted)}** message(s)."
            )
        )
        container.add_separator(divider=True)
        info = f"{dot} **Deleted:** `{len(deleted)}` message(s)\n{dot} **Channel:** {ctx.channel.mention}"
        if member:
            info += f"\n{dot} **Filter:** Messages from {member.mention}"
        container.add_text(info)

        msg = await send_container_response(ctx, container)
        # Auto-delete confirmation after 5 seconds to keep channel clean
        if msg and isinstance(msg, discord.Message):
            try:
                await msg.delete(delay=5.0)
            except Exception:
                pass


async def setup(bot: KyroBot) -> None:
    """Load the PurgeCog into KyroBot."""
    await bot.add_cog(PurgeCog(bot))
