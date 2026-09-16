"""
Kyro Discord Bot - Slowmode Moderation Module
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


class SlowmodeCog(commands.Cog):
    """Channel slowmode rate limiting tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="slowmode",
        description="Set slowmode delay for a channel (0 to disable, max 21600s).",
    )
    @app_commands.describe(
        seconds="Slowmode delay in seconds (0 to 21600)",
        channel="Channel to adjust (defaults to current)",
    )
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def slowmode(
        self,
        ctx: CustomContext,
        seconds: int = 0,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Set channel slowmode delay."""
        if seconds < 0 or seconds > 21600:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Invalid Seconds**\n"
                    "> Slowmode seconds must be between `0` and `21600` (6 hours)."
                )
            )
            await send_container_response(ctx, container)
            return

        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Error**\n> Slowmode only applies to text channels.")
            await send_container_response(ctx, container)
            return

        await target_channel.edit(slowmode_delay=seconds, reason=f"Slowmode set by {ctx.author}")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        if seconds == 0:
            container.add_section(
                content=(
                    f"**Slowmode Disabled**\n"
                    f"> Slowmode has been deactivated for {target_channel.mention}."
                )
            )
        else:
            container.add_section(
                content=(
                    f"**Slowmode Updated**\n"
                    f"> Slowmode set to **{seconds}s** for {target_channel.mention}."
                )
            )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Channel:** {target_channel.mention}\n"
            f"{dot} **Delay:** `{seconds} seconds`\n"
            f"{dot} **Moderator:** **{ctx.author.display_name}**"
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load the SlowmodeCog into KyroBot."""
    await bot.add_cog(SlowmodeCog(bot))
