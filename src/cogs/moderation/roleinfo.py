"""
Kyro Discord Bot - Role Information Module
Inspects role properties, hierarchy position, member count, and permissions.
Fully compliant with Discord Components V2 (KyroContainer), optimized for desktop & mobile.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import resolve_role
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.RoleInfo")


class RoleInfo(commands.Cog, name="Moderation-RoleInfo"):
    """Single role dossier and permissions inspector."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    def _build_usage_card(self, ctx: CustomContext) -> KyroContainer:
        """Construct the Components V2 usage guide for roleinfo."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Roleinfo Usage**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} `{prefix}roleinfo <@role>`\n"
            f"{dot} `{prefix}roleinfo <role-id>`\n"
            f"{dot} `{prefix}roleinfo <role-name>`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    @commands.hybrid_command(
        name="roleinfo",
        aliases=["ri"],
        description="Inspect a role's color, hierarchy position, member count, and permissions.",
    )
    @app_commands.describe(role="Role mention, ID, or name to inspect")
    @commands.guild_only()
    async def roleinfo(self, ctx: CustomContext, *, role: Optional[str] = None) -> None:
        """Display deep inspection dossier for a role."""
        guild = ctx.guild
        if not guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        # Case 1: No argument passed -> Show clean usage card
        if not role or not role.strip():
            container = self._build_usage_card(ctx)
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        # Case 2: Resolve role by mention, ID, or name
        target_role = resolve_role(guild, role)
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

        # Case 3: Extract Role Details
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        created_ts = int(target_role.created_at.timestamp())
        hex_color = f"#{target_role.color.value:06X}" if target_role.color.value else "Default (No Color)"
        total_roles = len(guild.roles)
        hierarchy_pos = f"#{target_role.position} / {total_roles}"

        hoist_str = "Yes" if target_role.hoist else "No"
        mention_str = "Yes" if target_role.mentionable else "No"

        # Determine exact role classification
        if target_role.is_default():
            role_type = "Default (@everyone)"
        elif target_role.is_bot_managed():
            role_type = "Bot Integration"
        elif target_role.is_premium_subscriber():
            role_type = "Server Booster"
        elif target_role.is_integration():
            role_type = "External Integration"
        elif getattr(target_role.tags, "guild_connections", False):
            role_type = "Linked Connection"
        elif target_role.managed:
            role_type = "Managed Role"
        else:
            role_type = "Standard Role"

        # Member count & percentage
        member_count = len(target_role.members)
        total_members = max(len(guild.members), 1)
        member_pct = (member_count / total_members) * 100
        member_str = f"`{member_count:,}` members ({member_pct:.1f}% of server)"

        # Permission analysis
        perms = target_role.permissions
        key_perms: list[str] = []
        if perms.administrator:
            key_perms.append("Administrator")
        else:
            if perms.manage_guild:
                key_perms.append("Manage Server")
            if perms.manage_roles:
                key_perms.append("Manage Roles")
            if perms.manage_channels:
                key_perms.append("Manage Channels")
            if perms.ban_members:
                key_perms.append("Ban Members")
            if perms.kick_members:
                key_perms.append("Kick Members")
            if perms.moderate_members:
                key_perms.append("Timeout Members")
            if perms.manage_messages:
                key_perms.append("Manage Messages")
            if perms.mention_everyone:
                key_perms.append("Mention Everyone")
            if perms.view_audit_log:
                key_perms.append("View Audit Log")

        perms_str = " ".join(f"`{p}`" for p in key_perms) if key_perms else "`Standard Member Permissions`"

        # Build KyroContainer V2 card
        accent = target_role.color.value if target_role.color.value else None
        container = KyroContainer(accent_color=accent)

        # Header Section
        container.add_section(
            content=(
                f"**Role Information**\n"
                f"> Dossier and permissions for {target_role.mention}."
            )
        )
        container.add_separator(divider=True)

        # Core Details Section (Clean, mobile-first vertical separation)
        container.add_text(
            f"{dot} **Role:** {target_role.mention}\n"
            f"{dot} **Role ID:** `{target_role.id}`\n"
            f"{dot} **Color:** `{hex_color}` • **Position:** `{hierarchy_pos}`\n"
            f"{dot} **Members:** {member_str}\n"
            f"{dot} **Created:** <t:{created_ts}:D> (<t:{created_ts}:R>)"
        )
        container.add_separator(divider=True)

        # Settings & Type Section
        container.add_text(
            f"**Settings & Type**\n"
            f"{dot} **Hoisted:** `{hoist_str}` • **Mentionable:** `{mention_str}`\n"
            f"{dot} **Role Type:** `{role_type}`"
        )
        container.add_separator(divider=True)

        # Key Permissions Section
        container.add_text(
            f"**Key Permissions**\n"
            f"{perms_str}"
        )

        # Thumbnail if role has custom icon
        if target_role.display_icon:
            container.add_thumbnail(str(target_role.display_icon.url))

        # Footer
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: KyroBot) -> None:
    """Load the RoleInfo cog into KyroBot."""
    await bot.add_cog(RoleInfo(bot))
