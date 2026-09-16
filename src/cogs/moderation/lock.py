"""
Kyro Discord Bot - Channel Lock & Unlock Moderation Module
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import dispatch_mod_log
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class LockCog(commands.Cog):
    """Channel lock and unlock moderation tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="lock",
        description="Lock a channel to prevent regular members from sending messages.",
    )
    @app_commands.describe(channel="Channel to lock (defaults to current)", reason="Reason for locking")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def lock(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Lock a channel."""
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Error**\n> Lock command only applies to text channels.")
            await send_container_response(ctx, container)
            return

        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await target_channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: {reason}")

        await dispatch_mod_log(self.bot, ctx.guild, "Channel Lock", ctx.author, ctx.author, reason, extra=f"Channel: {target_channel.mention}")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Channel Locked**\n"
                f"> {target_channel.mention} has been locked."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Channel:** {target_channel.mention}\n"
            f"{dot} **Moderator:** **{ctx.author.display_name}** (`{ctx.author.id}`)\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="unlock",
        description="Unlock a channel to allow members to send messages.",
    )
    @app_commands.describe(channel="Channel to unlock (defaults to current)", reason="Reason for unlocking")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def unlock(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Unlock a channel."""
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Error**\n> Unlock command only applies to text channels.")
            await send_container_response(ctx, container)
            return

        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await target_channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: {reason}")

        await dispatch_mod_log(self.bot, ctx.guild, "Channel Unlock", ctx.author, ctx.author, reason, extra=f"Channel: {target_channel.mention}")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Channel Unlocked**\n"
                f"> {target_channel.mention} has been unlocked."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Channel:** {target_channel.mention}\n"
            f"{dot} **Moderator:** **{ctx.author.display_name}** (`{ctx.author.id}`)\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load the LockCog into KyroBot."""
    await bot.add_cog(LockCog(bot))
