"""
Kyro Discord Bot - Mass Role Assignment (roleall) Module
Streamlined mass role management for human members with rate-limit safety,
Discord Components V2 layout, and cancellation support.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import resolve_role
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.RoleAll")


class RoleAll(commands.Cog, name="Moderation-RoleAll"):
    """Mass Role Management Suite."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # Track running mass-role tasks per guild
        self.active_tasks: set[int] = set()
        # Track cancellation requests per guild
        self.cancelled_tasks: set[int] = set()

    def _validate_role_hierarchy(
        self,
        ctx: CustomContext,
        role: discord.Role,
    ) -> tuple[bool, str | None]:
        if role.is_default():
            return False, "Cannot mass-manage the `@everyone` role."
        if role.managed:
            return False, "This role is integrated/managed by an external bot or application."

        if not ctx.guild.me.guild_permissions.manage_roles:
            return False, "I do not have the `Manage Roles` permission in this server."

        if role >= ctx.guild.me.top_role:
            return False, "I cannot mass-assign this role because it is higher than or equal to my highest role."

        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            return False, "You cannot mass-assign this role because it is higher than or equal to your highest role."

        return True, None

    def _build_usage_card(self, ctx: CustomContext) -> KyroContainer:
        """Construct the Components V2 usage guide for roleall commands."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Roleall Commands**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} `{prefix}roleall <role>`\n"
            f"{dot} `{prefix}roleall remove <role>`\n"
            f"{dot} `{prefix}roleall cancel`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    @commands.group(
        name="roleall",
        invoke_without_command=True,
        description="Mass assign a role to all human members in the server.",
    )
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def roleall_group(self, ctx: CustomContext, *, role: Optional[str] = None) -> None:
        """Directly assigns a role to all human members in the server."""
        if ctx.invoked_subcommand is not None:
            return

        # Case 1: No role passed -> Show clean usage card
        if not role or not role.strip():
            container = self._build_usage_card(ctx)
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        # Case 2: Resolve role by mention, ID, or name
        target_role = resolve_role(ctx.guild, role)
        if not target_role:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Role Not Found**\n"
                    f"> Could not find any role matching `{role}` in this server."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        # Hierarchy validation
        valid, err = self._validate_role_hierarchy(ctx, target_role)
        if not valid:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err}")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        # Ensure all members are cached (important for large servers)
        if not ctx.guild.chunked:
            try:
                await ctx.guild.chunk(cache=True)
            except Exception as e:
                logger.debug(f"Guild chunking skipped/failed: {e}")

        # Target human members who don't already have the role
        targets = [m for m in ctx.guild.members if not m.bot and target_role not in m.roles]
        await self._execute_mass_role(ctx, target_role, targets, action="add", scope_label="All Human Members")

    @roleall_group.command(
        name="remove",
        aliases=["rm", "take", "del"],
        description="Mass remove a role from all members who have it.",
    )
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def roleall_remove(self, ctx: CustomContext, *, role: Optional[str] = None) -> None:
        """Remove a role from everyone who currently possesses it."""
        if not role or not role.strip():
            container = self._build_usage_card(ctx)
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        target_role = resolve_role(ctx.guild, role)
        if not target_role:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Role Not Found**\n"
                    f"> Could not find any role matching `{role}` in this server."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        valid, err = self._validate_role_hierarchy(ctx, target_role)
        if not valid:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err}")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        if not ctx.guild.chunked:
            try:
                await ctx.guild.chunk(cache=True)
            except Exception as e:
                logger.debug(f"Guild chunking skipped/failed: {e}")

        targets = [m for m in ctx.guild.members if target_role in m.roles]
        await self._execute_mass_role(ctx, target_role, targets, action="remove", scope_label="Members with Role")

    @roleall_group.command(
        name="cancel",
        aliases=["stop", "abort"],
        description="Cancel an active mass role operation in this server.",
    )
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def roleall_cancel(self, ctx: CustomContext) -> None:
        """Cancel an in-progress mass-role task."""
        guild_id = ctx.guild.id
        if guild_id not in self.active_tasks:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content="**Roleall Notice**\n> There is no active mass-role task running in this server."
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        self.cancelled_tasks.add(guild_id)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content="**Roleall Cancelled**\n> Stopping the active mass-role operation. Please wait a moment for the background worker to halt."
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())

    async def _execute_mass_role(
        self,
        ctx: CustomContext,
        role: discord.Role,
        targets: list[discord.Member],
        action: str,
        scope_label: str,
    ) -> None:
        if not targets:
            container = KyroContainer(accent_color=None)
            msg = "All human members already have this role." if action == "add" else "No members found possessing this role."
            container.add_section(content=f"**Role Notice**\n> {msg}")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        guild_id = ctx.guild.id
        if guild_id in self.active_tasks:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Task In Progress**\n"
                    "> Another mass-role operation is already running in this server.\n"
                    "> Please wait for it to complete or use `roleall cancel`."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        self.active_tasks.add(guild_id)
        self.cancelled_tasks.discard(guild_id)
        total_targets = len(targets)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        verb = "Adding" if action == "add" else "Removing"
        init_container = KyroContainer(accent_color=role.color.value if role.color.value else None)
        init_container.add_section(
            content=(
                f"**Mass Role Dispatched**\n"
                f"> {verb} {role.mention} for {scope_label.lower()}."
            )
        )
        init_container.add_separator(divider=True)
        init_container.add_text(
            f"{dot} **Action:** `{action.title()}`\n"
            f"{dot} **Role:** {role.mention} (`{role.id}`)\n"
            f"{dot} **Queued:** `{total_targets:,}` members\n"
            f"{dot} **Moderator:** {ctx.author.mention}"
        )
        init_container.add_separator(divider=True)
        init_container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, init_container, allowed_mentions=discord.AllowedMentions.none())

        # Background runner
        self.bot.loop.create_task(
            self._mass_role_worker(ctx, role, targets, action, scope_label)
        )

    async def _mass_role_worker(
        self,
        ctx: CustomContext,
        role: discord.Role,
        targets: list[discord.Member],
        action: str,
        scope_label: str,
    ) -> None:
        guild_id = ctx.guild.id
        success_count = 0
        fail_count = 0
        was_cancelled = False

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        try:
            for member in targets:
                if guild_id in self.cancelled_tasks:
                    was_cancelled = True
                    break

                try:
                    if action == "add":
                        await member.add_roles(role, reason=f"Mass Role Add by {ctx.author} ({ctx.author.id})")
                    else:
                        await member.remove_roles(role, reason=f"Mass Role Remove by {ctx.author} ({ctx.author.id})")
                    success_count += 1
                except (discord.Forbidden, discord.HTTPException):
                    fail_count += 1

                # Discord API rate-limit throttling
                await asyncio.sleep(0.8)

        finally:
            self.active_tasks.discard(guild_id)
            self.cancelled_tasks.discard(guild_id)

        # Completion or Cancellation summary
        status_title = "Mass Role Cancelled" if was_cancelled else "Mass Role Completed"
        accent = None if was_cancelled else (role.color.value if role.color.value else None)

        summary_container = KyroContainer(accent_color=accent)
        summary_container.add_section(
            content=(
                f"**{status_title}**\n"
                f"> Process finished for {role.mention}."
            )
        )
        summary_container.add_separator(divider=True)
        summary_container.add_text(
            f"{dot} **Scope:** `{scope_label}`\n"
            f"{dot} **Successful:** `{success_count:,}`\n"
            f"{dot} **Failed / Skipped:** `{fail_count:,}`"
        )
        summary_container.add_separator(divider=True)
        summary_container.add_text(f"-# Requested by {ctx.author.display_name}")

        try:
            await send_container_response(ctx, summary_container, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            pass


async def setup(bot: KyroBot) -> None:
    """Load the RoleAll cog into KyroBot."""
    await bot.add_cog(RoleAll(bot))
