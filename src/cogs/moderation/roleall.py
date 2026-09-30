"""
Kyro Discord Bot - Mass Role Assignment (roleall) Module
Safely assigns or removes roles in bulk for humans, bots, or all members
with rate-limit throttling and live execution feedback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.RoleAll")


class RoleAll(commands.Cog, name="Moderation-RoleAll"):
    """Mass Role Management Suite."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # Track running mass-role tasks per guild to prevent concurrent clashes
        self.active_tasks: set[int] = set()

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

    @commands.hybrid_group(
        name="roleall",
        invoke_without_command=True,
        description="Mass assign or remove roles from humans, bots, or everyone.",
    )
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def roleall_group(self, ctx: CustomContext) -> None:
        """Display mass-role command usage."""
        if ctx.invoked_subcommand is None:
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"### Mass Role Assignment (`roleall`)\n"
                    f"> **All Humans:** `{prefix}roleall humans <@role>`\n"
                    f"> **All Bots:** `{prefix}roleall bots <@role>`\n"
                    f"> **All Members:** `{prefix}roleall all <@role>`\n"
                    f"> **Mass Remove:** `{prefix}roleall remove <@role>`"
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)

    async def _execute_mass_role(
        self,
        ctx: CustomContext,
        role: discord.Role,
        targets: list[discord.Member],
        action: str,  # "add" or "remove"
        scope_label: str,
    ) -> None:
        if not targets:
            await ctx.send_warning(f"No eligible members found to {action} {role.mention}.")
            return

        guild_id = ctx.guild.id
        if guild_id in self.active_tasks:
            await ctx.send_warning("Another mass-role task is currently running in this server. Please wait for it to complete.")
            return

        self.active_tasks.add(guild_id)
        total_targets = len(targets)

        init_container = KyroContainer(accent_color=role.color.value if role.color.value else None)
        init_container.add_section(
            content=(
                f"### Mass Role Task Dispatched\n"
                f"> **Action:** {action.title()} {role.mention}\n"
                f"> **Scope:** `{scope_label}` ({total_targets:,} members queued)\n\n"
                f"Processing in background with rate-limit safety. A completion summary will be posted once done."
            )
        )
        init_container.add_separator(divider=True)
        init_container.add_text(f"-# Initiated by {ctx.author.display_name}")
        await send_container_response(ctx, init_container)

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

        try:
            for i, member in enumerate(targets, 1):
                try:
                    if action == "add":
                        await member.add_roles(role, reason=f"Mass Role Add by {ctx.author} ({ctx.author.id})")
                    else:
                        await member.remove_roles(role, reason=f"Mass Role Remove by {ctx.author} ({ctx.author.id})")
                    success_count += 1
                except Exception as e:
                    fail_count += 1
                    logger.debug(f"Failed to {action} role for {member}: {e}")

                # Discord API rate-limit throttling: 1 request every 0.8s
                await asyncio.sleep(0.8)

        finally:
            self.active_tasks.discard(guild_id)

        # Completion summary
        summary_container = KyroContainer(accent_color=discord.Color.green().value)
        summary_container.add_section(
            content=(
                f"### Mass Role Task Completed\n"
                f"> **Role:** {role.mention} (`{role.name}`)\n"
                f"> **Scope:** `{scope_label}`\n"
                f"• **Successful:** `{success_count:,}`\n"
                f"• **Failed / Skipped:** `{fail_count:,}`"
            )
        )
        summary_container.add_separator(divider=True)
        summary_container.add_text(f"-# Completed for {ctx.author.display_name}")
        try:
            await send_container_response(ctx, summary_container)
        except Exception:
            pass

    @roleall_group.command(
        name="humans",
        description="Assign a role to all human members in this server.",
    )
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def roleall_humans(self, ctx: CustomContext, *, role: discord.Role) -> None:
        """Assign a role to all real humans."""
        valid, err = self._validate_role_hierarchy(ctx, role)
        if not valid:
            await ctx.send_warning(err or "Hierarchy error.")
            return

        targets = [m for m in ctx.guild.members if not m.bot and role not in m.roles]
        await self._execute_mass_role(ctx, role, targets, action="add", scope_label="All Human Members")

    @roleall_group.command(
        name="bots",
        description="Assign a role to all bot accounts in this server.",
    )
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def roleall_bots(self, ctx: CustomContext, *, role: discord.Role) -> None:
        """Assign a role to all bots."""
        valid, err = self._validate_role_hierarchy(ctx, role)
        if not valid:
            await ctx.send_warning(err or "Hierarchy error.")
            return

        targets = [m for m in ctx.guild.members if m.bot and role not in m.roles]
        await self._execute_mass_role(ctx, role, targets, action="add", scope_label="All Bot Accounts")

    @roleall_group.command(
        name="all",
        description="Assign a role to every single member in this server.",
    )
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def roleall_all(self, ctx: CustomContext, *, role: discord.Role) -> None:
        """Assign a role to everyone."""
        valid, err = self._validate_role_hierarchy(ctx, role)
        if not valid:
            await ctx.send_warning(err or "Hierarchy error.")
            return

        targets = [m for m in ctx.guild.members if role not in m.roles]
        await self._execute_mass_role(ctx, role, targets, action="add", scope_label="All Members (Humans & Bots)")

    @roleall_group.command(
        name="remove",
        description="Remove a role from everyone who currently possesses it.",
    )
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def roleall_remove(self, ctx: CustomContext, *, role: discord.Role) -> None:
        """Remove a role from everyone."""
        valid, err = self._validate_role_hierarchy(ctx, role)
        if not valid:
            await ctx.send_warning(err or "Hierarchy error.")
            return

        targets = [m for m in ctx.guild.members if role in m.roles]
        await self._execute_mass_role(ctx, role, targets, action="remove", scope_label="Members with Role")


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(RoleAll(bot))
