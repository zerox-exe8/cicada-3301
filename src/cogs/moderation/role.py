"""
Kyro Discord Bot - Single Role Management & Dynamic Shortcut System
Allows toggling roles, adding/removing roles, and dynamically defining custom role shortcuts
(e.g., `?role setup dynamicduo @DynamicDuo` -> direct trigger via `?dynamicduo @user`).
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.Role")


class Role(commands.Cog, name="Moderation-Role"):
    """Role assignment and dynamic custom shortcut suite."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # In-memory microsecond cache: {guild_id: {shortcut_name: role_id}}
        self.shortcuts: dict[int, dict[str, int]] = {}

    async def cog_load(self) -> None:
        """Load all dynamic guild role shortcuts into memory."""
        try:
            rows = await self.bot.db.fetch_all("SELECT guild_id, shortcut_name, role_id FROM guild_role_shortcuts;")
            for r in rows:
                g_id = int(r["guild_id"])
                name = str(r["shortcut_name"]).lower()
                r_id = int(r["role_id"])
                if g_id not in self.shortcuts:
                    self.shortcuts[g_id] = {}
                self.shortcuts[g_id][name] = r_id
            logger.info(f"Loaded {len(rows)} custom role shortcut(s) into memory cache.")
        except Exception as e:
            logger.debug(f"Notice loading role shortcuts: {e}")

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

    # ─── Standard Role Command & Subcommands ──────────────────────────────────

    @commands.hybrid_group(
        name="role",
        aliases=["r"],
        invoke_without_command=True,
        description="Toggle, assign, or remove a role from a member, or manage role shortcuts.",
    )
    @app_commands.describe(
        member="Target member to modify",
        role="Role to toggle on the member",
    )
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def role_group(
        self,
        ctx: CustomContext,
        member: Optional[discord.Member] = None,
        *,
        role: Optional[discord.Role] = None,
    ) -> None:
        """Smart role toggle: Adds role if missing, removes if present."""
        if ctx.invoked_subcommand is not None:
            return

        if not member or not role:
            # Show role help summary
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"### Role Management Usage\n"
                    f"> **Toggle Role:** `{prefix}role <@member> <@role>`\n"
                    f"> **Explicit Add:** `{prefix}role add <@member> <@role>`\n"
                    f"> **Explicit Remove:** `{prefix}role remove <@member> <@role>`\n"
                    f"> **Setup Custom Shortcut:** `{prefix}role setup <name> <@role>`\n"
                    f"> **View Configured Shortcuts:** `{prefix}role config`"
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        valid, err = self._validate_role_hierarchy(ctx.author, ctx.guild, role, target=member)
        if not valid:
            await ctx.send_warning(err or "Hierarchy constraint error.")
            return

        # Toggle logic
        if role in member.roles:
            await member.remove_roles(role, reason=f"Kyro Role Toggle by {ctx.author} ({ctx.author.id})")
            action = "Removed"
            badge = "Role Removed"
        else:
            await member.add_roles(role, reason=f"Kyro Role Toggle by {ctx.author} ({ctx.author.id})")
            action = "Added"
            badge = "Role Added"

        container = KyroContainer(accent_color=role.color.value if role.color.value else None)
        container.add_section(
            content=(
                f"### {badge}\n"
                f"> **Target:** {member.mention} (`{member.name}`)\n"
                f"> **Role:** {role.mention} (`{role.name}`)\n"
                f"> **Action:** Successfully {action.lower()} role."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Moderated by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @role_group.command(
        name="add",
        description="Explicitly assign a role to a member.",
    )
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def role_add(
        self,
        ctx: CustomContext,
        member: discord.Member,
        *,
        role: discord.Role,
    ) -> None:
        """Add a role to a member."""
        if role in member.roles:
            await ctx.send_warning(f"{member.mention} already has the {role.mention} role.")
            return

        valid, err = self._validate_role_hierarchy(ctx.author, ctx.guild, role, target=member)
        if not valid:
            await ctx.send_warning(err or "Hierarchy constraint error.")
            return

        await member.add_roles(role, reason=f"Kyro Role Add by {ctx.author} ({ctx.author.id})")
        container = KyroContainer(accent_color=role.color.value if role.color.value else None)
        container.add_section(
            content=(
                f"### Role Assigned\n"
                f"> **Target:** {member.mention} (`{member.name}`)\n"
                f"> **Role:** {role.mention}\n"
                f"> **Action:** Assigned successfully."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Moderated by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @role_group.command(
        name="remove",
        description="Explicitly remove a role from a member.",
    )
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    @commands.guild_only()
    async def role_remove(
        self,
        ctx: CustomContext,
        member: discord.Member,
        *,
        role: discord.Role,
    ) -> None:
        """Remove a role from a member."""
        if role not in member.roles:
            await ctx.send_warning(f"{member.mention} does not have the {role.mention} role.")
            return

        valid, err = self._validate_role_hierarchy(ctx.author, ctx.guild, role, target=member)
        if not valid:
            await ctx.send_warning(err or "Hierarchy constraint error.")
            return

        await member.remove_roles(role, reason=f"Kyro Role Remove by {ctx.author} ({ctx.author.id})")
        container = KyroContainer(accent_color=role.color.value if role.color.value else None)
        container.add_section(
            content=(
                f"### Role Removed\n"
                f"> **Target:** {member.mention} (`{member.name}`)\n"
                f"> **Role:** {role.mention}\n"
                f"> **Action:** Removed successfully."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Moderated by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    # ─── Dynamic Role Shortcuts Configuration ────────────────────────────────

    @role_group.group(
        name="setup",
        invoke_without_command=True,
        description="Create or configure custom role shortcuts (e.g. dynamicduo, cutie, friend).",
    )
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def role_setup(
        self,
        ctx: CustomContext,
        name: Optional[str] = None,
        *,
        role: Optional[discord.Role] = None,
    ) -> None:
        """Dynamically bind any custom shortcut name to a role."""
        if not name or not role:
            # If called without arguments, show configured list
            await self.role_config(ctx)
            return

        clean_name = name.strip().lower()
        if not re.match(r"^[a-zA-Z0-9_\-]{2,32}$", clean_name):
            await ctx.send_warning("Shortcut name must be alphanumeric (2-32 characters, no spaces).")
            return

        valid, err = self._validate_role_hierarchy(ctx.author, ctx.guild, role)
        if not valid:
            await ctx.send_warning(err or "Cannot bind this role due to hierarchy constraints.")
            return

        # Save to PostgreSQL
        await self.bot.db.execute(
            """
            INSERT INTO guild_role_shortcuts (guild_id, shortcut_name, role_id)
            VALUES (?, ?, ?)
            ON CONFLICT (guild_id, shortcut_name) DO UPDATE SET role_id = EXCLUDED.role_id;
            """,
            ctx.guild.id,
            clean_name,
            role.id,
        )

        # Update Memory Cache
        if ctx.guild.id not in self.shortcuts:
            self.shortcuts[ctx.guild.id] = {}
        self.shortcuts[ctx.guild.id][clean_name] = role.id

        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        container = KyroContainer(accent_color=role.color.value if role.color.value else None)
        container.add_section(
            content=(
                f"### Role Shortcut Configured\n"
                f"> **Shortcut Name:** `{clean_name}`\n"
                f"> **Bound Role:** {role.mention} (`{role.name}`)\n\n"
                f"Staff members with `Manage Roles` can now execute:\n"
                f"• `{prefix}{clean_name} @user` *(Instant 1-word role toggle)*"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Configured by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @role_setup.command(
        name="remove",
        aliases=["delete"],
        description="Delete a configured role shortcut.",
    )
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def role_setup_remove(self, ctx: CustomContext, name: str) -> None:
        """Remove a custom shortcut from configuration."""
        clean_name = name.strip().lower()
        guild_shortcuts = self.shortcuts.get(ctx.guild.id, {})

        if clean_name not in guild_shortcuts:
            await ctx.send_warning(f"No shortcut named `{clean_name}` is configured in this server.")
            return

        await self.bot.db.execute(
            "DELETE FROM guild_role_shortcuts WHERE guild_id = ? AND shortcut_name = ?;",
            ctx.guild.id,
            clean_name,
        )
        guild_shortcuts.pop(clean_name, None)

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Shortcut Deleted\n"
                f"> Successfully removed role shortcut `{clean_name}` from this server."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Updated by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @role_group.command(
        name="config",
        aliases=["list"],
        description="List all configured custom role shortcuts in this server.",
    )
    @commands.guild_only()
    async def role_config(self, ctx: CustomContext) -> None:
        """Display all configured role shortcuts."""
        guild_shortcuts = self.shortcuts.get(ctx.guild.id, {})
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)

        if not guild_shortcuts:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"### Server Role Shortcuts\n"
                    f"> No custom role shortcuts have been created in this server yet.\n\n"
                    f"Create any shortcut dynamically using:\n"
                    f"• `{prefix}role setup <name> @role` (e.g. `{prefix}role setup cutie @Cutie`)"
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        lines: list[str] = []
        for name, role_id in sorted(guild_shortcuts.items()):
            role = ctx.guild.get_role(role_id)
            role_str = role.mention if role else f"`[Deleted Role ID: {role_id}]`"
            lines.append(f"• **`{prefix}{name}`** ➔ {role_str}")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Configured Role Shortcuts ({len(lines)})\n"
                f"> Staff can toggle these roles using 1-word commands:\n\n"
                + "\n".join(lines)
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Total shortcuts: {len(lines)}")
        await send_container_response(ctx, container)

    # ─── Dynamic 1-Word Message Listener ──────────────────────────────────────

    @commands.Cog.listener("on_message")
    async def dynamic_role_shortcut_listener(self, message: discord.Message) -> None:
        """
        Intercepts custom role shortcuts (e.g., `?dynamicduo @user`, `?cutie @user`)
        and executes fast role toggling.
        """
        if message.author.bot or not message.guild or not isinstance(message.author, discord.Member):
            return

        guild_id = message.guild.id
        guild_shortcuts = self.shortcuts.get(guild_id)
        if not guild_shortcuts:
            return

        prefix = self.bot.guild_mgr.get_prefix(guild_id)
        content = message.content.strip()
        if not content.startswith(prefix):
            return

        tokens = content[len(prefix):].strip().split()
        if not tokens:
            return

        cmd_trigger = tokens[0].lower()
        if cmd_trigger not in guild_shortcuts:
            return

        # Ensure user has Manage Roles or Administrator
        perms = message.author.guild_permissions
        if not (perms.manage_roles or perms.administrator):
            return

        role_id = guild_shortcuts[cmd_trigger]
        target_role = message.guild.get_role(role_id)
        if not target_role:
            return

        # Target member resolution from tokens[1]
        if len(tokens) < 2:
            return

        target_str = tokens[1]
        target_member: Optional[discord.Member] = None

        # Check mention format <@123> or <@!123>
        mention_match = re.match(r"^<@!?(\d+)>$", target_str)
        if mention_match:
            target_id = int(mention_match.group(1))
            target_member = message.guild.get_member(target_id)
        elif target_str.isdigit():
            target_member = message.guild.get_member(int(target_str))

        if not target_member:
            return

        # Hierarchy validation
        valid, err = self._validate_role_hierarchy(message.author, message.guild, target_role, target=target_member)
        if not valid:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Cannot Toggle Role**\n> {err}")
            await send_container_response(message.channel, container)
            return

        # Toggle action
        if target_role in target_member.roles:
            await target_member.remove_roles(
                target_role,
                reason=f"Kyro Shortcut '{cmd_trigger}' by {message.author} ({message.author.id})",
            )
            action = "Removed"
            badge = "Role Removed"
        else:
            await target_member.add_roles(
                target_role,
                reason=f"Kyro Shortcut '{cmd_trigger}' by {message.author} ({message.author.id})",
            )
            action = "Added"
            badge = "Role Added"

        container = KyroContainer(accent_color=target_role.color.value if target_role.color.value else None)
        container.add_section(
            content=(
                f"### {badge}\n"
                f"> **Target:** {target_member.mention} (`{target_member.name}`)\n"
                f"> **Role:** {target_role.mention} (`{target_role.name}`)\n"
                f"> **Action:** Successfully {action.lower()} via shortcut `{cmd_trigger}`."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Moderated by {message.author.display_name}")
        await send_container_response(message.channel, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Role(bot))
