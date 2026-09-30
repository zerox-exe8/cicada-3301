"""
Kyro Discord Bot - User Information Module
Top-level interactive user dossier with 3 distinct tabs (Profile, Server, Roles),
zero bullet dots, zero unwanted mentions, and clean formatting.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    KyroContainer,
    send_container_response,
    edit_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.General.UserInfo")


class UserInfoView(discord.ui.View):
    """Interactive 3-tab view for user information (Profile, Server, Roles)."""

    def __init__(
        self,
        ctx: CustomContext,
        target: discord.Member | discord.User,
        full_user: discord.User,
    ) -> None:
        super().__init__(timeout=120)
        self.ctx = ctx
        self.target = target
        self.full_user = full_user
        self.current_tab = "profile"
        self._build_tabs()

    def _build_tabs(self) -> None:
        self.clear_items()

        # Tab 1: Profile
        btn_profile = discord.ui.Button(
            label="Profile",
            style=discord.ButtonStyle.primary if self.current_tab == "profile" else discord.ButtonStyle.secondary,
            custom_id="tab_profile",
        )
        btn_profile.callback = self._on_profile_clicked
        self.add_item(btn_profile)

        # Tab 2: Server Standing (only if target is in the server)
        if isinstance(self.target, discord.Member):
            btn_server = discord.ui.Button(
                label="Server",
                style=discord.ButtonStyle.primary if self.current_tab == "server" else discord.ButtonStyle.secondary,
                custom_id="tab_server",
            )
            btn_server.callback = self._on_server_clicked
            self.add_item(btn_server)

            # Tab 3: Roles
            btn_roles = discord.ui.Button(
                label="Roles",
                style=discord.ButtonStyle.primary if self.current_tab == "roles" else discord.ButtonStyle.secondary,
                custom_id="tab_roles",
            )
            btn_roles.callback = self._on_roles_clicked
            self.add_item(btn_roles)

    async def _on_profile_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can change tabs.", ephemeral=True)
            return
        self.current_tab = "profile"
        self._build_tabs()
        container = self.render_container()
        await edit_container_response(interaction, container, view=self)

    async def _on_server_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can change tabs.", ephemeral=True)
            return
        self.current_tab = "server"
        self._build_tabs()
        container = self.render_container()
        await edit_container_response(interaction, container, view=self)

    async def _on_roles_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can change tabs.", ephemeral=True)
            return
        self.current_tab = "roles"
        self._build_tabs()
        container = self.render_container()
        await edit_container_response(interaction, container, view=self)

    def render_container(self) -> KyroContainer:
        target = self.target
        full_user = self.full_user
        is_member = isinstance(target, discord.Member)

        container = KyroContainer(accent_color=None)

        # Asset links header (no buttons, clean text links)
        links = [f"[Avatar]({target.display_avatar.url})"]
        if getattr(full_user, "banner", None):
            links.append(f"[Banner]({full_user.banner.url})")
        links_str = " | ".join(links)

        # ─── TAB 1: PROFILE ───────────────────────────────────────────────────
        if self.current_tab == "profile":
            created_ts = int(target.created_at.timestamp())
            badges = []
            flags = target.public_flags
            if flags.staff:
                badges.append("Discord Staff")
            if flags.partner:
                badges.append("Partnered Owner")
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

            badges_str = ", ".join(badges) if badges else "Standard User"
            account_type = "Bot Account" if target.bot else "Human User"

            accent = getattr(full_user, "accent_color", None)
            accent_str = f"#{accent.value:06X}" if accent else "None"

            container.add_section(
                content=(
                    f"### {target.name}\n"
                    f"> **Assets:** {links_str}\n\n"
                    f"**Account Identity**\n"
                    f"Username: `{target.name}`\n"
                    f"Display Name: `{target.display_name}`\n"
                    f"User ID: `{target.id}`\n"
                    f"Created: <t:{created_ts}:F> (<t:{created_ts}:R>)\n"
                    f"Type: `{account_type}`\n"
                    f"Badges: `{badges_str}`\n"
                    f"Accent Color: `{accent_str}`"
                )
            )

        # ─── TAB 2: SERVER STANDING ───────────────────────────────────────────
        elif self.current_tab == "server" and is_member:
            joined_ts = int(target.joined_at.timestamp()) if target.joined_at else 0
            joined_str = f"<t:{joined_ts}:F> (<t:{joined_ts}:R>)" if joined_ts else "Unknown"

            # Join position
            join_pos_str = "N/A"
            if self.ctx.guild:
                sorted_members = sorted(
                    [m for m in self.ctx.guild.members if m.joined_at],
                    key=lambda m: m.joined_at,
                )
                try:
                    pos = sorted_members.index(target) + 1
                    join_pos_str = f"#{pos:,} of {len(sorted_members):,}"
                except ValueError:
                    pass

            nickname_str = target.nick if target.nick else "None"
            booster_str = f"Since <t:{int(target.premium_since.timestamp())}:R>" if target.premium_since else "No"
            timeout_str = f"Until <t:{int(target.timed_out_until.timestamp())}:R>" if getattr(target, "timed_out_until", None) else "No"

            # Key permissions
            perms = target.guild_permissions
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

            perms_block = ", ".join(f"`{p}`" for p in key_perms) if key_perms else "`Standard Member`"

            container.add_section(
                content=(
                    f"### {target.name} — Server Standing\n"
                    f"> **Assets:** {links_str}\n\n"
                    f"**Membership Info**\n"
                    f"Joined: {joined_str}\n"
                    f"Join Position: `{join_pos_str}`\n"
                    f"Server Nickname: `{nickname_str}`\n"
                    f"Server Booster: `{booster_str}`\n"
                    f"Timed Out: `{timeout_str}`\n\n"
                    f"**Key Permissions**\n"
                    f"{perms_block}"
                )
            )

        # ─── TAB 3: ROLES ─────────────────────────────────────────────────────
        elif self.current_tab == "roles" and is_member:
            roles = [r for r in target.roles if not r.is_default()]
            roles.sort(key=lambda r: r.position, reverse=True)
            total_roles = len(roles)

            top_role_str = target.top_role.name if target.top_role != self.ctx.guild.default_role else "None"
            role_tags = [f"`@{r.name}`" for r in roles]
            roles_block = ", ".join(role_tags) if role_tags else "No roles assigned"

            container.add_section(
                content=(
                    f"### {target.name} — Roles Overview\n"
                    f"> **Assets:** {links_str}\n\n"
                    f"**Roles Statistics**\n"
                    f"Total Roles: `{total_roles}`\n"
                    f"Highest Role: `@{top_role_str}`\n\n"
                    f"**Assigned Roles**\n"
                    f"{roles_block}"
                )
            )

        container.add_thumbnail(target.display_avatar.url)
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.ctx.author.name}")
        return container

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class UserInfo(commands.Cog, name="General-UserInfo"):
    """User Information Module."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="userinfo",
        aliases=["ui", "whois"],
        description="View interactive user dossier with Profile, Server, and Roles tabs.",
    )
    @app_commands.describe(member="Member or user to inspect")
    async def userinfo(
        self,
        ctx: CustomContext,
        member: Optional[discord.Member | discord.User] = None,
    ) -> None:
        """Display 3-tab interactive user dossier."""
        target = member or ctx.author

        full_user = target
        try:
            full_user = await self.bot.fetch_user(target.id)
        except Exception:
            pass

        view = UserInfoView(ctx, target, full_user)
        container = view.render_container()
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(UserInfo(bot))
