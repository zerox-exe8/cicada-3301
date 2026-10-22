from __future__ import annotations

import logging
import discord
from discord import app_commands
from discord.ext import commands

from src.utils.containers import KyroContainer, send_container_response

logger = logging.getLogger("Kyro.ErrorHandler")


class ErrorHandler(commands.Cog):
    """Global listener for command and interaction errors using Components V2."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._default_tree_error = None

    async def cog_load(self) -> None:
        """Register application command error handler."""
        self._default_tree_error = self.bot.tree.on_error
        self.bot.tree.on_error = self.on_app_command_error

    async def cog_unload(self) -> None:
        """Restore default application command error handler."""
        if self._default_tree_error:
            self.bot.tree.on_error = self._default_tree_error

    @commands.Cog.listener()
    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Handle errors occurring during text/hybrid prefix command execution."""
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

        container = KyroContainer(accent_color=None)

        sig = ctx.command.signature if ctx.command else ""
        if sig:
            import re
            sig = re.sub(r'="[^"]*"', '', sig)
            sig = re.sub(r"='[^']*'", '', sig)
            sig = re.sub(r'=\S+', '', sig)
        cmd_name = ctx.command.qualified_name if ctx.command else "command"
        clean_usage = f"`{ctx.prefix}{cmd_name} {sig}`".strip()

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
            err_msg = str(error).strip()
            if not err_msg or "check functions for command" in err_msg.lower():
                err_msg = "You do not have permission to use this command."
            container.add_section(
                content=(
                    f"**{lock_icon}Access Denied**\n"
                    f"> {err_msg}"
                )
            )

        elif isinstance(error, commands.MissingRequiredArgument):
            container.add_section(
                content=(
                    f"**{warn_icon}Invalid Command Usage**\n"
                    f"> Missing required parameter: `{error.param.name}`\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, commands.MemberNotFound):
            arg = getattr(error, "argument", "specified")
            container.add_section(
                content=(
                    f"**{warn_icon}Member Not Found**\n"
                    f"> Could not find member `{arg}` in this server.\n"
                    f"> Please mention the member, use their username, or provide their User ID.\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, commands.UserNotFound):
            arg = getattr(error, "argument", "specified")
            container.add_section(
                content=(
                    f"**{warn_icon}User Not Found**\n"
                    f"> Could not find user `{arg}`.\n"
                    f"> Please provide a valid User ID or mention.\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, commands.RoleNotFound):
            arg = getattr(error, "argument", "specified")
            container.add_section(
                content=(
                    f"**{warn_icon}Role Not Found**\n"
                    f"> Could not find role `{arg}` in this server.\n"
                    f"> Please mention the role or provide its exact name or ID.\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, (commands.ChannelNotFound, commands.ChannelNotReadable)):
            arg = getattr(error, "argument", "specified")
            container.add_section(
                content=(
                    f"**{warn_icon}Channel Not Found**\n"
                    f"> Could not find or access channel `{arg}`.\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, commands.MessageNotFound):
            arg = getattr(error, "argument", "specified")
            container.add_section(
                content=(
                    f"**{warn_icon}Message Not Found**\n"
                    f"> Could not find message `{arg}` in this channel.\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, commands.ThreadNotFound):
            arg = getattr(error, "argument", "specified")
            container.add_section(
                content=(
                    f"**{warn_icon}Thread Not Found**\n"
                    f"> Could not find thread `{arg}`.\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, commands.BadUnionArgument):
            container.add_section(
                content=(
                    f"**{warn_icon}Invalid Parameter**\n"
                    f"> Could not convert parameter `{error.param.name}` to a valid target.\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, commands.BadLiteralArgument):
            literals = ", ".join(f"`{lit}`" for lit in error.literals)
            container.add_section(
                content=(
                    f"**{warn_icon}Invalid Option**\n"
                    f"> Invalid choice for parameter `{error.param.name}`. Expected one of: {literals}.\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, commands.RangeError):
            container.add_section(
                content=(
                    f"**{warn_icon}Value Out of Range**\n"
                    f"> Value `{error.value}` is outside the permitted range (`{error.minimum}` - `{error.maximum}`).\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, commands.BadArgument):
            container.add_section(
                content=(
                    f"**{warn_icon}Invalid Argument**\n"
                    f"> {str(error)}\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, commands.TooManyArguments):
            container.add_section(
                content=(
                    f"**{warn_icon}Too Many Arguments**\n"
                    f"> You provided extra arguments that are not accepted.\n"
                    f"> Usage: {clean_usage}"
                )
            )

        elif isinstance(error, commands.DisabledCommand):
            container.add_section(
                content=(
                    f"**{lock_icon}Command Disabled**\n"
                    f"> This command is temporarily disabled."
                )
            )

        elif isinstance(error, commands.NoPrivateMessage):
            container.add_section(
                content=(
                    f"**{warn_icon}Server Only**\n"
                    f"> This command can only be used inside a Discord server."
                )
            )

        elif isinstance(error, commands.MaxConcurrencyReached):
            container.add_section(
                content=(
                    f"**{clock_icon}Concurrency Limit Reached**\n"
                    f"> This command is already running the maximum allowed number of times ({error.number}). Try again shortly."
                )
            )

        elif isinstance(error, discord.Forbidden):
            container.add_section(
                content=(
                    f"**{lock_icon}Permission Denied**\n"
                    f"> I do not have sufficient Discord permissions or role hierarchy to perform this action."
                )
            )

        elif isinstance(error, discord.NotFound):
            container.add_section(
                content=(
                    f"**{warn_icon}Resource Not Found**\n"
                    f"> The requested Discord resource (channel, message, user, or role) could not be found."
                )
            )

        elif isinstance(error, discord.HTTPException) and error.status == 429:
            logger.error(
                f"Discord REST API 429 Rate Limit active during '{ctx.command}': {error}. "
                "Suppressing error message response to avoid extending rate limit window."
            )
            return

        # ── Unhandled exceptions ONLY ──
        # Every branch above produces a user-facing message for an EXPECTED error
        # (missing argument, bad input, permissions, ...). Those must never be
        # escalated to the Sentinel, otherwise a single typo (e.g. `?jump` without
        # an index) is reported as a subsystem incident and the whole music engine
        # looks "critical".
        if not container.components:
            import traceback
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            cmd_name = ctx.command.qualified_name if ctx.command else "Unknown"
            err_type = type(error).__name__
            err_details = str(error) or err_type
            logger.error(f"Unhandled error in '{cmd_name}': {err_type}: {err_details}\n{tb}")

            if hasattr(self.bot, "sentinel") and self.bot.sentinel:
                from src.sentinel.models import SubsystemType, IncidentSeverity
                self.bot.sentinel.record_incident(
                    SubsystemType.COMMAND,
                    IncidentSeverity.WARNING,
                    f"Command Exception: {cmd_name}",
                    f"{err_type}: {err_details}",
                    action_taken="Handled via maintenance responder; pending developer review",
                    resolved=False,
                    guild_id=ctx.guild.id if ctx.guild else None,
                    traceback=tb,
                )

            is_dev = False
            if hasattr(self.bot, "perm_mgr") and self.bot.perm_mgr:
                is_dev = self.bot.perm_mgr.is_developer_sync(ctx.author.id)

            if is_dev:
                container.add_section(
                    content=(
                        f"**{warn_icon}Command Exception (Developer Mode)**\n"
                        f"> `{cmd_name}` encountered an unhandled exception:\n"
                        f"> `{type(error).__name__}: {error}`"
                    )
                )
            else:
                tools_icon = f"{e_reg.get('icons_settings', e_reg.get('icon_dev', '⚙️'))} " if e_reg else ""
                dot = e_reg.get("heart_dot", "•") if e_reg else "•"
                container.add_section(
                    content=(
                        f"**{tools_icon}Command Under Maintenance**\n"
                        f"> Yeh command abhi active development ya maintenance phase me hai.\n"
                        f"> Hamari team is par kaam kar rahi hai, kripya thodi der baad dobara koshish karein!"
                    )
                )
                container.add_separator(divider=True)
                container.add_text(
                    f"> {dot} **Status:** `Work in Progress / Maintenance`\n"
                    f"> {dot} **Notice:** New features & fixes are actively being deployed."
                )

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        try:
            await send_container_response(ctx, container, ephemeral=True)
        except Exception as e:
            logger.debug(f"Failed to dispatch error container: {e}")

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Handle errors occurring during application / slash command execution."""
        error = getattr(error, "original", error)

        e_reg = getattr(self.bot, "custom_emojis", None)
        err_icon = f"{e_reg.get('icons_wrong', e_reg.get('icon_x', ''))} " if e_reg else ""
        warn_icon = f"{e_reg.get('icons_warning', '')} " if e_reg else ""
        clock_icon = f"{e_reg.get('icons_clock', '')} " if e_reg else ""
        lock_icon = f"{e_reg.get('icons_locked', e_reg.get('icon_lock', ''))} " if e_reg else ""

        container = KyroContainer(accent_color=None)

        if isinstance(error, app_commands.CommandOnCooldown):
            container.add_section(
                content=(
                    f"**{clock_icon}Cooldown Active**\n"
                    f"> This command is currently on cooldown. Try again in `{error.retry_after:.1f}s`."
                )
            )

        elif isinstance(error, app_commands.MissingPermissions):
            missing_perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            container.add_section(
                content=(
                    f"**{lock_icon}Permission Denied**\n"
                    f"> You need the following permissions to execute this command:\n> {missing_perms}"
                )
            )

        elif isinstance(error, app_commands.BotMissingPermissions):
            missing_perms = ", ".join(f"`{p}`" for p in error.missing_permissions)
            container.add_section(
                content=(
                    f"**{lock_icon}Bot Missing Permissions**\n"
                    f"> I need the following permissions in this channel:\n> {missing_perms}"
                )
            )

        elif isinstance(error, app_commands.CheckFailure):
            container.add_section(
                content=(
                    f"**{lock_icon}Access Denied**\n"
                    f"> {str(error) or 'You do not have permission to use this command.'}"
                )
            )

        elif isinstance(error, app_commands.TransformerError):
            container.add_section(
                content=(
                    f"**{warn_icon}Invalid Parameter**\n"
                    f"> Could not parse value `{error.value}` for parameter `{error.param.name}`."
                )
            )

        elif isinstance(error, discord.Forbidden):
            container.add_section(
                content=(
                    f"**{lock_icon}Permission Denied**\n"
                    f"> I do not have sufficient Discord permissions or role hierarchy to perform this action."
                )
            )

        elif isinstance(error, discord.NotFound):
            container.add_section(
                content=(
                    f"**{warn_icon}Resource Not Found**\n"
                    f"> The requested Discord resource (channel, message, user, or role) was not found."
                )
            )

        elif isinstance(error, discord.HTTPException) and error.status == 429:
            logger.error(
                f"Discord REST API 429 Rate Limit active during slash command '{interaction.command}': {error}."
            )
            return

        # ── Unhandled exceptions ONLY ── (see note in on_command_error)
        if not container.components:
            import traceback
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            cmd_name = interaction.command.qualified_name if interaction.command else "Unknown"
            err_type = type(error).__name__
            err_details = str(error) or err_type
            logger.error(f"Unhandled slash error in '{cmd_name}': {err_type}: {err_details}\n{tb}")
            if hasattr(self.bot, "sentinel") and self.bot.sentinel:
                from src.sentinel.models import SubsystemType, IncidentSeverity
                self.bot.sentinel.record_incident(
                    SubsystemType.COMMAND,
                    IncidentSeverity.WARNING,
                    f"Slash Command Exception: {cmd_name}",
                    f"{err_type}: {err_details}",
                    action_taken="Sent error container to user; pending root cause resolution",
                    resolved=False,
                    guild_id=interaction.guild_id,
                    traceback=tb,
                )
            is_dev = False
            if hasattr(self.bot, "perm_mgr") and self.bot.perm_mgr:
                is_dev = self.bot.perm_mgr.is_developer_sync(interaction.user.id)

            if is_dev:
                container.add_section(
                    content=(
                        f"**{warn_icon}Slash Command Exception (Developer Mode)**\n"
                        f"> `{cmd_name}` encountered an unhandled exception:\n"
                        f"> `{type(error).__name__}: {error}`"
                    )
                )
            else:
                tools_icon = f"{e_reg.get('icons_settings', e_reg.get('icon_dev', '⚙️'))} " if e_reg else ""
                dot = e_reg.get("heart_dot", "•") if e_reg else "•"
                container.add_section(
                    content=(
                        f"**{tools_icon}Command Under Maintenance**\n"
                        f"> Yeh command abhi active development ya maintenance phase me hai.\n"
                        f"> Hamari team is par kaam kar rahi hai, kripya thodi der baad dobara koshish karein!"
                    )
                )
                container.add_separator(divider=True)
                container.add_text(
                    f"> {dot} **Status:** `Work in Progress / Maintenance`\n"
                    f"> {dot} **Notice:** New features & fixes are actively being deployed."
                )

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {interaction.user.display_name}")

        try:
            await send_container_response(interaction, container, ephemeral=True)
        except Exception as e:
            logger.debug(f"Failed to dispatch slash error container: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ErrorHandler(bot))
