from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response
from src.cogs.antinuke._views import AntinukeControlView

if TYPE_CHECKING:
    from src.core.bot import KyroBot


def build_antinuke_card(bot: KyroBot, guild: discord.Guild, author_id: int) -> tuple[KyroContainer, AntinukeControlView]:
    """Assemble the clean, premium Antinuke dashboard container."""
    cfg = bot.antinuke_mgr.get_settings(guild.id)
    is_enabled = cfg.get("enabled", False)
    punishment = cfg.get("punishment", "ban").capitalize()
    log_ch = bot.antinuke_mgr.get_log_channel(guild)
    eo_count = len(bot.antinuke_mgr.get_extra_owners(guild.id))

    container = KyroContainer(accent_color=None)
    # Title with clean user-friendly tagline directly beneath
    container.add_section(
        content=(
            "**Kyro Antinuke**\n"
            "> *Real-time protection against nukes, raids, and unauthorized changes.*"
        )
    )
    container.add_separator(divider=True)

    # Full granular protection modules list (20 individual protections)
    modules = [
        ("Anti-Ban", cfg.get("ban_protection", True)),
        ("Anti-Kick", cfg.get("kick_protection", True)),
        ("Anti-Bot", cfg.get("bot_protection", True)),
        ("Anti-Prune", cfg.get("prune_protection", True)),
        ("Channel Create", cfg.get("channel_create_protection", cfg.get("channel_protection", True))),
        ("Channel Delete", cfg.get("channel_delete_protection", cfg.get("channel_protection", True))),
        ("Channel Update", cfg.get("channel_update_protection", cfg.get("channel_protection", True))),
        ("Role Create", cfg.get("role_create_protection", cfg.get("role_protection", True))),
        ("Role Delete", cfg.get("role_delete_protection", cfg.get("role_protection", True))),
        ("Role Update", cfg.get("role_update_protection", cfg.get("role_protection", True))),
        ("Everyone Disarm", cfg.get("everyone_protection", True)),
        ("Member Role", cfg.get("member_role_protection", True)),
        ("Vanity URL", cfg.get("vanity_protection", True)),
        ("Webhook Create", cfg.get("webhook_create_protection", cfg.get("webhook_protection", True))),
        ("Webhook Delete", cfg.get("webhook_delete_protection", cfg.get("webhook_protection", True))),
        ("Server Update", cfg.get("guild_update_protection", True)),
        ("AutoMod Rule", cfg.get("automod_protection", True)),
        ("Emoji Delete", cfg.get("emoji_protection", True)),
        ("Sticker Delete", cfg.get("sticker_protection", True)),
        ("Integrations", cfg.get("integration_protection", True)),
    ]

    # Render compact 2-per-line display without category clutter
    mod_items = []
    for name, state in modules:
        mod_tag = "`[Active]`" if (state and is_enabled) else "`[Disabled]`"
        mod_items.append(f"• {name} {mod_tag}")

    paired_lines = []
    for i in range(0, len(mod_items), 2):
        if i + 1 < len(mod_items):
            second = mod_items[i + 1].lstrip("• ")
            paired_lines.append(f"{mod_items[i]}  •  {second}")
        else:
            paired_lines.append(mod_items[i])

    container.add_text("\n".join(paired_lines))
    container.add_separator(divider=True)

    # Core configuration & status cleanly positioned at the bottom
    status_tag = "`[Active]`" if is_enabled else "`[Disabled]`"
    punish_tag = f"`[{punishment}]`"
    log_tag = log_ch.mention if log_ch else "`[None]`"

    bottom_lines = [
        f"• **Status:** {status_tag} **—** **Punishment:** {punish_tag}",
        f"• **Log Channel:** {log_tag}",
        f"• **Extra Owners:** `{eo_count}`",
    ]
    container.add_text("\n".join(bottom_lines))

    view = AntinukeControlView(bot, guild, author_id)
    return container, view


class AntinukePanelCog(commands.Cog):
    """Core Antinuke configuration and master control panel."""
    category: str = "Security"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: CustomContext) -> bool:
        """Only Guild Owner or registered Extra Owners can configure Antinuke."""
        if not ctx.guild:
            return False
        if ctx.author.id == ctx.guild.owner_id:
            return True
        if self.bot.antinuke_mgr.is_extra_owner(ctx.guild.id, ctx.author.id):
            return True
        raise commands.CheckFailure("Only the **Server Owner** or authorized **Extra Owners** can configure Antinuke.")

    @commands.hybrid_group(
        name="antinuke",
        aliases=["security", "an"],
        description="Master Antinuke control panel and configuration.",
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def antinuke(self, ctx: CustomContext) -> None:
        """Display the interactive Antinuke control card."""
        container, view = build_antinuke_card(self.bot, ctx.guild, ctx.author.id)
        await send_container_response(ctx, container, view=view)

    @antinuke.command(name="enable", description="Enable the Antinuke defense protocol.")
    async def antinuke_enable(self, ctx: CustomContext) -> None:
        """Turn on Antinuke protection."""
        await self.bot.antinuke_mgr.update_settings(ctx.guild.id, enabled=True)
        self.bot.antinuke_mgr.snapshot_guild_state(ctx.guild)

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Activated**")
        container.add_separator(divider=True)
        container.add_text("• **Status:** `[Active]` **—** **Punishment:** `[Ban]`")
        await send_container_response(ctx, container)

    @antinuke.command(name="disable", description="Disable the Antinuke defense protocol.")
    async def antinuke_disable(self, ctx: CustomContext) -> None:
        """Turn off Antinuke protection."""
        await self.bot.antinuke_mgr.update_settings(ctx.guild.id, enabled=False)

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Deactivated**")
        container.add_separator(divider=True)
        container.add_text("• **Status:** `[Disabled]`\n> *Use `,antinuke enable` to re-arm protection.*")
        await send_container_response(ctx, container)

    @antinuke.command(name="punishment", description="Set the punishment for unauthorized actions.")
    @app_commands.describe(action="Punishment to execute on attackers")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Ban Perpetrator", value="ban"),
            app_commands.Choice(name="Kick Perpetrator", value="kick"),
            app_commands.Choice(name="Strip Roles Only", value="strip_roles"),
        ]
    )
    async def antinuke_punishment(self, ctx: CustomContext, action: str) -> None:
        """Configure antinuke action upon breach."""
        clean_action = action.lower()
        if clean_action not in ["ban", "kick", "strip_roles"]:
            await ctx.send_error("Invalid punishment. Choose from: `ban`, `kick`, `strip_roles`.")
            return

        await self.bot.antinuke_mgr.update_settings(ctx.guild.id, punishment=clean_action)
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Punishment Updated**")
        container.add_separator(divider=True)
        container.add_text(f"• **New Action:** `[{clean_action.capitalize()}]`")
        await send_container_response(ctx, container)

    @antinuke.command(name="log", description="Bind a channel for antinuke incident alerts.")
    @app_commands.describe(channel="Target channel for security logs")
    async def antinuke_log(self, ctx: CustomContext, channel: discord.TextChannel) -> None:
        """Set antinuke incident logging channel."""
        await self.bot.antinuke_mgr.update_settings(ctx.guild.id, log_channel_id=channel.id)

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Log Channel Configured**")
        container.add_separator(divider=True)
        container.add_text(f"• **Target Channel:** {channel.mention}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load AntinukePanelCog."""
    await bot.add_cog(AntinukePanelCog(bot))
