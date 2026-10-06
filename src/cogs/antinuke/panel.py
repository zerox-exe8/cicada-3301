from __future__ import annotations

from typing import TYPE_CHECKING
import logging
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response
from src.cogs.antinuke._views import AntinukeControlView

if TYPE_CHECKING:
    from src.core.bot import KyroBot


logger = logging.getLogger("Kyro.Antinuke.Panel")


async def ensure_unified_log_channel(
    bot: KyroBot,
    guild: discord.Guild,
    invoker: discord.Member | discord.User | None = None,
) -> tuple[discord.TextChannel | None, bool]:
    """
    Find or auto-create a strictly private unified `kyro_logs` channel.
    Secures permissions against public access (@everyone denied view_channel).
    Binds the channel to both antinuke and unified server audit logs.
    Returns (channel, is_newly_created).
    """
    log_channel: discord.TextChannel | None = None
    for ch in guild.text_channels:
        if ch.name.lower() in ("kyro_logs", "kyro-logs"):
            log_channel = ch
            break

    is_new = False
    if log_channel is None:
        try:
            # Strictly private: hide from @everyone, allow bot and extra owners
            overwrites: dict[Any, discord.PermissionOverwrite] = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False,
                    read_messages=False,
                    send_messages=False,
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    read_message_history=True,
                    manage_messages=True,
                ),
            }
            extra_owner_ids = bot.antinuke_mgr.get_extra_owners(guild.id)
            for eo_id in extra_owner_ids:
                eo_m = guild.get_member(eo_id)
                if eo_m:
                    overwrites[eo_m] = discord.PermissionOverwrite(
                        view_channel=True,
                        read_messages=True,
                        read_message_history=True,
                    )

            log_channel = await guild.create_text_channel(
                "kyro_logs",
                overwrites=overwrites,
                topic="Kyro unified logs — security alerts + message / member / server / voice audit.",
                reason="Kyro Antinuke: auto-create unified log channel (secured private)",
            )
            is_new = True
        except (discord.Forbidden, Exception) as e:
            logger.warning(f"Could not auto-create kyro_logs in guild {guild.id}: {e}")
            log_channel = None
    else:
        # Secure existing channel so it is NOT public to regular members
        try:
            default_perms = log_channel.permissions_for(guild.default_role)
            if default_perms.view_channel:
                await log_channel.set_permissions(
                    guild.default_role,
                    view_channel=False,
                    read_messages=False,
                    send_messages=False,
                    reason="Kyro Antinuke: secure log channel from public access",
                )
            bot_perms = log_channel.permissions_for(guild.me)
            if not (bot_perms.view_channel and bot_perms.send_messages and bot_perms.embed_links):
                await log_channel.set_permissions(
                    guild.me,
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    embed_links=True,
                    attach_files=True,
                    read_message_history=True,
                    reason="Kyro Antinuke: grant bot required permissions in log channel",
                )
        except (discord.Forbidden, Exception) as e:
            logger.warning(f"Could not secure permissions for existing log channel {log_channel.id}: {e}")

    if log_channel is not None:
        await bot.antinuke_mgr.update_settings(
            guild.id, enabled=True, log_channel_id=log_channel.id
        )
        try:
            await bot.log_mgr.set_log_channel(guild.id, "all", log_channel.id)
        except Exception:
            pass

        # Post initialization card into the new logs channel
        if is_new:
            try:
                dot = bot.custom_emojis.get("heart_dot", "•")
                init_card = KyroContainer(accent_color=None)
                init_card.add_section(
                    content="**Kyro Logs**\n> This channel is used by Kyro to record server activity and antinuke alerts."
                )
                init_card.add_separator(divider=True)
                init_card.add_text(
                    f"> {dot} **Access:** Private (hidden from @everyone)\n"
                    f"> {dot} **Logs:** Antinuke, Member, Message, Server, Voice"
                )
                init_card.add_separator(divider=True)
                invoker_str = f"Created by {invoker.mention} • " if invoker else ""
                init_card.add_text(f"-# {invoker_str}<t:{int(discord.utils.utcnow().timestamp())}:f>")
                await send_container_response(log_channel, init_card)
            except Exception as e:
                logger.warning(f"Could not send initialization card to log channel: {e}")

    return log_channel, is_new


def build_antinuke_card(bot: KyroBot, guild: discord.Guild, author_id: int) -> tuple[KyroContainer, AntinukeControlView]:
    """Assemble the clean, straight-line Antinuke dashboard container with heart dot and switch emojis."""
    cfg = bot.antinuke_mgr.get_settings(guild.id)
    is_enabled = cfg.get("enabled", False)
    raw_punishment = cfg.get("punishment", "ban")
    punishment = {"ban": "Ban", "kick": "Kick", "strip_roles": "Quarantine"}.get(raw_punishment, str(raw_punishment).capitalize())
    log_ch = bot.antinuke_mgr.get_log_channel(guild)
    if not log_ch:
        try:
            log_ch = bot.log_mgr.get_log_channel(guild, "all")
        except Exception:
            pass
    eo_count = len(bot.antinuke_mgr.get_extra_owners(guild.id))

    dot = bot.custom_emojis.get("heart_dot", "•")
    sw_on = bot.custom_emojis.get("icon_switch_on", "`[ON]`")
    sw_off = bot.custom_emojis.get("icon_switch_off", "`[OFF]`")

    container = KyroContainer(accent_color=None)
    tagline = (
        "> *Real-time protection against nukes, raids, and unauthorized changes.*"
        if is_enabled
        else "> *Protection is currently inactive. Use `,antinuke enable` to arm.*"
    )
    container.add_section(
        content=(
            "**Kyro Antinuke**\n"
            f"{tagline}"
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
    container.add_separator(divider=True)

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
        description="Open the Antinuke setup for your server.",
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def antinuke(self, ctx: CustomContext) -> None:
        """Launch the Antinuke setup, or show a notice if already enabled."""
        cfg = self.bot.antinuke_mgr.get_settings(ctx.guild.id)
        if cfg.get("enabled", False):
            # Already enabled — show a small clean notice
            dot = self.bot.custom_emojis.get("heart_dot", "•")
            sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
            c = KyroContainer(accent_color=None)
            c.add_section(content="**Kyro Antinuke**\n> Antinuke is already active on this server.")
            c.add_separator(divider=True)
            c.add_text(f"> {dot} **Status:** {sw_on}")
            c.add_separator(divider=True)
            c.add_text(f"-# Use `,antinuke disable` to turn it off.")
            await send_container_response(ctx, c)
            return

        from src.cogs.antinuke._setup_view import AntinukeSetupWizard
        wizard = AntinukeSetupWizard(self.bot, ctx.guild, ctx.author)
        container = wizard.get_dashboard_container()
        await send_container_response(ctx, container, view=wizard)

    @antinuke.command(name="enable", description="Enable Antinuke protection on your server.")
    async def antinuke_enable(self, ctx: CustomContext) -> None:
        """Turn on Antinuke protection + auto-create private kyro_logs channel."""
        guild = ctx.guild
        cfg = self.bot.antinuke_mgr.get_settings(guild.id)

        # If already enabled, show a small notice — don't re-run setup
        if cfg.get("enabled", False):
            dot = self.bot.custom_emojis.get("heart_dot", "•")
            sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
            c = KyroContainer(accent_color=None)
            c.add_section(content="**Kyro Antinuke**\n> Antinuke is already active on this server.")
            c.add_separator(divider=True)
            c.add_text(f"> {dot} **Status:** {sw_on}")
            c.add_separator(divider=True)
            c.add_text("-# Use `,antinuke disable` to turn it off.")
            await send_container_response(ctx, c)
            return

        # Enable antinuke and auto-create logs channel
        log_channel, _ = await ensure_unified_log_channel(self.bot, guild, ctx.author)
        if log_channel is None:
            await self.bot.antinuke_mgr.update_settings(guild.id, enabled=True)
        self.bot.antinuke_mgr.snapshot_guild_state(guild)

        # Show clean success embed — no control panel buttons
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content="**Kyro Antinuke**\n> Antinuke is now active and protecting your server."
        )
        container.add_separator(divider=True)
        container.add_text(f"> {dot} **Status:** {sw_on}")
        container.add_separator(divider=True)
        container.add_text(f"-# Enabled by {ctx.author.display_name} • <t:{int(discord.utils.utcnow().timestamp())}:f>")
        await send_container_response(ctx, container)

    @antinuke.command(name="disable", description="Disable Antinuke protection on your server.")
    async def antinuke_disable(self, ctx: CustomContext) -> None:
        """Turn off Antinuke protection and auto-delete the kyro_logs channel."""
        guild = ctx.guild
        await self.bot.antinuke_mgr.update_settings(guild.id, enabled=False)

        # Auto-delete the kyro_logs channel that was created during enable
        log_channel = self.bot.antinuke_mgr.get_log_channel(guild)
        if log_channel is not None:
            try:
                await log_channel.delete(reason="Kyro Antinuke disabled — auto-removing kyro_logs channel")
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.warning(f"Could not delete kyro_logs in guild {guild.id}: {e}")

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "[OFF]")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Kyro Antinuke**\n"
                "> Antinuke has been turned off."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"> {dot} **Status:** {sw_off}")
        container.add_separator(divider=True)
        container.add_text(f"-# Disabled by {ctx.author.display_name} • <t:{int(discord.utils.utcnow().timestamp())}:f>")
        await send_container_response(ctx, container)

    @antinuke.command(name="punishment", description="Set the punishment for unauthorized actions.")
    @app_commands.describe(action="Punishment to execute on attackers")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="ban", value="ban"),
            app_commands.Choice(name="kick", value="kick"),
            app_commands.Choice(name="quarantine", value="strip_roles"),
        ]
    )
    async def antinuke_punishment(self, ctx: CustomContext, action: str) -> None:
        """Configure antinuke action upon breach."""
        clean_action = action.lower()
        # Alias: allow `quarantine` as user-friendly name for strip_roles
        if clean_action in ("quarantine", "quarantine_only", "quarantaine"):
            clean_action = "strip_roles"
        if clean_action not in ["ban", "kick", "strip_roles"]:
            await ctx.send_error("Invalid punishment. Choose from: `ban`, `kick`, `quarantine`.")
            return

        await self.bot.antinuke_mgr.update_settings(ctx.guild.id, punishment=clean_action)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        display_name = {"ban": "Ban", "kick": "Kick", "strip_roles": "Quarantine"}.get(clean_action, clean_action.capitalize())
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Punishment Updated**")
        container.add_separator(divider=True)
        container.add_text(f"{dot} **New Action:** `{display_name}`")
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
