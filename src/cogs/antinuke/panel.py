from __future__ import annotations

import datetime
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
    is_locked = bot.antinuke_mgr.is_locked_down(guild.id)
    lockdown_tag = "`Active (Restricted)`" if is_locked else "`Normal`"

    bottom_lines = [
        f"> **Status:** {status_switch} **—** **Punishment:** {punish_tag}",
        f"> **Log Channel:** {log_tag}",
        f"> **Lockdown Mode:** {lockdown_tag} **—** **Extra Owners:** `{eo_count}`",
    ]
    container.add_text("\n".join(bottom_lines))
    container.add_separator(divider=True)

    view = AntinukeControlView(bot, guild, author_id)
    return container, view


def build_antinuke_status_card(
    bot: KyroBot,
    guild: discord.Guild,
    author: discord.Member | discord.User | None = None,
) -> KyroContainer:
    """Build a comprehensive, clean status summary card showing Status, Modules, Punishment, Lockdown, and Logs."""
    cfg = bot.antinuke_mgr.get_settings(guild.id)
    is_enabled = cfg.get("enabled", False)
    dot = bot.custom_emojis.get("heart_dot", "•")
    sw_on = bot.custom_emojis.get("icon_switch_on", "[ON]")
    sw_off = bot.custom_emojis.get("icon_switch_off", "[OFF]")
    status_sw = sw_on if is_enabled else sw_off

    raw_punish = cfg.get("punishment", "strip_roles")
    punish_map = {"ban": "Ban", "kick": "Kick", "strip_roles": "Quarantine"}
    punish_str = punish_map.get(raw_punish, "Quarantine")

    log_ch = bot.antinuke_mgr.get_log_channel(guild)
    if not log_ch:
        try:
            log_ch = bot.log_mgr.get_log_channel(guild, "all")
        except Exception:
            pass
    log_str = log_ch.mention if log_ch else "`None`"

    is_locked = bot.antinuke_mgr.is_locked_down(guild.id)
    lockdown_tag = "`Active (Restricted)`" if is_locked else "`Normal`"

    all_keys = [
        "ban", "kick", "bot", "prune", "channel_create", "channel_delete", "channel_update",
        "role_create", "role_delete", "role_update", "everyone", "member_role", "vanity",
        "webhook_create", "webhook_delete", "guild_update", "automod", "emoji", "sticker", "integration"
    ]
    if is_enabled:
        active_count = sum(1 for k in all_keys if bot.antinuke_mgr.is_module_enabled(guild.id, k))
        total_count = len(all_keys)
        if active_count == total_count:
            mod_str = f"`All Modules Active ({active_count}/{total_count})`"
        elif active_count == 0:
            mod_str = "`No Modules Active`"
        else:
            mod_str = f"`{active_count}/{total_count} Modules Active`"
    else:
        mod_str = "`Disabled`"

    c = KyroContainer(accent_color=None)
    title_sub = (
        "> Antinuke is already active on this server."
        if is_enabled
        else "> Antinuke is currently disabled on this server."
    )
    c.add_section(content=f"**Kyro Antinuke**\n{title_sub}")
    c.add_separator(divider=True)
    c.add_text(
        f"> {dot} **Status:** {status_sw}\n"
        f"> {dot} **Protection Modules:** {mod_str}\n"
        f"> {dot} **Punishment:** `{punish_str}`\n"
        f"> {dot} **Lockdown:** {lockdown_tag}\n"
        f"> {dot} **Logs:** {log_str}"
    )
    c.add_separator(divider=True)
    footer = (
        "-# Use `,antinuke disable` to turn it off or `,antinuke setup` to reconfigure."
        if is_enabled
        else "-# Use `,antinuke enable` or `,antinuke setup` to turn it on."
    )
    c.add_text(footer)
    return c


def build_lockdown_card(
    bot: KyroBot,
    guild: discord.Guild,
    author: discord.Member | discord.User,
    affected_channels: int,
) -> KyroContainer:
    """Build antinuke-styled server lockdown status card."""
    dot = bot.custom_emojis.get("heart_dot", "•")
    sw_on = bot.custom_emojis.get("icon_switch_on", "[ON]")

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            "**Kyro Lockdown**\n"
            "> *All public channels have been locked down.*"
        )
    )
    container.add_separator(divider=True)
    container.add_text(
        f"> {dot} **Status:** {sw_on}\n"
        f"> {dot} **Locked Channels:** `{affected_channels} Channels`\n"
        f"> {dot} **Chat & Messages:** `Closed`\n"
        f"> {dot} **Voice Speaking:** `Muted`\n"
        f"> {dot} **Raid Protection:** `Active`"
    )
    container.add_separator(divider=True)
    container.add_text(
        f"> **How to open:** Use `,lockdown off` to open all channels back."
    )
    container.add_separator(divider=True)
    container.add_text(f"-# Executed by {author.display_name} • Kyro Server Lockdown • <t:{int(discord.utils.utcnow().timestamp())}:f>")
    return container


def build_lockdown_lift_card(
    bot: KyroBot,
    guild: discord.Guild,
    author: discord.Member | discord.User,
    restored_channels: int,
) -> KyroContainer:
    """Build antinuke-styled server lockdown lift card."""
    dot = bot.custom_emojis.get("heart_dot", "•")
    sw_off = bot.custom_emojis.get("icon_switch_off", "[OFF]")

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            "**Kyro Lockdown**\n"
            "> *Lockdown has been lifted. Server is open now.*"
        )
    )
    container.add_separator(divider=True)
    container.add_text(
        f"> {dot} **Status:** {sw_off}\n"
        f"> {dot} **Unlocked Channels:** `{restored_channels} Channels`\n"
        f"> {dot} **Chat & Messages:** `Open`\n"
        f"> {dot} **Voice Speaking:** `Open`\n"
        f"> {dot} **Raid Protection:** `Standby`"
    )
    container.add_separator(divider=True)
    container.add_text(
        f"> **Notice:** All channels are back to normal."
    )
    container.add_separator(divider=True)
    container.add_text(f"-# Lifted by {author.display_name} • Kyro Server Lockdown • <t:{int(discord.utils.utcnow().timestamp())}:f>")
    return container


class AntinukePanelCog(commands.Cog):
    """Core Antinuke configuration and master control panel."""
    category: str = "Security"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    async def cog_check(self, ctx: CustomContext) -> bool:
        """Only Guild Owner, registered Extra Owners, or Administrators (for lockdown) can run Antinuke commands."""
        if not ctx.guild:
            return False
        if ctx.author.id == ctx.guild.owner_id:
            return True
        if self.bot.antinuke_mgr.is_extra_owner(ctx.guild.id, ctx.author.id):
            return True
        cmd_name = ctx.command.name if ctx.command else ""
        if cmd_name in ("lockdown", "standalone_lockdown") and ctx.author.guild_permissions.administrator:
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
        """Launch the Antinuke setup, or show current configuration if already enabled."""
        cfg = self.bot.antinuke_mgr.get_settings(ctx.guild.id)
        if cfg.get("enabled", False):
            # Already enabled — show clean notice with Status, Modules, Punishment, and Logs
            c = build_antinuke_status_card(self.bot, ctx.guild, ctx.author)
            await send_container_response(ctx, c)
            return

        from src.cogs.antinuke._setup_view import AntinukeSetupWizard
        wizard = AntinukeSetupWizard(self.bot, ctx.guild, ctx.author)
        container = wizard.get_dashboard_container()
        await send_container_response(ctx, container, view=wizard)

    @antinuke.command(name="show", aliases=["config", "settings", "status", "info"], description="Show current Antinuke configuration, modules, punishment, and logs.")
    async def antinuke_show(self, ctx: CustomContext) -> None:
        """Display the complete antinuke status, modules, punishment and log channel."""
        c = build_antinuke_status_card(self.bot, ctx.guild, ctx.author)
        await send_container_response(ctx, c)

    @antinuke.command(name="setup", description="Launch the step-by-step Antinuke setup wizard.")
    async def antinuke_setup(self, ctx: CustomContext) -> None:
        """Launch the Antinuke setup wizard explicitly."""
        from src.cogs.antinuke._setup_view import AntinukeSetupWizard
        wizard = AntinukeSetupWizard(self.bot, ctx.guild, ctx.author)
        container = wizard.get_dashboard_container()
        await send_container_response(ctx, container, view=wizard)

    @antinuke.command(name="enable", description="Enable Antinuke protection on your server.")
    async def antinuke_enable(self, ctx: CustomContext) -> None:
        """Turn on Antinuke protection + auto-create private kyro_logs channel."""
        guild = ctx.guild
        cfg = self.bot.antinuke_mgr.get_settings(guild.id)

        # If already enabled, show the comprehensive status card — don't re-run setup
        if cfg.get("enabled", False):
            c = build_antinuke_status_card(self.bot, guild, ctx.author)
            await send_container_response(ctx, c)
            return

        # Enable antinuke, set punishment to quarantine and auto-create logs channel
        log_channel, _ = await ensure_unified_log_channel(self.bot, guild, ctx.author)
        await self.bot.antinuke_mgr.update_settings(
            guild.id,
            enabled=True,
            punishment="strip_roles",
            log_channel_id=log_channel.id if log_channel else None,
        )
        self.bot.antinuke_mgr.snapshot_guild_state(guild)

        # Show clean success embed — with status, protection modules, quarantine punishment and logs channel
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
        log_str = log_channel.mention if log_channel else "`None`"

        all_keys = [
            "ban", "kick", "bot", "prune", "channel_create", "channel_delete", "channel_update",
            "role_create", "role_delete", "role_update", "everyone", "member_role", "vanity",
            "webhook_create", "webhook_delete", "guild_update", "automod", "emoji", "sticker", "integration"
        ]
        active_count = sum(1 for k in all_keys if self.bot.antinuke_mgr.is_module_enabled(guild.id, k))
        total_count = len(all_keys)
        mod_disp = f"`All Modules Active ({active_count}/{total_count})`" if active_count == total_count else f"`{active_count}/{total_count} Modules Active`"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content="**Kyro Antinuke**\n> Antinuke is now active and protecting your server."
        )
        container.add_separator(divider=True)
        container.add_text(
            f"> {dot} **Status:** {sw_on}\n"
            f"> {dot} **Protection Modules:** {mod_disp}\n"
            f"> {dot} **Punishment:** `Quarantine`\n"
            f"> {dot} **Logs:** {log_str}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Enabled by {ctx.author.display_name} • <t:{int(discord.utils.utcnow().timestamp())}:f>")
        await send_container_response(ctx, container)

    @antinuke.command(name="disable", description="Disable Antinuke protection on your server.")
    async def antinuke_disable(self, ctx: CustomContext) -> None:
        """Turn off Antinuke protection and auto-delete the kyro_logs channel."""
        guild = ctx.guild
        await self.bot.antinuke_mgr.update_settings(guild.id, enabled=False)

        # Auto-delete the kyro_logs channel only if it is the dedicated kyro_logs channel
        log_channel = self.bot.antinuke_mgr.get_log_channel(guild)
        if log_channel is not None and log_channel.name.lower() in ("kyro_logs", "kyro-logs"):
            try:
                await log_channel.delete(reason="Kyro Antinuke disabled — auto-removing kyro_logs channel")
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.warning(f"Could not delete kyro_logs in guild {guild.id}: {e}")

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "[OFF]")
        raw_punish = self.bot.antinuke_mgr.get_settings(guild.id).get("punishment", "strip_roles")
        punish_map = {"ban": "Ban", "kick": "Kick", "strip_roles": "Quarantine"}
        punish_str = punish_map.get(raw_punish, "Quarantine")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Kyro Antinuke**\n"
                "> Antinuke has been turned off."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"> {dot} **Status:** {sw_off}\n"
            f"> {dot} **Protection Modules:** `Disabled`\n"
            f"> {dot} **Punishment:** `{punish_str}`\n"
            f"> {dot} **Logs:** `None`"
        )
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

    # ------------------ SERVER LOCKDOWN COMMAND ------------------

    @antinuke.command(name="lockdown", description="Freeze or unfreeze public messaging across all channels.")
    @app_commands.describe(action="'on' to freeze, 'off' to restore permissions")
    async def antinuke_lockdown(self, ctx: CustomContext, action: str = "") -> None:
        """Lockdown sub-command under antinuke."""
        await self._handle_lockdown(ctx, action)

    @commands.command(name="lockdown", description="Freeze or unfreeze public messaging across all channels.")
    async def standalone_lockdown(self, ctx: CustomContext, action: str = "") -> None:
        """
        Server lockdown command.
        Usage:
          ,lockdown on   -> Locks all channels
          ,lockdown off  -> Unlocks all channels
          ,lockdown      -> Toggles lockdown on / off
        """
        await self._handle_lockdown(ctx, action)

    async def _handle_lockdown(self, ctx: CustomContext, action: str = "") -> None:
        guild = ctx.guild
        clean = action.strip().lower()

        # Unlock branch
        if clean in ("off", "lift", "disable", "stop", "unlock", "end"):
            if not self.bot.antinuke_mgr.is_locked_down(guild.id):
                await ctx.send_warning("This server is **not currently in lockdown**.")
                return
            restored = await self.bot.antinuke_mgr.emergency_unlock(
                guild, reason=f"Lockdown lifted by {ctx.author}"
            )
            card = build_lockdown_lift_card(self.bot, guild, ctx.author, restored)
            await send_container_response(ctx, card)
            return

        # Lock branch
        if clean in ("on", "enable", "start", "freeze"):
            if self.bot.antinuke_mgr.is_locked_down(guild.id):
                await ctx.send_warning("This server is **already in lockdown**. Use `,lockdown off` to restore.")
                return
            affected = await self.bot.antinuke_mgr.emergency_lockdown(
                guild, reason=f"Lockdown ordered by {ctx.author}"
            )
            card = build_lockdown_card(self.bot, guild, ctx.author, affected)
            await send_container_response(ctx, card)
            return

        # Smart toggle if no explicit argument was passed
        if self.bot.antinuke_mgr.is_locked_down(guild.id):
            restored = await self.bot.antinuke_mgr.emergency_unlock(
                guild, reason=f"Lockdown lifted by {ctx.author}"
            )
            card = build_lockdown_lift_card(self.bot, guild, ctx.author, restored)
            await send_container_response(ctx, card)
        else:
            affected = await self.bot.antinuke_mgr.emergency_lockdown(
                guild, reason=f"Lockdown ordered by {ctx.author}"
            )
            card = build_lockdown_card(self.bot, guild, ctx.author, affected)
            await send_container_response(ctx, card)


async def setup(bot: KyroBot) -> None:
    """Load AntinukePanelCog."""
    await bot.add_cog(AntinukePanelCog(bot))
