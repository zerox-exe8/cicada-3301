"""
Kyro Discord Bot - No-Prefix Management Module
Enables Bot Owners and Developers to grant/revoke Direct Command Execution authority.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Developer.NoPrefix")


class NoPrefixCog(commands.Cog, name="Developer-NoPrefix"):
    """No-Prefix Direct Command Execution protocol manager."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.group(
        name="noprefix",
        aliases=["np"],
        invoke_without_command=True,
        description="Manage Direct Command Execution (No-Prefix) authority.",
    )
    @is_developer()
    async def noprefix(self, ctx: CustomContext) -> None:
        """Overview of No-Prefix management commands."""
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**No-Prefix Protocol**\n"
                f"> **add** • `?np add <@user | id>`\n"
                f"> **remove** • `?np remove <@user | id>`\n"
                f"> **list** • `?np list`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Active Authorized: {len(self.bot.no_prefix_users)} users")
        await send_container_response(ctx, container)

    @noprefix.command(name="add")
    @is_developer()
    async def np_add(self, ctx: CustomContext, *, user: str) -> None:
        """Grant direct command execution authority (no prefix needed) to a user."""
        clean = user.strip("<@!> ")
        target_user: discord.User | None = None
        target_id: int | None = None

        if clean.isdigit():
            target_id = int(clean)
            target_user = self.bot.get_user(target_id)
            if not target_user:
                try:
                    target_user = await self.bot.fetch_user(target_id)
                except Exception:
                    pass
        else:
            try:
                target_user = await commands.UserConverter().convert(ctx, user)
                target_id = target_user.id
            except Exception:
                pass

        if not target_id:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Error:** Could not resolve user `{user}`. Please provide a mention or valid User ID.")
            await send_container_response(ctx, container)
            return

        target_name = target_user.name if target_user else f"User {target_id}"

        if target_id in self.bot.no_prefix_users:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Notice:** `{target_name}` already has No-Prefix authorization.")
            await send_container_response(ctx, container)
            return

        # 1. Update in-memory set (0ms immediate effect)
        self.bot.no_prefix_users.add(target_id)

        # 2. Persist to PostgreSQL database
        try:
            await self.bot.db.execute(
                """
                INSERT INTO system_no_prefix (user_id, added_by)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO NOTHING;
                """,
                target_id,
                ctx.author.id,
            )
        except Exception as e:
            logger.error(f"Failed to persist No-Prefix grant to DB: {e}")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**No-Prefix Authorized**\n"
                f"> **User:** `{target_name}` (`{target_id}`)\n"
                f"> **Standing:** `Direct Execution Active`\n"
                f"> **Granted By:** `{ctx.author.name}`"
            )
        )
        await send_container_response(ctx, container)

    @noprefix.command(name="remove", aliases=["rm", "del"])
    @is_developer()
    async def np_remove(self, ctx: CustomContext, *, user: str) -> None:
        """Revoke direct command execution authority from a user."""
        clean = user.strip("<@!> ")
        target_id: int | None = None
        target_name: str = ""

        if clean.isdigit():
            target_id = int(clean)
            target_user = self.bot.get_user(target_id)
            target_name = target_user.name if target_user else f"User {target_id}"
        else:
            try:
                target_user = await commands.UserConverter().convert(ctx, user)
                target_id = target_user.id
                target_name = target_user.name
            except Exception:
                pass

        if not target_id:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Error:** Could not resolve user `{user}`. Please provide a mention or valid User ID.")
            await send_container_response(ctx, container)
            return

        if target_id not in self.bot.no_prefix_users:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Notice:** `{target_name}` does not have No-Prefix authorization.")
            await send_container_response(ctx, container)
            return

        # 1. Update in-memory set
        self.bot.no_prefix_users.discard(target_id)

        # 2. Delete from PostgreSQL database
        try:
            await self.bot.db.execute(
                "DELETE FROM system_no_prefix WHERE user_id = $1;",
                target_id,
            )
        except Exception as e:
            logger.error(f"Failed to delete No-Prefix from DB: {e}")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**No-Prefix Revoked**\n"
                f"> **User:** `{target_name}` (`{target_id}`)\n"
                f"> **Standing:** `Standard Prefix Enforced`"
            )
        )
        await send_container_response(ctx, container)

    @noprefix.command(name="list", aliases=["ls", "show"])
    @is_developer()
    async def np_list(self, ctx: CustomContext) -> None:
        """Display list of all users authorized for No-Prefix execution."""
        rows = await self.bot.db.fetch_all("SELECT user_id, added_by, created_at FROM system_no_prefix ORDER BY created_at DESC;")
        if not rows and not self.bot.no_prefix_users:
            container = KyroContainer(accent_color=None)
            container.add_text("**No-Prefix Directory:** `Empty` (No users authorized)")
            await send_container_response(ctx, container)
            return

        entries = []
        for r in rows[:15]:
            uid = r["user_id"]
            user_obj = self.bot.get_user(uid)
            uname = f"`{user_obj.name}`" if user_obj else f"`ID: {uid}`"
            entries.append(f"> {uname} • `{uid}`")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**No-Prefix Directory**\n"
                + ("\n".join(entries) if entries else "> No entries found")
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Total Active: {len(self.bot.no_prefix_users)} users")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(NoPrefixCog(bot))
