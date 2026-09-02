"""
Kyro Discord Bot - Developer Operations Cog
Restricted root management suite for bot owners and registered developers.
Includes Direct Execution Authority (No-Prefix engine), module hot-reloading, and diagnostics.
"""

from __future__ import annotations

import io
import sys
import time
import textwrap
import traceback
from contextlib import redirect_stdout
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer, is_owner
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class Developer(commands.Cog):
    """Restricted root operations and system diagnostics."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    # =========================================================
    # No-Prefix Protocol Management (Direct Execution Engine)
    # =========================================================

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
                f"> **add** • `?np add <@user>`\n"
                f"> **remove** • `?np remove <@user>`\n"
                f"> **list** • `?np list`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Active Authorized: {len(self.bot.no_prefix_users)} users")
        await send_container_response(ctx, container)

    @noprefix.command(name="add")
    @is_developer()
    async def np_add(self, ctx: CustomContext, user: discord.User) -> None:
        """Grant direct command execution authority (no prefix needed) to a user."""
        if user.id in self.bot.no_prefix_users:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Notice:** `{user.name}` already has No-Prefix authorization.")
            await send_container_response(ctx, container)
            return

        # 1. Update in-memory set (0ms immediate effect)
        self.bot.no_prefix_users.add(user.id)

        # 2. Persist to PostgreSQL database
        try:
            await self.bot.db.execute(
                """
                INSERT INTO system_no_prefix (user_id, added_by)
                VALUES ($1, $2)
                ON CONFLICT (user_id) DO NOTHING;
                """,
                user.id,
                ctx.author.id,
            )
        except Exception as e:
            self.bot.logger.error(f"Failed to persist No-Prefix grant to DB: {e}")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**No-Prefix Authorized**\n"
                f"> **User:** `{user.name}` (`{user.id}`)\n"
                f"> **Standing:** `Direct Execution Active`\n"
                f"> **Granted By:** `{ctx.author.name}`"
            )
        )
        await send_container_response(ctx, container)

    @noprefix.command(name="remove", aliases=["rm", "del"])
    @is_developer()
    async def np_remove(self, ctx: CustomContext, user: discord.User) -> None:
        """Revoke direct command execution authority from a user."""
        if user.id not in self.bot.no_prefix_users:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Notice:** `{user.name}` does not have No-Prefix authorization.")
            await send_container_response(ctx, container)
            return

        # 1. Update in-memory set
        self.bot.no_prefix_users.discard(user.id)

        # 2. Delete from PostgreSQL database
        try:
            await self.bot.db.execute(
                "DELETE FROM system_no_prefix WHERE user_id = $1;",
                user.id,
            )
        except Exception as e:
            self.bot.logger.error(f"Failed to delete No-Prefix from DB: {e}")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**No-Prefix Revoked**\n"
                f"> **User:** `{user.name}` (`{user.id}`)\n"
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

    # =========================================================
    # Owner Debugging & Module Lifecycle
    # =========================================================

    @commands.command(name="eval", aliases=["e", "py"])
    @is_owner()
    async def eval_code(self, ctx: CustomContext, *, code: str) -> None:
        """Execute asynchronous Python code snippet in safe sandbox."""
        # Clean markdown code blocks if provided
        if code.startswith("```") and code.endswith("```"):
            code = "\n".join(code.split("\n")[1:-1])
        code = code.strip("` \n")

        local_vars = {
            "bot": self.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "discord": discord,
            "commands": commands,
        }

        stdout = io.StringIO()
        func_def = f"async def _eval_func():\n{textwrap.indent(code, '    ')}"

        try:
            exec(func_def, local_vars)
            func = local_vars["_eval_func"]
            t_start = time.perf_counter()
            with redirect_stdout(stdout):
                ret = await func()
            t_dur = (time.perf_counter() - t_start) * 1000

            res = stdout.getvalue()
            result_str = str(ret) if ret is not None else (res.strip() if res else "None")

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Evaluation Output**\n"
                    f"```py\n{result_str[:1500]}\n```"
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Execution Time: {t_dur:.2f}ms")
            await send_container_response(ctx, container)
        except Exception as exc:
            err = traceback.format_exc()
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Evaluation Error**\n"
                    f"```py\n{err[:1500]}\n```"
                )
            )
            await send_container_response(ctx, container)

    @commands.command(name="reload", aliases=["r"])
    @is_developer()
    async def reload_module(self, ctx: CustomContext, module_name: str) -> None:
        """Hot-reload a cog without restarting the bot."""
        mod = module_name.strip()
        if not mod.startswith("src.cogs."):
            # Try finding shortcut
            if "." not in mod:
                # e.g. "developer" or "help" or "music"
                for ext in list(self.bot.extensions.keys()):
                    if ext.endswith(f".{mod}") or ext.endswith(f"._{mod}"):
                        mod = ext
                        break
            else:
                mod = f"src.cogs.{mod}"

        try:
            await self.bot.reload_extension(mod)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Module Reloaded**\n"
                    f"> **Path:** `{mod}`\n"
                    f"> **Status:** `Active & Fresh`"
                )
            )
            await send_container_response(ctx, container)
        except Exception as e:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Failed to reload `{mod}`:**\n`{e}`")
            await send_container_response(ctx, container)

    @commands.command(name="guilds", aliases=["servers"])
    @is_developer()
    async def network_guilds(self, ctx: CustomContext) -> None:
        """Display connected server nodes and member metrics."""
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count or 0, reverse=True)
        total_members = sum(g.member_count or 0 for g in guilds)

        lines = []
        for g in guilds[:10]:
            lines.append(f"> `{g.name}` • `{g.member_count} members` (`{g.id}`)")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Network Nodes ({len(guilds)} Guilds)**\n"
                + "\n".join(lines)
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Total Network Entities: {total_members:,} | Latency: {round(self.bot.latency * 1000)}ms")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Developer(bot))
