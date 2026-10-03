"""
Kyro Discord Bot - Role Management System
Handles role toggling, assignment, and removal with flexible input (mention, ID, or name).
Fully compliant with Discord Components V2 (KyroContainer).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import check_hierarchy, dispatch_mod_log
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.Role")


def resolve_role(guild: discord.Guild, query: str) -> Optional[discord.Role]:
    """
    Resolve a role in the guild from:
    1. Role mention (<@&123456789>)
    2. Role ID (123456789)
    3. Exact role name (case-insensitive)
    4. Role name starting with query (case-insensitive)
    5. Substring match on role name (case-insensitive, ignoring @everyone)
    """
    clean_query = query.strip()
    if not clean_query:
        return None

    # 1. Mention check: <@&123456789>
    mention_match = re.match(r"^<@&(\d+)>$", clean_query)
    if mention_match:
        role_id = int(mention_match.group(1))
        return guild.get_role(role_id)

    # 2. Raw Digits (Role ID): 123456789
    if clean_query.isdigit():
        role = guild.get_role(int(clean_query))
        if role:
            return role

    clean_lower = clean_query.lower()

    # 3. Exact name match (case-insensitive)
    for r in guild.roles:
        if r.name.lower() == clean_lower:
            return r

    # 4. Starts with match (case-insensitive)
    for r in guild.roles:
        if r.name.lower().startswith(clean_lower):
            return r

    # 5. Substring match (case-insensitive, ignoring @everyone)
    for r in guild.roles:
        if not r.is_default() and clean_lower in r.name.lower():
            return r

    return None


class Role(commands.Cog, name="Moderation-Role"):
    """Server role management and assignment tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    def _validate_role_hierarchy(
        self,
        ctx_or_member: discord.Member,
        guild: discord.Guild,
        role: discord.Role,
        target: Optional[discord.Member] = None,
    ) -> tuple[bool, str | None]:
        """Validate hierarchy constraints for role management."""
        if role.is_default():
            return False, "Cannot manage the `@everyone` role."
        if role.managed:
            return False, "This role is integrated/managed by an external bot or application."

        bot_member = guild.me
        if not bot_member.guild_permissions.manage_roles:
            return False, "I do not have the `Manage Roles` permission in this server."

        if role >= bot_member.top_role:
            return False, "I cannot assign or remove this role because it is higher than or equal to my highest role."

        if ctx_or_member.id != guild.owner_id and role >= ctx_or_member.top_role:
            return False, "You cannot assign or remove this role because it is higher than or equal to your highest role."

        if target and target.id == guild.owner_id and ctx_or_member.id != guild.owner_id:
            return False, "You cannot modify roles of the server owner."

        return True, None

    def _build_usage_card(self, ctx: CustomContext) -> KyroContainer:
        """Construct the Components V2 usage guide for role commands."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Role Commands**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} `{prefix}role <@member> <role>`\n"
            f"{dot} `{prefix}role add <@member> <role>`\n"
            f"{dot} `{prefix}role remove <@member> <role>`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    def _build_role_card(
        self,
        ctx: CustomContext,
        action: str,
        member: discord.Member,
        role: discord.Role,
    ) -> KyroContainer:
        """Construct the Components V2 action card (Added / Removed)."""
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        accent = role.color.value if role.color.value else None
        container = KyroContainer(accent_color=accent)
        container.add_section(
            content=(
                f"**Role {action}**\n"
                f"> {action} {role.mention} on {member.mention}."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** {member.mention} (`{member.id}`)\n"
            f"{dot} **Role:** {role.mention} (`{role.id}`)\n"
            f"{dot} **Moderator:** {ctx.author.mention}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    # ─── Main Role Command & Subcommands ─────────────────────────────────────

    @commands.group(
        name="role",
        aliases=["r"],
        invoke_without_command=True,
        description="Toggle, assign, or remove a role from a member.",
    )
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def role_group(
        self,
        ctx: CustomContext,
        member: Optional[discord.Member] = None,
        *,
        role: Optional[str] = None,
    ) -> None:
        """
        Smart role toggle:
        - If role is present on member -> Removes it
        - If role is missing from member -> Adds it
        """
        if ctx.invoked_subcommand is not None:
            return

        # Case 1: No arguments passed -> Show clean Role Usage card
        if member is None:
            container = self._build_usage_card(ctx)
            await send_container_response(ctx, container)
            return

        # Case 2: Member passed but role missing
        if not role or not role.strip():
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Missing Role Argument**\n"
                    f"> Please specify the role to toggle for {member.mention}.\n"
                    f"> Example: `{prefix}role {member.mention} <role-name or ID>`"
                )
            )
            await send_container_response(ctx, container)
            return

        # Case 3: Resolve role by mention, ID, or name
        target_role = resolve_role(ctx.guild, role)
        if not target_role:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Role Not Found**\n"
                    f"> Could not find any role matching `{role}` in this server."
                )
            )
            await send_container_response(ctx, container)
            return

        # Hierarchy validation
        valid, err = self._validate_role_hierarchy(ctx.author, ctx.guild, target_role, target=member)
        if not valid:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err}")
            await send_container_response(ctx, container)
            return

        # Smart Toggle Logic
        if target_role in member.roles:
            await member.remove_roles(target_role, reason=f"Role toggle by {ctx.author} ({ctx.author.id})")
            await dispatch_mod_log(self.bot, ctx.guild, "Role Removed", member, ctx.author, extra=f"Role: {target_role.name}")
            container = self._build_role_card(ctx, "Removed", member, target_role)
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
        else:
            await member.add_roles(target_role, reason=f"Role toggle by {ctx.author} ({ctx.author.id})")
            await dispatch_mod_log(self.bot, ctx.guild, "Role Added", member, ctx.author, extra=f"Role: {target_role.name}")
            container = self._build_role_card(ctx, "Added", member, target_role)
            # Only ping target member receiving the role
            user_ping = discord.AllowedMentions(users=[member], roles=False, everyone=False, replied_user=False)
            await send_container_response(ctx, container, allowed_mentions=user_ping)

    @role_group.command(
        name="add",
        aliases=["give"],
        description="Assign a role to a member.",
    )
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def role_add(
        self,
        ctx: CustomContext,
        member: Optional[discord.Member] = None,
        *,
        role: Optional[str] = None,
    ) -> None:
        """Assign a role to a member."""
        if member is None or not role:
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

        valid, err = self._validate_role_hierarchy(ctx.author, ctx.guild, target_role, target=member)
        if not valid:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err}")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        # If already has role -> Notify that it is already added (silent, no ping)
        if target_role in member.roles:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Role Notice**\n"
                    f"> {member.mention} already has the {target_role.mention} role."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        await member.add_roles(target_role, reason=f"Role added by {ctx.author} ({ctx.author.id})")
        await dispatch_mod_log(self.bot, ctx.guild, "Role Added", member, ctx.author, extra=f"Role: {target_role.name}")
        container = self._build_role_card(ctx, "Added", member, target_role)
        # Only ping target member receiving the role
        user_ping = discord.AllowedMentions(users=[member], roles=False, everyone=False, replied_user=False)
        await send_container_response(ctx, container, allowed_mentions=user_ping)

    @role_group.command(
        name="remove",
        aliases=["rm", "take", "del"],
        description="Remove a role from a member.",
    )
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def role_remove(
        self,
        ctx: CustomContext,
        member: Optional[discord.Member] = None,
        *,
        role: Optional[str] = None,
    ) -> None:
        """Remove a role from a member."""
        if member is None or not role:
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

        valid, err = self._validate_role_hierarchy(ctx.author, ctx.guild, target_role, target=member)
        if not valid:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err}")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        if target_role not in member.roles:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Role Notice**\n"
                    f"> {member.mention} doesn't have the {target_role.mention} role."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        await member.remove_roles(target_role, reason=f"Role removed by {ctx.author} ({ctx.author.id})")
        await dispatch_mod_log(self.bot, ctx.guild, "Role Removed", member, ctx.author, extra=f"Role: {target_role.name}")
        container = self._build_role_card(ctx, "Removed", member, target_role)
        await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: KyroBot) -> None:
    """Load the Role cog into KyroBot."""
    await bot.add_cog(Role(bot))
