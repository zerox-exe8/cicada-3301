"""
Kyro Discord Bot - Server Information Module
Top-level interactive server dossier with 3 distinct tabs (Overview, Channels & Population, Roles),
zero bullet dots, zero unwanted mentions, and clean formatting.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    KyroContainer,
    send_container_response,
    edit_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.General.ServerInfo")


class ServerInfoView(discord.ui.View):
    """Interactive 3-tab view for server information (Overview, Channels & Population, Roles)."""

    def __init__(self, ctx: CustomContext, guild: discord.Guild) -> None:
        super().__init__(timeout=120)
        self.ctx = ctx
        self.guild = guild
        self.current_tab = "overview"
        self._build_tabs()

    def _build_tabs(self) -> None:
        self.clear_items()

        # Tab 1: Overview
        btn_overview = discord.ui.Button(
            label="Overview",
            style=discord.ButtonStyle.primary if self.current_tab == "overview" else discord.ButtonStyle.secondary,
            custom_id="tab_overview",
        )
        btn_overview.callback = self._on_overview_clicked
        self.add_item(btn_overview)

        # Tab 2: Channels & Population
        btn_stats = discord.ui.Button(
            label="Channels & Population",
            style=discord.ButtonStyle.primary if self.current_tab == "stats" else discord.ButtonStyle.secondary,
            custom_id="tab_stats",
        )
        btn_stats.callback = self._on_stats_clicked
        self.add_item(btn_stats)

        # Tab 3: Roles
        btn_roles = discord.ui.Button(
            label="Roles",
            style=discord.ButtonStyle.primary if self.current_tab == "roles" else discord.ButtonStyle.secondary,
            custom_id="tab_roles",
        )
        btn_roles.callback = self._on_roles_clicked
        self.add_item(btn_roles)

    async def _on_overview_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can change tabs.", ephemeral=True)
            return
        self.current_tab = "overview"
        self._build_tabs()
        container = self.render_container()
        await edit_container_response(interaction, container, view=self)

    async def _on_stats_clicked(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can change tabs.", ephemeral=True)
            return
        self.current_tab = "stats"
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
        guild = self.guild
        container = KyroContainer(accent_color=None)

        # Asset links header (no buttons, clean text links)
        links = []
        if guild.icon:
            links.append(f"[Icon]({guild.icon.url})")
        if guild.banner:
            links.append(f"[Banner]({guild.banner.url})")
        if guild.splash:
            links.append(f"[Splash]({guild.splash.url})")
        links_str = " | ".join(links) if links else "No Assets"

        # ─── TAB 1: OVERVIEW ──────────────────────────────────────────────────
        if self.current_tab == "overview":
            created_ts = int(guild.created_at.timestamp())
            owner = guild.owner
            owner_str = f"{owner.name} (ID: {owner.id})" if owner else f"ID: {guild.owner_id}"

            boost_tier = guild.premium_tier
            boost_count = guild.premium_subscription_count or 0
            boosters_count = len(guild.premium_subscribers)

            verif_level = str(guild.verification_level).replace("_", " ").title()
            explicit_filter = str(guild.explicit_content_filter).replace("_", " ").title()
            vanity_str = f"discord.gg/{guild.vanity_url_code}" if getattr(guild, "vanity_url_code", None) else "None"

            container.add_section(
                content=(
                    f"### {guild.name}\n"
                    f"> **Assets:** {links_str}\n\n"
                    f"**Server Identity**\n"
                    f"Owner: `{owner_str}`\n"
                    f"Server ID: `{guild.id}`\n"
                    f"Created: <t:{created_ts}:F> (<t:{created_ts}:R>)\n"
                    f"Language: `{guild.preferred_locale}`\n\n"
                    f"**Security & Boosts**\n"
                    f"Verification: `{verif_level}`\n"
                    f"Content Filter: `{explicit_filter}`\n"
                    f"Boost Status: Level `{boost_tier}` ({boost_count} Boosts, {boosters_count} Boosters)\n"
                    f"Vanity URL: `{vanity_str}`"
                )
            )

        # ─── TAB 2: CHANNELS & POPULATION ──────────────────────────────────────
        elif self.current_tab == "stats":
            total_members = guild.member_count or len(guild.members)
            bots_count = sum(1 for m in guild.members if m.bot)
            humans_count = total_members - bots_count
            humans_pct = round((humans_count / total_members) * 100 if total_members else 0)
            bots_pct = round((bots_count / total_members) * 100 if total_members else 0)

            text_channels = len(guild.text_channels)
            voice_channels = len(guild.voice_channels)
            stage_channels = len(guild.stage_channels)
            forum_channels = len(guild.forums) if hasattr(guild, "forums") else 0
            categories = len(guild.categories)
            total_channels = text_channels + voice_channels + stage_channels + forum_channels

            static_emojis = sum(1 for e in guild.emojis if not e.animated)
            animated_emojis = sum(1 for e in guild.emojis if e.animated)
            total_emojis = len(guild.emojis)
            total_stickers = len(guild.stickers)

            container.add_section(
                content=(
                    f"### {guild.name} — Channels & Population\n"
                    f"> **Assets:** {links_str}\n\n"
                    f"**Members Population**\n"
                    f"Total Members: `{total_members:,}`\n"
                    f"Real Humans: `{humans_count:,}` ({humans_pct}%)\n"
                    f"Bot Accounts: `{bots_count:,}` ({bots_pct}%)\n\n"
                    f"**Channel Structure**\n"
                    f"Total Channels: `{total_channels}`\n"
                    f"Text Channels: `{text_channels}`\n"
                    f"Voice Channels: `{voice_channels}`\n"
                    f"Stage Channels: `{stage_channels}`\n"
                    f"Forum Channels: `{forum_channels}`\n"
                    f"Categories: `{categories}`\n\n"
                    f"**Server Expressions**\n"
                    f"Total Emojis: `{total_emojis}` ({static_emojis} Static, {animated_emojis} Animated)\n"
                    f"Total Stickers: `{total_stickers}`"
                )
            )

        # ─── TAB 3: ROLES ─────────────────────────────────────────────────────
        elif self.current_tab == "roles":
            roles = [r for r in guild.roles if not r.is_default()]
            roles.sort(key=lambda r: r.position, reverse=True)
            total_roles = len(roles)

            top_role_str = roles[0].name if roles else "None"
            admin_roles = [f"`@{r.name}`" for r in roles if r.permissions.administrator]
            admin_str = ", ".join(admin_roles) if admin_roles else "None"

            hoisted_count = sum(1 for r in roles if r.hoist)
            mentionable_count = sum(1 for r in roles if r.mentionable)

            # Clean role tags without raw user pings
            shown_roles = [f"`@{r.name}`" for r in roles[:25]]
            roles_block = ", ".join(shown_roles) if shown_roles else "None"
            more_str = f"\n*(+{total_roles - 25} more roles)*" if total_roles > 25 else ""

            container.add_section(
                content=(
                    f"### {guild.name} — Roles Overview\n"
                    f"> **Assets:** {links_str}\n\n"
                    f"**Roles Statistics**\n"
                    f"Total Roles: `{total_roles}`\n"
                    f"Highest Role: `@{top_role_str}`\n"
                    f"Hoisted Roles: `{hoisted_count}`\n"
                    f"Mentionable Roles: `{mentionable_count}`\n"
                    f"Administrator Roles: {admin_str}\n\n"
                    f"**Hierarchy Roster**\n"
                    f"{roles_block}{more_str}"
                )
            )

        if guild.icon:
            container.add_thumbnail(guild.icon.url)

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.ctx.author.name}")
        return container

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class ServerInfo(commands.Cog, name="General-ServerInfo"):
    """Server Information Module."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="serverinfo",
        aliases=["si", "guildinfo"],
        description="View interactive server dossier with Overview, Channels, and Roles tabs.",
    )
    @commands.guild_only()
    async def serverinfo(self, ctx: CustomContext) -> None:
        """Display 3-tab interactive server dossier."""
        guild = ctx.guild
        if not guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        view = ServerInfoView(ctx, guild)
        container = view.render_container()
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ServerInfo(bot))
