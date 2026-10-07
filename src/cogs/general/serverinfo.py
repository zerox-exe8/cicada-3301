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


class ServerModuleSelect(discord.ui.Select):
    """Dropdown menu for switching between server info modules."""

    def __init__(self, current_module: str = "overview") -> None:
        options = [
            discord.SelectOption(
                label="Overview",
                value="overview",
                description="Core identity, highlighted owner & server creation",
                default=current_module == "overview",
            ),
            discord.SelectOption(
                label="Members",
                value="members",
                description="Total population, humans, bots & presences",
                default=current_module == "members",
            ),
            discord.SelectOption(
                label="Channels",
                value="channels",
                description="Channel hierarchy, rooms & special channels",
                default=current_module == "channels",
            ),
            discord.SelectOption(
                label="Security",
                value="security",
                description="Safety levels, 2FA, nitro tier & server limits",
                default=current_module == "security",
            ),
            discord.SelectOption(
                label="Roles",
                value="roles",
                description="Role hierarchy, permissions & expressions",
                default=current_module == "roles",
            ),
        ]
        super().__init__(
            placeholder="Select Module...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="serverinfo_module_select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: ServerInfoView = self.view  # type: ignore
        if interaction.user.id != view.ctx.author.id:
            await interaction.response.send_message(
                "Only the command invoker can change modules.",
                ephemeral=True,
            )
            return

        view.current_module = self.values[0]
        view.build_items()
        container = view.render_container()
        await edit_container_response(interaction, container, view=view)


class ServerInfoView(discord.ui.View):
    """Interactive module view for comprehensive server dossier."""

    def __init__(self, ctx: CustomContext, guild: discord.Guild) -> None:
        super().__init__(timeout=120)
        self.ctx = ctx
        self.guild = guild
        self.current_module = "overview"
        self.build_items()

    def build_items(self) -> None:
        self.clear_items()
        self.add_item(ServerModuleSelect(current_module=self.current_module))

    def render_container(self) -> KyroContainer:
        guild = self.guild
        container = KyroContainer(accent_color=None)
        e_reg = getattr(self.ctx.bot, "custom_emojis", {})
        dot = e_reg.get("heart_dot", "❥")

        # Asset links header (Icon, Banner, Splash)
        links = []
        if guild.icon:
            links.append(f"[Icon]({guild.icon.url})")
        if guild.banner:
            links.append(f"[Banner]({guild.banner.url})")
        if guild.splash:
            links.append(f"[Splash]({guild.splash.url})")
        links_str = " | ".join(links) if links else "None"

        # ─── MODULE 1: OVERVIEW ────────────────────────────────────────────────
        if self.current_module == "overview":
            created_ts = int(guild.created_at.timestamp())
            owner = guild.owner or guild.get_member(guild.owner_id)

            # Highlighted owner information
            if owner:
                owner_tag = f"`{owner.name}`"
                owner_mention = f"<@{owner.id}>"
                owner_id_str = f"`{owner.id}`"
                if owner.joined_at:
                    owner_tenure = f"<t:{int(owner.joined_at.timestamp())}:D> (<t:{int(owner.joined_at.timestamp())}:R>)"
                else:
                    owner_tenure = f"<t:{int(owner.created_at.timestamp())}:R>"
            else:
                owner_tag = "`Unknown`"
                owner_mention = f"<@{guild.owner_id}>"
                owner_id_str = f"`{guild.owner_id}`"
                owner_tenure = "Unknown"

            vanity = f"discord.gg/{guild.vanity_url_code}" if getattr(guild, "vanity_url_code", None) else "None"
            locale = str(guild.preferred_locale)

            # Notable feature badges
            features_map = {
                "COMMUNITY": "Community",
                "PARTNERED": "Partnered",
                "VERIFIED": "Verified",
                "DISCOVERABLE": "Discoverable",
                "VANITY_URL": "Vanity URL",
                "INVITE_SPLASH": "Splash Invite",
                "BANNER": "Banner",
                "ANIMATED_ICON": "Animated Icon",
                "MEMBER_VERIFICATION_GATE_ENABLED": "Member Screening",
                "AUTO_MODERATION": "AutoMod",
                "ROLE_ICONS": "Role Icons",
            }
            notable = [features_map[f] for f in guild.features if f in features_map]
            if not notable and guild.features:
                notable = [f.replace("_", " ").title() for f in guild.features[:6]]
            badges_str = " ".join(f"`{b}`" for b in notable) if notable else "`Standard`"

            desc_block = f"> *\"{guild.description}\"*\n\n" if guild.description else ""

            container.add_section(
                content=(
                    f"### {guild.name}\n"
                    f"> **Assets:** {links_str}\n\n"
                    f"{desc_block}"
                    f"**Server Owner**\n"
                    f"{dot} Mention: {owner_mention} ({owner_tag})\n"
                    f"{dot} Owner ID: {owner_id_str}\n"
                    f"{dot} Ownership Since: {owner_tenure}\n\n"
                    f"**Server Identity**\n"
                    f"{dot} Server ID: `{guild.id}`\n"
                    f"{dot} Created On: <t:{created_ts}:D> (<t:{created_ts}:R>)\n"
                    f"{dot} Primary Locale: `{locale}`\n"
                    f"{dot} Assigned Shard: `#{guild.shard_id}`\n"
                    f"{dot} Vanity Invite: `{vanity}`\n\n"
                    f"**Perks & Badges**\n"
                    f"{dot} Badges: {badges_str}"
                )
            )

        # ─── MODULE 2: MEMBERS ────────────────────────────────────────────────
        elif self.current_module == "members":
            total_members = guild.member_count or len(guild.members)
            bots_count = sum(1 for m in guild.members if m.bot)
            humans_count = max(0, total_members - bots_count)
            humans_pct = round((humans_count / total_members) * 100 if total_members else 0)
            bots_pct = round((bots_count / total_members) * 100 if total_members else 0)

            # Presences (from cached members)
            online_count = sum(1 for m in guild.members if m.status == discord.Status.online)
            idle_count = sum(1 for m in guild.members if m.status == discord.Status.idle)
            dnd_count = sum(1 for m in guild.members if m.status == discord.Status.dnd)
            offline_count = sum(1 for m in guild.members if m.status == discord.Status.offline)

            # Staff: Administrator or Manage Guild permission
            staff_count = sum(
                1 for m in guild.members
                if not m.bot and (m.guild_permissions.administrator or m.guild_permissions.manage_guild)
            )
            boosters_count = len(guild.premium_subscribers)

            container.add_section(
                content=(
                    f"### {guild.name} — Members\n"
                    f"> **Assets:** {links_str}\n\n"
                    f"**Demographics**\n"
                    f"{dot} Total Population: `{total_members:,}`\n"
                    f"{dot} Real Humans: `{humans_count:,}` ({humans_pct}%)\n"
                    f"{dot} Bot Accounts: `{bots_count:,}` ({bots_pct}%)\n\n"
                    f"**Status & Presence**\n"
                    f"{dot} Online: `{online_count:,}`\n"
                    f"{dot} Idle: `{idle_count:,}`\n"
                    f"{dot} Do Not Disturb: `{dnd_count:,}`\n"
                    f"{dot} Offline: `{offline_count:,}`\n\n"
                    f"**Staff & Supporters**\n"
                    f"{dot} Server Staff: `{staff_count:,}` members\n"
                    f"{dot} Active Boosters: `{boosters_count:,}` members"
                )
            )

        # ─── MODULE 3: CHANNELS ───────────────────────────────────────────────
        elif self.current_module == "channels":
            text_channels = len(guild.text_channels)
            voice_channels = len(guild.voice_channels)
            stage_channels = len(guild.stage_channels)
            forum_channels = len(guild.forums) if hasattr(guild, "forums") else 0
            news_channels = sum(1 for c in guild.text_channels if c.is_news())
            categories = len(guild.categories)
            threads = len(guild.threads) if hasattr(guild, "threads") else 0
            total_channels = text_channels + voice_channels + stage_channels + forum_channels

            rules_ch = f"<#{guild.rules_channel.id}>" if guild.rules_channel else "`None`"
            sys_ch = f"<#{guild.system_channel.id}>" if guild.system_channel else "`None`"
            safety_ch = f"<#{guild.public_updates_channel.id}>" if guild.public_updates_channel else "`None`"
            if guild.afk_channel:
                afk_ch = f"<#{guild.afk_channel.id}> (`{guild.afk_timeout // 60}m timeout`)"
            else:
                afk_ch = "`None`"

            container.add_section(
                content=(
                    f"### {guild.name} — Channels\n"
                    f"> **Assets:** {links_str}\n\n"
                    f"**Channel Structure**\n"
                    f"{dot} Total Channels: `{total_channels}`\n"
                    f"{dot} Categories: `{categories}`\n"
                    f"{dot} Text Channels: `{text_channels}`\n"
                    f"{dot} Voice Channels: `{voice_channels}`\n"
                    f"{dot} Announcement: `{news_channels}`\n"
                    f"{dot} Stage Rooms: `{stage_channels}`\n"
                    f"{dot} Forum Rooms: `{forum_channels}`\n"
                    f"{dot} Active Threads: `{threads}`\n\n"
                    f"**Special Configuration**\n"
                    f"{dot} Rules Channel: {rules_ch}\n"
                    f"{dot} System Messages: {sys_ch}\n"
                    f"{dot} Safety Updates: {safety_ch}\n"
                    f"{dot} AFK Channel: {afk_ch}"
                )
            )

        # ─── MODULE 4: SECURITY ───────────────────────────────────────────────
        elif self.current_module == "security":
            verif_level = str(guild.verification_level).replace("_", " ").title()
            explicit_filter = str(guild.explicit_content_filter).replace("_", " ").title()
            mfa_status = "Enabled (Required)" if guild.mfa_level else "Disabled"
            default_notifs = "All Messages" if guild.default_notifications == discord.NotificationLevel.all_messages else "Only @mentions"
            nsfw_level = str(guild.nsfw_level).replace("_", " ").title()

            boost_tier = guild.premium_tier
            boost_count = guild.premium_subscription_count or 0
            bitrate_kbps = guild.bitrate_limit // 1000
            filesize_mb = round(guild.filesize_limit / (1024 * 1024))
            emoji_capacity = guild.emoji_limit

            container.add_section(
                content=(
                    f"### {guild.name} — Security & Protection\n"
                    f"> **Assets:** {links_str}\n\n"
                    f"**Safety Protocols**\n"
                    f"{dot} Verification Level: `{verif_level}`\n"
                    f"{dot} Content Filter: `{explicit_filter}`\n"
                    f"{dot} 2FA Moderation: `{mfa_status}`\n"
                    f"{dot} Default Notifications: `{default_notifs}`\n"
                    f"{dot} NSFW Rating: `{nsfw_level}`\n\n"
                    f"**Boost Level & Tier Perks**\n"
                    f"{dot} Server Tier: `Level {boost_tier}` ({boost_count} Boosts)\n"
                    f"{dot} Max Audio Bitrate: `{bitrate_kbps} kbps`\n"
                    f"{dot} Upload File Limit: `{filesize_mb} MB`\n"
                    f"{dot} Emoji Capacity: `{emoji_capacity} slots`"
                )
            )

        # ─── MODULE 5: ROLES ──────────────────────────────────────────────────
        elif self.current_module == "roles":
            roles = [r for r in guild.roles if not r.is_default()]
            roles.sort(key=lambda r: r.position, reverse=True)
            total_roles = len(roles)

            top_role_str = f"@{roles[0].name}" if roles else "None"
            hoisted_count = sum(1 for r in roles if r.hoist)
            mentionable_count = sum(1 for r in roles if r.mentionable)
            managed_count = sum(1 for r in roles if r.managed)
            admin_roles = [r for r in roles if r.permissions.administrator]

            static_emojis = sum(1 for e in guild.emojis if not e.animated)
            animated_emojis = sum(1 for e in guild.emojis if e.animated)
            total_emojis = len(guild.emojis)
            total_stickers = len(guild.stickers)

            shown_roles = [f"`@{r.name}`" for r in roles[:20]]
            roles_block = ", ".join(shown_roles) if shown_roles else "None"
            more_str = f"\n*(+{total_roles - 20} more roles)*" if total_roles > 20 else ""

            container.add_section(
                content=(
                    f"### {guild.name} — Roles & Hierarchy\n"
                    f"> **Assets:** {links_str}\n\n"
                    f"**Role Analytics**\n"
                    f"{dot} Total Roles: `{total_roles}`\n"
                    f"{dot} Highest Role: `{top_role_str}`\n"
                    f"{dot} Hoisted Roles: `{hoisted_count}`\n"
                    f"{dot} Mentionable Roles: `{mentionable_count}`\n"
                    f"{dot} Bot / Managed Roles: `{managed_count}`\n"
                    f"{dot} Administrator Roles: `{len(admin_roles)}`\n\n"
                    f"**Server Expressions**\n"
                    f"{dot} Total Emojis: `{total_emojis}` ({static_emojis} Static, {animated_emojis} Animated)\n"
                    f"{dot} Custom Stickers: `{total_stickers}`\n\n"
                    f"**Top Hierarchy**\n"
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
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True


class ServerInfo(commands.Cog, name="General-ServerInfo"):
    """Server Information Module."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="serverinfo",
        aliases=["si", "guildinfo"],
        description="View interactive server dossier across dedicated modules.",
    )
    @commands.guild_only()
    async def serverinfo(self, ctx: CustomContext) -> None:
        """Display interactive server dossier with module selector."""
        guild = ctx.guild
        if not guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        view = ServerInfoView(ctx, guild)
        container = view.render_container()
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ServerInfo(bot))
