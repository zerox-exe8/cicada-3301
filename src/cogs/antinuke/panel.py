from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response
from src.cogs.antinuke._views import AntinukeControlView

if TYPE_CHECKING:
    from src.core.bot import KyroBot


def build_antinuke_card(bot: KyroBot, guild: discord.Guild, author_id: int) -> tuple[KyroContainer, AntinukeControlView]:
    """Assemble the clean Components V2 Dashboard Card for Antinuke."""
    cfg = bot.antinuke_mgr.get_settings(guild.id)
    is_enabled = cfg.get("enabled", False)
    punishment = cfg.get("punishment", "ban").capitalize()
    log_ch = bot.antinuke_mgr.get_log_channel(guild)

    e_reg = bot.custom_emojis
    dot = e_reg.get("heart_dot", "-")
    shield = e_reg.get("icon_shield", "")
    badge_str = f"{shield} " if shield else ""

    container = KyroContainer(accent_color=None)
    status_badge = "🟢 `Active`" if is_enabled else "🔴 `Disabled`"
    container.add_section(
        content=(
            f"**{badge_str}Kyro Antinuke Protocol — Dashboard**\n"
            f"> System Status: {status_badge} • Punishment: `{punishment}`"
        )
    )
    container.add_separator(divider=True)

    # Sub-modules checklist
    modules = [
        ("Vanity URL Protection", cfg.get("vanity_protection", True)),
        ("@everyone Escalation Disarm", cfg.get("everyone_protection", True)),
        ("Role Protection (Nuke/Tamper)", cfg.get("role_protection", True)),
        ("Channel Protection (Nuke/Tamper)", cfg.get("channel_protection", True)),
        ("Anti-Bot (Unauthorized Adds)", cfg.get("bot_protection", True)),
        ("Anti-Webhook (Instant Killer)", cfg.get("webhook_protection", True)),
        ("Anti-Ban & Anti-Kick Protection", cfg.get("ban_protection", True)),
        ("Anti-AutoMod Rule Hijack", cfg.get("automod_protection", True)),
    ]

    mod_lines = []
    for name, state in modules:
        icon = "✅" if (state and is_enabled) else ("⚪" if state else "❌")
        mod_lines.append(f"{icon} **{name}**")

    container.add_text(
        f"{dot} **Security Alert Log:** {log_ch.mention if log_ch else '`None (Fallback to ModLog)`'}\n"
        f"{dot} **Extra Owners:** `{len(bot.antinuke_mgr.get_extra_owners(guild.id))}` registered\n\n"
        + "\n".join(mod_lines)
    )

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
        from src.utils.containers import send_container_response
        await send_container_response(ctx, container, view=view)

    @antinuke.command(name="enable", description="Enable the Antinuke defense protocol.")
    async def antinuke_enable(self, ctx: CustomContext) -> None:
        """Turn on Antinuke protection."""
        await self.bot.antinuke_mgr.update_settings(ctx.guild.id, enabled=True)
        # Snapshot state immediately upon activation
        self.bot.antinuke_mgr.snapshot_guild_state(ctx.guild)

        dot = self.bot.custom_emojis.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Kyro Antinuke Activated**\n"
                "> The server is now actively protected against malicious nukes, rogue admins, and webhook attacks."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"{dot} **Status:** 🟢 `Active`\n{dot} **Default Punishment:** `Ban`")
        await send_container_response(ctx, container)

    @antinuke.command(name="disable", description="Disable the Antinuke defense protocol.")
    async def antinuke_disable(self, ctx: CustomContext) -> None:
        """Turn off Antinuke protection."""
        await self.bot.antinuke_mgr.update_settings(ctx.guild.id, enabled=False)

        dot = self.bot.custom_emojis.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Kyro Antinuke Deactivated**\n"
                "> Real-time antinuke triggers, instant rollback, and unauthorized action traps are now offline."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"{dot} **Status:** 🔴 `Disabled`\n{dot} Use `?antinuke enable` to re-arm protection.")
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
        dot = self.bot.custom_emojis.get("heart_dot", "-")
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

        dot = self.bot.custom_emojis.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Log Channel Configured**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target Channel:** {channel.mention}\n"
            f"{dot} All security intercepts and self-healing actions will be recorded here."
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load AntinukePanelCog."""
    await bot.add_cog(AntinukePanelCog(bot))
