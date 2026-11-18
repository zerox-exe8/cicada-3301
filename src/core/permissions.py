from __future__ import annotations

import functools
import logging
from typing import Any, Callable, TypeVar

import discord
import discord.ext.commands.core
from discord import app_commands
from discord.ext import commands

from src.core.config import Config

logger = logging.getLogger("Kyro.Core.Permissions")

T = TypeVar("T")


def is_owner_sync(bot: Any, user_id: int) -> bool:
    """
    Synchronous, non-blocking check to determine if a user ID belongs to
    the application owner.
    """
    if not user_id:
        return False

    if user_id in Config.OWNER_IDS:
        return True

    if not bot:
        return False

    perm_mgr = getattr(bot, "perm_mgr", None)
    if perm_mgr and hasattr(perm_mgr, "is_owner_sync"):
        if perm_mgr.is_owner_sync(user_id):
            return True

    owner_ids = getattr(bot, "owner_ids", None)
    if owner_ids and user_id in owner_ids:
        return True

    owner_id = getattr(bot, "owner_id", None)
    if owner_id and user_id == owner_id:
        return True

    return False


async def is_owner_async(bot: Any, user: discord.abc.User | discord.Member) -> bool:
    """
    Asynchronous check for application owner status with dynamic
    Discord API resolution fallback.
    """
    if not user:
        return False

    if is_owner_sync(bot, user.id):
        return True

    if bot and hasattr(bot, "is_owner"):
        try:
            if await bot.is_owner(user):
                return True
        except Exception as e:
            logger.debug(f"is_owner check exception: {e}")

    return False


def is_owner_or_developer_sync(bot: Any, user_id: int) -> bool:
    """
    Synchronous, non-blocking check to determine if a user ID belongs to
    the application owner or an authorized system developer.
    Runs with 0ns latency and zero network round-trips.
    """
    if not user_id:
        return False

    if is_owner_sync(bot, user_id):
        return True

    if user_id in Config.DEVELOPER_IDS:
        return True

    if not bot:
        return False

    perm_mgr = getattr(bot, "perm_mgr", None)
    if perm_mgr and hasattr(perm_mgr, "is_developer_sync"):
        if perm_mgr.is_developer_sync(user_id):
            return True

    return False


async def is_owner_or_developer_async(bot: Any, user: discord.abc.User | discord.Member) -> bool:
    """
    Asynchronous check for application owner or developer status with dynamic
    Discord API resolution fallback when memory cache is unpopulated.
    """
    if not user:
        return False

    if is_owner_or_developer_sync(bot, user.id):
        return True

    if bot and hasattr(bot, "is_owner"):
        try:
            if await bot.is_owner(user):
                return True
        except Exception as e:
            logger.debug(f"is_owner check exception: {e}")

    return False


# =========================================================================
# Transparent Command Permission Overrides (Application Owner Bypass Only)
# =========================================================================

def owner_override_has_permissions(**perms: bool) -> Callable[[T], T]:
    """
    Drop-in replacement for commands.has_permissions:
    - Application Owners automatically bypass personal guild permission checks (logged at INFO).
    - Regular server members and developers are strictly evaluated against discord channel permissions.
    - Bot permissions (bot_has_permissions) and role hierarchy remain strictly untouched.
    """
    invalid = set(perms) - set(discord.Permissions.VALID_FLAGS)
    if invalid:
        raise TypeError(f"Invalid permission(s): {', '.join(invalid)}")

    async def predicate(ctx: commands.Context) -> bool:
        # 1. Owner Bypass Only
        if is_owner_sync(ctx.bot, ctx.author.id) or await is_owner_async(ctx.bot, ctx.author):
            guild_id = ctx.guild.id if ctx.guild else "DM"
            cmd_name = ctx.command.qualified_name if ctx.command else "unknown"
            logger.info(
                f"Owner permission override bypass used: guild={guild_id}, command='{cmd_name}', user_id={ctx.author.id}"
            )
            return True

        # 2. Guild Context Evaluation
        ch = ctx.channel
        permissions = ch.permissions_for(ctx.author)

        missing = [perm for perm, value in perms.items() if getattr(permissions, perm) != value]
        if not missing:
            return True

        raise commands.MissingPermissions(missing)

    return commands.check(predicate)


def owner_override_has_guild_permissions(**perms: bool) -> Callable[[T], T]:
    """
    Drop-in replacement for commands.has_guild_permissions:
    - Application Owners automatically bypass personal guild permission checks (logged at INFO).
    - Regular server members and developers are evaluated against guild-level permissions.
    """
    invalid = set(perms) - set(discord.Permissions.VALID_FLAGS)
    if invalid:
        raise TypeError(f"Invalid permission(s): {', '.join(invalid)}")

    async def predicate(ctx: commands.Context) -> bool:
        # 1. Owner Bypass Only
        if is_owner_sync(ctx.bot, ctx.author.id) or await is_owner_async(ctx.bot, ctx.author):
            guild_id = ctx.guild.id if ctx.guild else "DM"
            cmd_name = ctx.command.qualified_name if ctx.command else "unknown"
            logger.info(
                f"Owner guild permission override bypass used: guild={guild_id}, command='{cmd_name}', user_id={ctx.author.id}"
            )
            return True

        # 2. Guild Context Evaluation
        if ctx.guild is None:
            raise commands.NoPrivateMessage()

        permissions = ctx.author.guild_permissions
        missing = [perm for perm, value in perms.items() if getattr(permissions, perm) != value]
        if not missing:
            return True

        raise commands.MissingPermissions(missing)

    return commands.check(predicate)


def owner_override_app_has_permissions(**perms: bool) -> Callable[[T], T]:
    """
    Drop-in replacement for app_commands.checks.has_permissions:
    - Application Owners automatically bypass personal slash command permission checks (logged at INFO).
    - Regular server members and developers are evaluated against interaction permissions.
    """
    invalid = set(perms) - set(discord.Permissions.VALID_FLAGS)
    if invalid:
        raise TypeError(f"Invalid permission(s): {', '.join(invalid)}")

    async def predicate(interaction: discord.Interaction) -> bool:
        # 1. Owner Bypass Only
        client = interaction.client
        user = interaction.user

        if is_owner_sync(client, user.id) or await is_owner_async(client, user):
            guild_id = interaction.guild_id or "DM"
            cmd_name = interaction.command.name if interaction.command else "unknown"
            logger.info(
                f"Owner slash permission override bypass used: guild={guild_id}, command='{cmd_name}', user_id={user.id}"
            )
            return True

        # 2. Interaction Context Evaluation
        permissions = interaction.permissions
        missing = [perm for perm, value in perms.items() if getattr(permissions, perm) != value]
        if not missing:
            return True

        raise app_commands.MissingPermissions(missing)

    return app_commands.check(predicate)


_INSTALLED = False


def install_permission_overrides() -> None:
    """
    Install universal Application Owner Overrides into discord.ext.commands
    and discord.app_commands.checks globally across the runtime.
    Guarantees seamless owner access for all cogs loaded afterwards.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    logger.info("Installing Kyro Application Owner permission overrides...")

    # Hook discord.ext.commands
    commands.has_permissions = owner_override_has_permissions
    discord.ext.commands.core.has_permissions = owner_override_has_permissions

    commands.has_guild_permissions = owner_override_has_guild_permissions
    discord.ext.commands.core.has_guild_permissions = owner_override_has_guild_permissions

    # Hook discord.app_commands
    app_commands.checks.has_permissions = owner_override_app_has_permissions

    _INSTALLED = True
    logger.info("Application Owner permission overrides installed successfully.")
