"""
Kyro Discord Bot - Role Information & Roster Management Module
Unified interactive command for role dossier, permissions matrix, and roster
powered by Discord Components V2 with 3 persistent neutral tabs (Overview, Permissions, Members).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import resolve_role
from src.utils.containers import (
    KyroContainer,
    send_container_response,
    edit_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.RoleInfo")

# Master permission matrix list (Discord role permissions)
ROLE_PERMISSIONS_LIST: list[tuple[str, str]] = [
    ("administrator", "Administrator"),
    ("view_audit_log", "View Audit Log"),
    ("manage_guild", "Manage Server"),
    ("manage_roles", "Manage Roles"),
    ("manage_channels", "Manage Channels"),
    ("kick_members", "Kick Members"),
    ("ban_members", "Ban Members"),
    ("moderate_members", "Timeout Members"),
    ("manage_emojis_and_stickers", "Manage Expressions"),
    ("manage_webhooks", "Manage Webhooks"),
    ("view_channel", "View Channels"),
    ("send_messages", "Send Messages"),
    ("embed_links", "Embed Links"),
    ("attach_files", "Attach Files"),
    ("add_reactions", "Add Reactions"),
    ("use_external_emojis", "External Emojis"),
    ("mention_everyone", "Mention Everyone"),
    ("manage_messages", "Manage Messages"),
    ("read_message_history", "Read History"),
    ("connect", "Connect"),
    ("speak", "Speak"),
    ("video", "Video"),
    ("mute_members", "Mute Members"),
    ("deafen_members", "Deafen Members"),
    ("move_members", "Move Members"),
]


class RoleInfoView(discord.ui.View):
    """Interactive 3-tab view for role dossier, permissions, and member roster."""

    def __init__(
        self,
        ctx: CustomContext,
        target_role: discord.Role,
        members: list[discord.Member],
        initial_tab: str = "overview",
        per_page: int = 15,
    ) -> None:
        super().__init__(timeout=120)
        self.ctx = ctx
        self.role = target_role
        self.members = members
        self.current_tab = initial_tab
        self.member_page = 0
        self.per_page = per_page
        self.max_page = max(0, (len(members) - 1) // per_page)
        self._build_components()

    def _build_components(self) -> None:
        """Build the 3 persistent navigation buttons (all neutral secondary, active tab disabled)."""
        self.clear_items()

        # Row 0: 3 Persistent Navigation Tabs
        btn_overview = discord.ui.Button(
            label="Overview",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_tab == "overview"),
            custom_id="roleinfo_tab_overview",
            row=0,
        )
        btn_overview.callback = self._on_overview_clicked
        self.add_item(btn_overview)

        btn_permissions = discord.ui.Button(
            label="Permissions",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_tab == "permissions"),
            custom_id="roleinfo_tab_permissions",
            row=0,
        )
        btn_permissions.callback = self._on_permissions_clicked
        self.add_item(btn_permissions)

        btn_members = discord.ui.Button(
            label="Members",
            style=discord.ButtonStyle.secondary,
            disabled=(self.current_tab == "members"),
            custom_id="roleinfo_tab_members",
            row=0,
        )
        btn_members.callback = self._on_members_clicked
        self.add_item(btn_members)

        # Row 1: Pagination (only active on Members tab when multiple pages exist)
        if self.current_tab == "members" and self.max_page > 0:
            btn_prev = discord.ui.Button(
                label="Previous",
                style=discord.ButtonStyle.secondary,
                disabled=self.member_page == 0,
                custom_id="roleinfo_page_prev",
                row=1,
            )
            btn_prev.callback = self._on_prev_page_clicked
            self.add_item(btn_prev)

            btn_next = discord.ui.Button(
                label="Next",
                style=discord.ButtonStyle.secondary,
                disabled=self.member_page >= self.max_page,
                custom_id="roleinfo_page_next",
                row=1,
            )
            btn_next.callback = self._on_next_page_clicked
            self.add_item(btn_next)

    # ---------------- TAB RENDERING ----------------

    def _render_overview(self) -> KyroContainer:
        """Tab 1: Kyro signature Role Overview card."""
        e_reg = self.ctx.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        created_ts = int(self.role.created_at.timestamp())
        hex_color = f"#{self.role.color.value:06X}" if self.role.color.value else "None"
        hierarchy_pos = f"{self.role.position}"

        hoist_str = "Yes" if self.role.hoist else "No"
        mention_str = "Yes" if self.role.mentionable else "No"

        # Classification without parentheses
        if self.role.is_default():
            role_type = "Default Role"
        elif self.role.is_bot_managed():
            role_type = "Bot Integration"
        elif self.role.is_premium_subscriber():
            role_type = "Server Booster"
        elif self.role.is_integration():
            role_type = "External Integration"
        elif getattr(self.role.tags, "guild_connections", False):
            role_type = "Linked Connection"
        elif self.role.managed:
            role_type = "Managed Role"
        else:
            role_type = "Standard Role"

        perms = self.role.permissions
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

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Role Information**\n"
                f"> Details, permissions, and members for {self.role.mention}."
            )
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Role:** {self.role.mention}\n"
            f"{dot} **Role ID:** `{self.role.id}`\n"
            f"{dot} **Color:** `{hex_color}` • **Position:** `{hierarchy_pos}`\n"
            f"{dot} **Members:** `{len(self.members)}` members\n"
            f"{dot} **Created:** <t:{created_ts}:D>"
        )
        container.add_separator(divider=True)

        container.add_text(
            f"**Settings & Type**\n"
            f"{dot} **Hoisted:** `{hoist_str}` • **Mentionable:** `{mention_str}`\n"
            f"{dot} **Role Type:** `{role_type}`"
        )
        container.add_separator(divider=True)

        container.add_text(
            f"**Key Permissions**\n"
            f"{perms_str}"
        )

        if self.role.display_icon:
            container.add_thumbnail(str(self.role.display_icon.url))

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.ctx.author.display_name}")
        return container

    def _render_permissions(self) -> KyroContainer:
        """Tab 2: Role Permissions - strictly show only permissions enabled on this role with switch emoji."""
        perms = self.role.permissions
        is_admin = perms.administrator
        e_reg = self.ctx.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")
        sw_on = e_reg.get("icon_switch_on", "🟢")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Role Permissions**\n"
                f"> Enabled permissions for {self.role.mention}."
            )
        )
        container.add_separator(divider=True)

        lines: list[str] = []
        if is_admin:
            lines.append(f"{dot} **Administrator:** {sw_on}")
            lines.append(f"> This role possesses full Administrator privileges across the server.")
        else:
            for perm_attr, perm_name in ROLE_PERMISSIONS_LIST:
                if getattr(perms, perm_attr, False):
                    lines.append(f"{dot} **{perm_name}:** {sw_on}")

        if not lines:
            lines.append(f"{dot} No elevated permissions enabled on this role.")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.ctx.author.display_name}")
        return container

    def _render_members(self) -> KyroContainer:
        """Tab 3: Role Member Roster."""
        e_reg = self.ctx.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)

        if self.role.is_default():
            container.add_section(
                content=(
                    f"**Role Members**\n"
                    f"> The `@everyone` role contains all server members. Use `membercount` for full totals."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {self.ctx.author.display_name}")
            return container

        count = len(self.members)
        count_str = f"{count:,} member" if count == 1 else f"{count:,} members"

        container.add_section(
            content=(
                f"**Role Members**\n"
                f"> Showing {count_str} with {self.role.mention}."
            )
        )
        container.add_separator(divider=True)

        start = self.member_page * self.per_page
        end = start + self.per_page
        current_slice = self.members[start:end]

        lines: list[str] = []
        for m in current_slice:
            tag = " `[BOT]`" if m.bot else ""
            lines.append(f"{dot} **{m.display_name}**{tag} `{m.id}`")

        container.add_text("\n".join(lines) if lines else f"{dot} No members found on this page.")
        container.add_separator(divider=True)

        page_info = f"Page {self.member_page + 1} of {self.max_page + 1} • " if self.max_page > 0 else ""
        container.add_text(f"-# {page_info}Requested by {self.ctx.author.display_name}")
        return container

    def render_container(self) -> KyroContainer:
        """Render active container according to selected tab."""
        if self.current_tab == "permissions":
            return self._render_permissions()
        elif self.current_tab == "members":
            return self._render_members()
        return self._render_overview()

    # ---------------- EVENT HANDLERS ----------------

    async def _on_overview_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can change tabs.", ephemeral=True)
            return
        self.current_tab = "overview"
        self._build_components()
        container = self.render_container()
        await edit_container_response(interaction, container, view=self)

    async def _on_permissions_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can change tabs.", ephemeral=True)
            return
        self.current_tab = "permissions"
        self._build_components()
        container = self.render_container()
        await edit_container_response(interaction, container, view=self)

    async def _on_members_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can change tabs.", ephemeral=True)
            return
        self.current_tab = "members"
        self._build_components()
        container = self.render_container()
        await edit_container_response(interaction, container, view=self)

    async def _on_prev_page_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can flip pages.", ephemeral=True)
            return
        if self.member_page > 0:
            self.member_page -= 1
            self._build_components()
            container = self.render_container()
            await edit_container_response(interaction, container, view=self)

    async def _on_next_page_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can flip pages.", ephemeral=True)
            return
        if self.member_page < self.max_page:
            self.member_page += 1
            self._build_components()
            container = self.render_container()
            await edit_container_response(interaction, container, view=self)

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class RoleInfo(commands.Cog, name="Moderation-RoleInfo"):
    """Unified role intelligence dossier, permissions audit, and roster explorer."""
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
            f"{dot} `{prefix}roleinfo <role-name>`\n"
            f"{dot} `{prefix}inrole <@role>`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    @commands.hybrid_command(
        name="roleinfo",
        aliases=["inrole", "rolemembers", "role-info"],
        description="View comprehensive role dossier, permissions matrix, and roster.",
    )
    @app_commands.describe(role="Role mention, ID, or name to inspect")
    @commands.guild_only()
    async def roleinfo(self, ctx: CustomContext, *, role: Optional[str] = None) -> None:
        """Inspect a server role with interactive Overview, Permissions, and Members tabs."""
        guild = ctx.guild
        if not guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        # Case 1: No role passed -> Show clean usage card
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

        # Ensure all members are cached for large guilds
        if not guild.chunked:
            try:
                await guild.chunk(cache=True)
            except Exception as e:
                logger.debug(f"Guild chunking skipped/failed: {e}")

        # If user ran `inrole` / `rolemembers`, jump directly to Members tab
        invoked_name = ctx.invoked_with.lower() if ctx.invoked_with else "roleinfo"
        initial_tab = "members" if invoked_name in ("inrole", "rolemembers") else "overview"

        view = RoleInfoView(
            ctx=ctx,
            target_role=target_role,
            members=target_role.members,
            initial_tab=initial_tab,
            per_page=15,
        )
        container = view.render_container()

        await send_container_response(
            ctx,
            container,
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: KyroBot) -> None:
    """Load the RoleInfo cog into KyroBot."""
    await bot.add_cog(RoleInfo(bot))
