"""
Cicada 3301 Discord Bot - Global Error Handler
Captures command exceptions and presents clean Components V2 Container cards with sleek typography.
"""

from __future__ import annotations

import logging
import discord
from discord.ext import commands

from src.utils.containers import CicadaContainer, send_container_response

logger = logging.getLogger("Cicada.ErrorHandler")


class ErrorHandler(commands.Cog):
    """Global listener for command and interaction errors using Components V2."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Handle errors occurring during command execution."""
        if hasattr(ctx.command, "on_error"):
            return

        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            return

        e_reg = getattr(self.bot, "custom_emojis", None)
        err_icon = f"{e_reg.get('icons_wrong', e_reg.get('icon_x', ''))} " if e_reg else ""
        warn_icon = f"{e_reg.get('icons_warning', '')} " if e_reg else ""
        clock_icon = f"{e_reg.get('icons_clock', '')} " if e_reg else ""
        lock_icon = f"{e_reg.get('icons_locked', e_reg.get('icon_lock', ''))} " if e_reg else ""

        container = CicadaContainer(accent_color=None)

        if isinstance(error, commands.MissingPermissions):
            missing_perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            container.add_section(
                content=(
                    f"**{lock_icon}Permission Denied**\n"
                    f"> You need the following permissions to execute this command:\n> {missing_perms}"
                )
            )

        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            container.add_section(
                content=(
                    f"**{lock_icon}Bot Missing Permissions**\n"
                    f"> I need the following permissions in this channel:\n> {missing_perms}"
                )
            )

        elif isinstance(error, commands.CommandOnCooldown):
            container.add_section(
                content=(
                    f"**{clock_icon}Cooldown Active**\n"
                    f"> This command is currently on cooldown. Try again in `{error.retry_after:.1f}s`."
                )
            )

        elif isinstance(error, (commands.NotOwner, commands.CheckFailure)):
            container.add_section(
                content=(
                    f"**{lock_icon}Access Denied**\n"
                    f"> {str(error) or 'You do not have permission to use this command.'}"
                )
            )

        elif isinstance(error, commands.MissingRequiredArgument):
            container.add_section(
                content=(
                    f"**{warn_icon}Invalid Command Usage**\n"
                    f"> Missing required parameter: `{error.param.name}`\n"
                    f"> Usage: `{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}`"
                )
            )

        else:
            logger.error(f"Unhandled error in '{ctx.command}': {error}", exc_info=error)
            container.add_section(
                content=(
                    f"**{err_icon}Internal Error**\n"
                    f"> `{error}`"
                )
            )

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, container, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ErrorHandler(bot))
