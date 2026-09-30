"""
Kyro Discord Bot - User Information Module
Comprehensive member inspection, permissions breakdown, and identity card.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.General.UserInfo")


class UserInfo(commands.Cog, name="General-UserInfo"):
    """User and Member Dossier."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="userinfo",
        aliases=["ui", "whois"],
        description="View detailed member account age, join dates, permissions, and roles.",
    )
    @app_commands.describe(member="Member or user to inspect")
    async def userinfo(
        self,
        ctx: CustomContext,
        member: Optional[discord.Member | discord.User] = None,
    ) -> None:
        """Display deep user identity card and permissions profile."""
        target = member or ctx.author

        # Fetch full user to populate banners & complete flags
        full_user = target
        try:
            full_user = await self.bot.fetch_user(target.id)
        except Exception:
            pass

        created_ts = int(target.created_at.timestamp())
        is_member = isinstance(target, discord.Member)

        # 1. Join Date and Position Calculation
        joined_str = "Not a member of this server"
        join_pos_str = "N/A"
        if is_member and target.joined_at:
            joined_ts = int(target.joined_at.timestamp())
            joined_str = f"<t:{joined_ts}:F> (<t:{joined_ts}:R>)"
            if ctx.guild:
                # Calculate join position sorted by joined_at
                sorted_members = sorted(
                    [m for m in ctx.guild.members if m.joined_at],
                    key=lambda m: m.joined_at,
                )
                try:
                    pos = sorted_members.index(target) + 1
                    join_pos_str = f"#{pos:,} of {len(sorted_members):,}"
                except ValueError:
                    pass

        # 2. Roles Breakdown
        top_role_str = "None"
        roles_list_str = "None"
        roles_count = 0
        if is_member and ctx.guild:
            roles = [r for r in target.roles if r != ctx.guild.default_role]
            roles_count = len(roles)
            if roles:
                top_role_str = target.top_role.mention
                roles_reversed = sorted(roles, key=lambda r: r.position, reverse=True)
                # Show top 5 roles
                shown_roles = [r.mention for r in roles_reversed[:5]]
                roles_list_str = " ".join(shown_roles)
                if len(roles_reversed) > 5:
                    roles_list_str += f" *(+{len(roles_reversed) - 5} more)*"

        # 3. Key Permissions
        key_perms: list[str] = []
        if is_member:
            perms = target.guild_permissions
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

        perms_str = ", ".join(f"`{p}`" for p in key_perms) if key_perms else "`Standard Member`"

        # 4. User Flags / Badges
        badges = []
        flags = target.public_flags
        if flags.staff:
            badges.append("Discord Staff")
        if flags.partner:
            badges.append("Partnered Server Owner")
        if flags.hypesquad:
            badges.append("HypeSquad Events")
        if flags.bug_hunter:
            badges.append("Bug Hunter")
        if flags.bug_hunter_level_2:
            badges.append("Bug Hunter Gold")
        if flags.active_developer:
            badges.append("Active Developer")
        if flags.early_supporter:
            badges.append("Early Supporter")
        if target.bot:
            badges.append("Bot Account")

        badges_str = " • ".join(f"`{b}`" for b in badges) if badges else "`Standard Account`"

        # 5. Build Container
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### {target.display_name} (`{target.name}`)\n"
                f"> **User ID:** `{target.id}` • **Type:** `{badges_str}`\n"
                f"> **Account Created:** <t:{created_ts}:F> (<t:{created_ts}:R>)"
            )
        )
        container.add_separator(divider=True)

        if is_member:
            container.add_section(
                content=(
                    f"**Server Membership**\n"
                    f"• **Joined Server:** {joined_str}\n"
                    f"• **Join Position:** `{join_pos_str}`\n"
                    f"• **Top Role:** {top_role_str} (`{roles_count}` total)\n"
                    f"• **Roles:** {roles_list_str}"
                )
            )
            container.add_separator(divider=True)
            container.add_section(
                content=(
                    f"**Key Permissions**\n"
                    f"> {perms_str}"
                )
            )

        avatar_url = target.display_avatar.url
        container.add_thumbnail(avatar_url)
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        # Media Buttons
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Avatar HD",
                url=f"{avatar_url}?size=4096" if "?" not in avatar_url else f"{avatar_url}&size=4096",
                style=discord.ButtonStyle.link,
            )
        )
        banner_asset = getattr(full_user, "banner", None)
        if banner_asset:
            banner_url = str(banner_asset.url)
            view.add_item(
                discord.ui.Button(
                    label="Banner HD",
                    url=f"{banner_url}?size=4096" if "?" not in banner_url else f"{banner_url}&size=4096",
                    style=discord.ButtonStyle.link,
                )
            )

        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(UserInfo(bot))
