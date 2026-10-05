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
    """Assemble the clean, straight-line Antinuke dashboard container with heart dot and switch emojis."""
    cfg = bot.antinuke_mgr.get_settings(guild.id)
    is_enabled = cfg.get("enabled", False)
    punishment = cfg.get("punishment", "ban").capitalize()
    log_ch = bot.antinuke_mgr.get_log_channel(guild)
    eo_count = len(bot.antinuke_mgr.get_extra_owners(guild.id))

    dot = bot.custom_emojis.get("heart_dot", "•")
    sw_on = bot.custom_emojis.get("icon_switch_on", "`[ON]`")
    sw_off = bot.custom_emojis.get("icon_switch_off", "`[OFF]`")

    container = KyroContainer(accent_color=None)
    # Title with user-friendly tagline directly beneath
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
        ("Anti-Channel Create", cfg.get("channel_create_protection", cfg.get("channel_protection", True))),
        ("Anti-Channel Delete", cfg.get("channel_delete_protection", cfg.get("channel_protection", True))),
        ("Anti-Channel Update", cfg.get("channel_update_protection", cfg.get("channel_protection", True))),
        ("Anti-Role Create", cfg.get("role_create_protection", cfg.get("role_protection", True))),
        ("Anti-Role Delete", cfg.get("role_delete_protection", cfg.get("role_protection", True))),
        ("Anti-Role Update", cfg.get("role_update_protection", cfg.get("role_protection", True))),
        ("Anti-Everyone", cfg.get("everyone_protection", True)),
        ("Anti-Member Role", cfg.get("member_role_protection", True)),
        ("Anti-Vanity", cfg.get("vanity_protection", True)),
        ("Anti-Webhook Create", cfg.get("webhook_create_protection", cfg.get("webhook_protection", True))),
        ("Anti-Webhook Delete", cfg.get("webhook_delete_protection", cfg.get("webhook_protection", True))),
        ("Anti-Server Update", cfg.get("guild_update_protection", True)),
        ("Anti-AutoMod", cfg.get("automod_protection", True)),
        ("Anti-Emoji Delete", cfg.get("emoji_protection", True)),
        ("Anti-Sticker Delete", cfg.get("sticker_protection", True)),
        ("Anti-Integration", cfg.get("integration_protection", True)),
    ]

    # Straight vertical lines with > blockquote, switch on/off emoji first, then module name
    mod_lines = ["**Protection Overview**", ""]
    for name, state in modules:
        is_active = state and is_enabled
        switch = sw_on if is_active else sw_off
        mod_lines.append(f"> {switch} **{name}**")

    container.add_text("\n".join(mod_lines))
    container.add_separator(divider=True)

    # Configuration & status cleanly positioned at the bottom with > blockquotes
    status_switch = sw_on if is_enabled else sw_off
    punish_tag = f"`{punishment}`"
    log_tag = log_ch.mention if log_ch else "`None`"

    bottom_lines = [
        f"> **Status:** {status_switch} **—** **Punishment:** {punish_tag}",
        f"> **Log Channel:** {log_tag}",
        f"> **Extra Owners:** `{eo_count}`",
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

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "`[ON]`")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Activated**")
        container.add_separator(divider=True)
        container.add_text(f"{dot} **Status:** {sw_on} **—** **Punishment:** `Ban`")
        await send_container_response(ctx, container)

    @antinuke.command(name="disable", description="Disable the Antinuke defense protocol.")
    async def antinuke_disable(self, ctx: CustomContext) -> None:
        """Turn off Antinuke protection."""
        await self.bot.antinuke_mgr.update_settings(ctx.guild.id, enabled=False)

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "`[OFF]`")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Deactivated**")
        container.add_separator(divider=True)
        container.add_text(f"{dot} **Status:** {sw_off}\n> *Use `,antinuke enable` to re-arm protection.*")
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
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Punishment Updated**")
        container.add_separator(divider=True)
        container.add_text(f"{dot} **New Action:** `{clean_action.capitalize()}`")
        await send_container_response(ctx, container)

    @antinuke.command(name="log", description="Bind a channel for antinuke incident alerts.")
    @app_commands.describe(channel="Target channel for security logs")
    async def antinuke_log(self, ctx: CustomContext, channel: discord.TextChannel) -> None:
        """Set antinuke incident logging channel."""
        await self.bot.antinuke_mgr.update_settings(ctx.guild.id, log_channel_id=channel.id)

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Log Channel Configured**")
        container.add_separator(divider=True)
        container.add_text(f"{dot} **Target Channel:** {channel.mention}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load AntinukePanelCog."""
    await bot.add_cog(AntinukePanelCog(bot))
