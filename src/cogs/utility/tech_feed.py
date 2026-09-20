"""
Kyro Discord Bot - Tech Intelligence Autonomous Feed Cog
Background ingestion and dispatch engine delivering zero-noise engineering, AI, security, and hardware intel.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional, Any

from datetime import datetime, timezone, timedelta
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.core.context import CustomContext
from src.managers.tech_manager import CATEGORY_BADGES, TechStory, validate_url_live
from src.utils.containers import (
    KyroContainer,
    edit_container_response,
    send_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Utility.TechFeed")

IST = timezone(timedelta(hours=5, minutes=30))

VALID_CATEGORIES: set[str] = {"all", "github", "ai", "security", "systems", "hardware", "tech"}

CADENCE_OPTIONS: list[dict[str, str]] = [
    {
        "label": "Every 15 Minutes",
        "value": "15m",
        "description": "Continuous real-time stream as tech stories break",
    },
    {
        "label": "Hourly Batch (Default)",
        "value": "hourly",
        "description": "10 curated top stories delivered hourly with 1m pacing",
    },
    {
        "label": "Morning 9:00 AM IST",
        "value": "09:00",
        "description": "Daily morning intelligence briefing drop at 9:00 AM IST",
    },
    {
        "label": "Midnight 12:00 AM IST",
        "value": "00:00",
        "description": "Daily midnight intelligence recap drop at 12:00 AM IST",
    },
    {
        "label": "Custom Time (IST)",
        "value": "custom",
        "description": "Specify custom 24-hour daily delivery time (HH:MM IST)",
    },
]


def format_cadence_label(cadence: str) -> str:
    c = str(cadence or "hourly").lower().strip()
    if c == "15m":
        return "Every 15 Minutes"
    if c == "hourly":
        return "Hourly Batch (1h)"
    if c == "09:00":
        return "Morning 9:00 AM IST"
    if c == "00:00":
        return "Midnight 12:00 AM IST"
    if c.startswith("custom:") or ":" in c:
        raw_time = c.replace("custom:", "").strip()
        return f"Daily at {raw_time} IST"
    return "Hourly Batch (1h)"


def parse_ist_timestamp(ts: Any) -> Optional[datetime]:
    """Parse and normalize any database timestamp to Indian Standard Time (IST)."""
    if not ts:
        return None
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except Exception:
            return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc).astimezone(IST)
        return ts.astimezone(IST)
    return None


def is_cadence_eligible(cfg: dict[str, Any], now_ist: datetime) -> bool:
    cadence = str(cfg.get("cadence") or "hourly").lower().strip()
    last_dispatch = parse_ist_timestamp(cfg.get("last_dispatch_ts"))
    today_str = now_ist.strftime("%Y-%m-%d")

    # 1. Real-time every 15 minutes
    if cadence == "15m":
        if last_dispatch is None:
            return True
        return (now_ist - last_dispatch).total_seconds() >= 800

    # 2. Morning 9:00 AM IST
    if cadence == "09:00":
        if now_ist.hour == 9 and 0 <= now_ist.minute < 30:
            if last_dispatch is None:
                return True
            return last_dispatch.strftime("%Y-%m-%d") != today_str
        return False

    # 3. Midnight 12:00 AM IST
    if cadence == "00:00":
        if now_ist.hour == 0 and 0 <= now_ist.minute < 30:
            if last_dispatch is None:
                return True
            return last_dispatch.strftime("%Y-%m-%d") != today_str
        return False

    # 4. Custom 24h Time: "custom:HH:MM" or "HH:MM" (evaluated strictly in IST)
    if cadence.startswith("custom:") or ":" in cadence:
        raw_time = cadence.replace("custom:", "").strip()
        try:
            parts = raw_time.split(":")
            h, m = int(parts[0]), int(parts[1])
            target_mins = h * 60 + m
            curr_mins = now_ist.hour * 60 + now_ist.minute
            diff = curr_mins - target_mins
            if 0 <= diff < 30:
                if last_dispatch is None:
                    return True
                return last_dispatch.strftime("%Y-%m-%d") != today_str
            return False
        except Exception:
            return False

    # 5. Default fallback: Hourly batch
    if last_dispatch is None:
        return True
    return (now_ist - last_dispatch).total_seconds() >= 3500


async def build_tech_dashboard(bot: KyroBot, guild: discord.Guild, cfg: dict[str, Any]) -> KyroContainer:
    channel = guild.get_channel(cfg["channel_id"])
    ch_mention = channel.mention if channel else f"Unknown ({cfg['channel_id']})"
    raw_cats = {c.strip() for c in cfg.get("categories", "all").split(",")}

    sw_on = bot.custom_emojis.get("icon_switch_on", "[ON]")
    sw_off = bot.custom_emojis.get("icon_switch_off", "[OFF]")
    dot = bot.custom_emojis.get("heart_dot", "•")

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"### Tech Dashboard\n"
            f"> Status: Active & Broadcasting"
        )
    )
    container.add_separator(divider=True)

    health = await bot.tech_realtime_mgr.get_global_health_summary()
    health_summary_parts = [f"{prov} `{stat}`" for prov, stat in health.items()]
    health_line = f"**Cloud Health:** " + f"  {dot}  ".join(health_summary_parts)

    cadence_raw = cfg.get("cadence", "hourly")
    cadence_label = format_cadence_label(cadence_raw)

    top_lines = [
        f"**Channel:** {ch_mention}  {dot}  **Cadence:** `{cadence_label} (10 Items • 1m Delay)`  {dot}  **Status:** `Active`",
        health_line,
    ]
    container.add_text("\n".join(top_lines))
    container.add_separator(divider=True)

    module_lines = ["**Active Modules:**"]
    for opt in MODULE_OPTIONS:
        val = opt["value"]
        lbl = opt["label"]
        is_active = ("all" in raw_cats) or (val in raw_cats)
        emoji = sw_on if is_active else sw_off
        module_lines.append(f"{emoji} **{lbl}**")

    container.add_text("\n".join(module_lines))
    container.add_separator(divider=True)
    return container

MODULE_OPTIONS: list[dict[str, str]] = [
    {
        "label": "GitHub",
        "value": "github",
        "description": "Trending repositories, open source tools & developer libraries",
    },
    {
        "label": "AI Research",
        "value": "ai",
        "description": "Frontier models, research papers, LLMs & breakthrough tools",
    },
    {
        "label": "Security Intel",
        "value": "security",
        "description": "Exploit disclosures, CVE reports & cyber defence intel",
    },
    {
        "label": "Consumer Tech",
        "value": "tech",
        "description": "Product announcements, hardware culture & industry shifts",
    },
    {
        "label": "Systems Intel",
        "value": "systems",
        "description": "Distributed architecture, databases, Linux kernel & backend",
    },
    {
        "label": "Hardware & Silicon",
        "value": "hardware",
        "description": "Semiconductors, CPUs, GPUs, architectures & chip roadmaps",
    },
]


class TechSetupChannelView(discord.ui.View):
    """Step 1: Select text channel for tech intelligence broadcasts."""

    def __init__(self, bot: KyroBot, author_id: int, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id
        self.selected_channel: discord.TextChannel | None = None

        self.channel_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            placeholder="Select news broadcast channel...",
            min_values=1,
            max_values=1,
            row=0,
        )
        self.channel_select.callback = self._on_channel_select
        self.add_item(self.channel_select)

        # Cancel on the left, Continue on the right (both secondary grey style, zero blue color)
        self.cancel_button = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.cancel_button.callback = self._on_cancel
        self.add_item(self.cancel_button)

        self.continue_button = discord.ui.Button(
            label="Continue",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.continue_button.callback = self._on_continue
        self.add_item(self.continue_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not (
            interaction.user.guild_permissions.manage_guild
            if isinstance(interaction.user, discord.Member)
            else False
        ):
            await interaction.response.send_message(
                "Only the command author or server administrators can interact with this setup.",
                ephemeral=True,
            )
            return False
        return True

    async def _on_channel_select(self, interaction: discord.Interaction) -> None:
        if not self.channel_select.values:
            return
        selected = self.channel_select.values[0]
        if isinstance(selected, discord.TextChannel):
            self.selected_channel = selected
        elif hasattr(selected, "id") and interaction.guild:
            self.selected_channel = interaction.guild.get_channel(selected.id)
        await interaction.response.defer()

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Tech Dashboard\n"
                f"> Setup cancelled."
            )
        )
        await edit_container_response(interaction, container, view=None)

    async def _on_continue(self, interaction: discord.Interaction) -> None:
        if not self.selected_channel:
            await interaction.response.send_message(
                "Please select a target text channel from the dropdown above before continuing.",
                ephemeral=True,
            )
            return

        if interaction.guild:
            perms = self.selected_channel.permissions_for(interaction.guild.me)
            if not (perms.send_messages and perms.embed_links):
                await interaction.response.send_message(
                    f"I require Send Messages and Embed Links permissions in {self.selected_channel.mention} to broadcast news.",
                    ephemeral=True,
                )
                return

        # Advance to Step 2: Modules Selection
        modules_view = TechSetupModulesView(
            bot=self.bot,
            author_id=self.author_id,
            channel=self.selected_channel,
        )
        container = modules_view.build_container()
        await edit_container_response(interaction, container, view=modules_view)


class TechSetupModulesView(discord.ui.View):
    """Step 2: Toggle intelligence modules individually with switch emojis."""

    def __init__(
        self,
        bot: KyroBot,
        author_id: int,
        channel: discord.TextChannel,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id
        self.channel = channel
        
        # If guild already has saved categories, load them; otherwise start empty so user selects to turn ON
        existing = self.bot.tech_mgr.get_config(channel.guild.id) if channel.guild else None
        if existing and existing.get("categories"):
            saved = [c.strip() for c in existing["categories"].split(",") if c.strip() in VALID_CATEGORIES]
            self.active_categories: set[str] = set(saved) if saved else set()
        else:
            self.active_categories: set[str] = set()

        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()

        select_options = [
            discord.SelectOption(
                label=opt["label"],
                value=opt["value"],
                description=opt["description"][:100],
            )
            for opt in MODULE_OPTIONS
        ]

        self.module_select = discord.ui.Select(
            placeholder="Select a module...",
            min_values=1,
            max_values=1,
            options=select_options,
            row=0,
        )
        self.module_select.callback = self._on_toggle_module
        self.add_item(self.module_select)

        self.done_button = discord.ui.Button(
            label="Done",
            style=discord.ButtonStyle.success,
            row=1,
        )
        self.done_button.callback = self._on_done
        self.add_item(self.done_button)

        self.back_button = discord.ui.Button(
            label="Back",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.back_button.callback = self._on_back
        self.add_item(self.back_button)

    def build_container(self) -> KyroContainer:
        """Render container showing module state with switch emojis only (no redundant on/off text)."""
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "[OFF]")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Tech Dashboard\n"
                f"> Step 2 of 2: Select Modules"
            )
        )
        container.add_separator(divider=True)

        info_lines = [
            f"**Target Channel:** {self.channel.mention}\n",
            "Select which intelligence modules to stream into this channel. "
            "Choose modules from the menu below to activate:",
        ]
        container.add_text("\n".join(info_lines))
        container.add_separator(divider=True)

        module_lines = []
        for opt in MODULE_OPTIONS:
            val = opt["value"]
            lbl = opt["label"]
            is_active = val in self.active_categories
            emoji = sw_on if is_active else sw_off
            module_lines.append(f"{emoji} **{lbl}**")

        container.add_text("\n".join(module_lines))
        return container

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not (
            interaction.user.guild_permissions.manage_guild
            if isinstance(interaction.user, discord.Member)
            else False
        ):
            await interaction.response.send_message(
                "Only the command author or server administrators can interact with this setup.",
                ephemeral=True,
            )
            return False
        return True

    async def _on_toggle_module(self, interaction: discord.Interaction) -> None:
        if not self.module_select.values:
            return
        chosen = self.module_select.values[0]
        if chosen in self.active_categories:
            self.active_categories.remove(chosen)
        else:
            self.active_categories.add(chosen)

        # Rebuild view components to reset dropdown selection placeholder cleanly
        self._build_components()
        container = self.build_container()
        await edit_container_response(interaction, container, view=self)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        channel_view = TechSetupChannelView(bot=self.bot, author_id=self.author_id)
        channel_view.selected_channel = self.channel
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Tech Dashboard\n"
                f"> Step 1 of 2: Select Channel"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"Select the text channel where real-time tech intelligence will be broadcast."
        )
        await edit_container_response(interaction, container, view=channel_view)

    async def _on_done(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        if not self.active_categories:
            await interaction.response.send_message(
                "Please enable at least one intelligence module before completing setup.",
                ephemeral=True,
            )
            return

        cat_str = ",".join(self.active_categories)
        success = await self.bot.tech_mgr.set_channel(
            guild_id=interaction.guild.id,
            channel_id=self.channel.id,
            categories=cat_str,
            thread_enabled=False,
        )

        if not success:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content="### Configuration Error\n> Failed to persist tech feed settings to database."
            )
            await edit_container_response(interaction, container, view=None)
            return

        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "[OFF]")
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Tech Dashboard\n"
                f"> Intelligence broadcasting is now active."
            )
        )
        container.add_separator(divider=True)

        cfg = self.bot.tech_mgr.get_config(interaction.guild.id) or {}
        cadence_label = format_cadence_label(cfg.get("cadence", "hourly"))
        top_lines = [
            f"**Channel:** {self.channel.mention}  {dot}  **Cadence:** `{cadence_label}`  {dot}  **Status:** `Active`"
        ]
        container.add_text("\n".join(top_lines))
        container.add_separator(divider=True)

        module_lines = ["**Active Modules:**"]
        for opt in MODULE_OPTIONS:
            val = opt["value"]
            lbl = opt["label"]
            is_active = val in self.active_categories
            emoji = sw_on if is_active else sw_off
            module_lines.append(f"{emoji} **{lbl}**")

        container.add_text("\n".join(module_lines))
        container.add_separator(divider=True)
        await edit_container_response(interaction, container, view=None)


class CustomTechCadenceModal(discord.ui.Modal, title="Custom Delivery Schedule"):
    time_input = discord.ui.TextInput(
        label="Delivery Time (24-Hour IST)",
        placeholder="e.g. 00:00, 14:30 or 21:00",
        min_length=3,
        max_length=5,
        required=True,
    )

    def __init__(self, bot: KyroBot, author_id: int, guild_id: int) -> None:
        super().__init__()
        self.bot = bot
        self.author_id = author_id
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val = self.time_input.value.strip()
        m = re.match(r"^([0-9]|0[0-9]|1[0-9]|2[0-3]):([0-5][0-9])$", val)
        if not m:
            await interaction.response.send_message(
                "Invalid time format. Please enter a valid 24-hour Indian time between 00:00 and 23:59 (e.g., 00:00, 09:00, 14:30, 21:15).",
                ephemeral=True,
            )
            return

        h = int(m.group(1))
        mins = int(m.group(2))
        cadence_val = f"custom:{h:02d}:{mins:02d}"
        await self.bot.tech_mgr.set_cadence(self.guild_id, cadence_val)

        cadence_view = TechCadenceView(self.bot, self.author_id, self.guild_id)
        container = cadence_view.build_container(note=f"Schedule updated to **Daily at {h:02d}:{mins:02d} IST**.")
        await edit_container_response(interaction, container, view=cadence_view)


class TechCadenceView(discord.ui.View):
    """View to select dispatch cadence/timing for Tech Intelligence."""

    def __init__(self, bot: KyroBot, author_id: int, guild_id: int, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id
        self.guild_id = guild_id
        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()
        cfg = self.bot.tech_mgr.get_config(self.guild_id) or {}
        active_cadence = cfg.get("cadence", "hourly")

        select_options = []
        for opt in CADENCE_OPTIONS:
            is_def = (opt["value"] == active_cadence) or (opt["value"] == "custom" and active_cadence.startswith("custom:"))
            select_options.append(
                discord.SelectOption(
                    label=opt["label"],
                    value=opt["value"],
                    description=opt["description"][:100],
                    default=is_def,
                )
            )

        self.cadence_select = discord.ui.Select(
            placeholder="Select delivery schedule...",
            min_values=1,
            max_values=1,
            options=select_options,
            row=0,
        )
        self.cadence_select.callback = self._on_select_cadence
        self.add_item(self.cadence_select)

        self.custom_button = discord.ui.Button(
            label="Custom Time",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.custom_button.callback = self._on_custom_button
        self.add_item(self.custom_button)

        self.back_button = discord.ui.Button(
            label="Back",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.back_button.callback = self._on_back
        self.add_item(self.back_button)

    def build_container(self, note: str | None = None) -> KyroContainer:
        cfg = self.bot.tech_mgr.get_config(self.guild_id) or {}
        current_label = format_cadence_label(cfg.get("cadence", "hourly"))
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Tech Intelligence Feed\n"
                f"> Schedule & Cadence Settings"
            )
        )
        container.add_separator(divider=True)

        lines = [
            f"**Current Schedule:** `{current_label}`\n",
            "Choose how frequently intelligence reports are broadcast to your channel:",
            f"{dot} **Every 15 Minutes:** Continuous real-time updates as stories break.",
            f"{dot} **Hourly Batch:** Top 10 stories delivered hourly with 1-minute pacing.",
            f"{dot} **Morning 9:00 AM:** Daily morning briefing drop at 9:00 AM IST.",
            f"{dot} **Midnight 12:00 AM:** Daily midnight intelligence recap at 12:00 AM IST.",
            f"{dot} **Custom Time:** Specify any exact daily delivery time in 24-hour IST.",
        ]
        if note:
            lines.append(f"\n> {note}")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        return container

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not (
            interaction.user.guild_permissions.manage_guild
            if isinstance(interaction.user, discord.Member)
            else False
        ):
            await interaction.response.send_message(
                "Only server administrators can modify tech feed settings.",
                ephemeral=True,
            )
            return False
        return True

    async def _on_select_cadence(self, interaction: discord.Interaction) -> None:
        if not self.cadence_select.values:
            return
        chosen = self.cadence_select.values[0]
        if chosen == "custom":
            modal = CustomTechCadenceModal(self.bot, self.author_id, self.guild_id)
            await interaction.response.send_modal(modal)
            return

        await self.bot.tech_mgr.set_cadence(self.guild_id, chosen)
        self._build_components()
        container = self.build_container(note=f"Schedule successfully updated to **{format_cadence_label(chosen)}**.")
        await edit_container_response(interaction, container, view=self)

    async def _on_custom_button(self, interaction: discord.Interaction) -> None:
        modal = CustomTechCadenceModal(self.bot, self.author_id, self.guild_id)
        await interaction.response.send_modal(modal)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        if interaction.guild:
            cfg = self.bot.tech_mgr.get_config(self.guild_id)
            if cfg:
                container = await build_tech_dashboard(self.bot, interaction.guild, cfg)
                view = TechStatusView(
                    bot=self.bot,
                    author_id=self.author_id,
                    guild_id=self.guild_id,
                    is_active=True,
                )
                await edit_container_response(interaction, container, view=view)


class TechStatusView(discord.ui.View):
    """Status panel view with Edit, Schedule, Health, and Disable buttons."""

    def __init__(
        self,
        bot: KyroBot,
        author_id: int,
        guild_id: int,
        is_active: bool,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id
        self.guild_id = guild_id

        if is_active:
            self.edit_button = discord.ui.Button(
                label="Edit Settings",
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            self.edit_button.callback = self._on_edit
            self.add_item(self.edit_button)

            self.schedule_button = discord.ui.Button(
                label="Schedule",
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            self.schedule_button.callback = self._on_schedule
            self.add_item(self.schedule_button)

            self.health_button = discord.ui.Button(
                label="Cloud Health",
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            self.health_button.callback = self._on_health_check
            self.add_item(self.health_button)

            self.disable_button = discord.ui.Button(
                label="Disable Feed",
                style=discord.ButtonStyle.danger,
                row=0,
            )
            self.disable_button.callback = self._on_disable
            self.add_item(self.disable_button)
        else:
            self.setup_button = discord.ui.Button(
                label="Configure Feed",
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            self.setup_button.callback = self._on_edit
            self.add_item(self.setup_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not (
            interaction.user.guild_permissions.manage_guild
            if isinstance(interaction.user, discord.Member)
            else False
        ):
            await interaction.response.send_message(
                "Only server administrators can modify tech feed settings.",
                ephemeral=True,
            )
            return False
        return True

    async def _on_edit(self, interaction: discord.Interaction) -> None:
        channel_view = TechSetupChannelView(bot=self.bot, author_id=self.author_id)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Tech Dashboard\n"
                f"> Step 1 of 2: Select Channel"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"Select the text channel where real-time tech intelligence will be broadcast."
        )
        await edit_container_response(interaction, container, view=channel_view)

    async def _on_schedule(self, interaction: discord.Interaction) -> None:
        cadence_view = TechCadenceView(self.bot, self.author_id, self.guild_id)
        container = cadence_view.build_container()
        await edit_container_response(interaction, container, view=cadence_view)

    async def _on_disable(self, interaction: discord.Interaction) -> None:
        await self.bot.tech_mgr.remove_channel(self.guild_id)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Tech Dashboard\n"
                f"> Automated broadcasting has been deactivated for this server."
            )
        )
        await edit_container_response(interaction, container, view=None)

    async def _on_health_check(self, interaction: discord.Interaction) -> None:
        """Display detailed live cloud telemetry matrix."""
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        health = await self.bot.tech_realtime_mgr.get_global_health_summary()

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "### Global Infrastructure Telemetry\n"
                "> Real-time Health Radar for Developer Platforms"
            )
        )
        container.add_separator(divider=True)

        lines = []
        for prov, stat in health.items():
            st_upper = stat.upper()
            lines.append(f"{dot} **{prov}:** `{st_upper}`")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text("-# Live telemetry polled from official status engines every 60s.")
        await send_container_response(interaction, container, ephemeral=True)


class TechFeedCog(commands.Cog):
    """Autonomous Tech Intelligence feed dispatcher and interactive setup."""
    category: str = "Utility"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self._is_dispatching: bool = False
        self._poller_task.start()

    def cog_unload(self) -> None:
        """Cancel background loops cleanly upon cog unload."""
        self._poller_task.cancel()

    # -------------------------------------------------------------------------
    # Interactive Bookmark Listener (Save to DM)
    # -------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Handle 'Save to DM' bookmark button clicks on tech news cards."""
        custom_id = (interaction.data or {}).get("custom_id")
        if not custom_id or not isinstance(custom_id, str) or not custom_id.startswith("tech_bm:"):
            return

        story_id = custom_id.replace("tech_bm:", "")
        story = self.bot.tech_mgr.get_story(story_id)
        if not story:
            try:
                await interaction.response.send_message(
                    "This story has expired from active cache. You can view it directly using the article link button.",
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        try:
            dot = self.bot.custom_emojis.get("heart_dot", "•")
            dm_card = self.bot.tech_mgr.build_story_container(story, dot=dot)
            await send_container_response(interaction.user, dm_card)
            await interaction.response.send_message(
                "Saved this article to your private DM inbox!",
                ephemeral=True,
            )
        except Exception:
            try:
                await interaction.response.send_message(
                    "Could not send DM. Please make sure your DMs are open for server members.",
                    ephemeral=True,
                )
            except Exception:
                pass

    def cog_unload(self) -> None:
        """Cancel background poller loop when extension unloads or reloads to prevent ghost tasks."""
        self._poller_task.cancel()

    # -------------------------------------------------------------------------
    # Autonomous Background Dispatcher Loop (15-Minute Cadence Check in IST)
    # -------------------------------------------------------------------------
    @tasks.loop(minutes=15)
    async def _poller_task(self) -> None:
        """Background poller checking guild schedules and dispatching curated intelligence batches."""
        try:
            await self.bot.wait_until_ready()
        except (RuntimeError, Exception):
            return

        guild_configs = self.bot.tech_mgr.get_all_configs()
        if not guild_configs:
            return  # Zero active subscriptions; avoid unnecessary network requests

        if self._is_dispatching:
            return

        now_ist = datetime.now(IST)
        eligible_guilds = {
            g_id: cfg for g_id, cfg in guild_configs.items()
            if is_cadence_eligible(cfg, now_ist)
        }
        if not eligible_guilds:
            return

        self._is_dispatching = True
        # Immediately record dispatch timestamp for all eligible guilds so no other loop or task can re-qualify
        for g_id in eligible_guilds.keys():
            await self.bot.tech_mgr.update_last_dispatch(g_id, now_ist)

        try:
            # 1. Harvest balanced batch of up to 10 top-signal items across all categories
            stories = await self.bot.tech_mgr.harvest_balanced_batch(target_total=10)
            if not stories:
                return

            dot = self.bot.custom_emojis.get("heart_dot", "•")
            today_str = now_ist.strftime("%Y-%m-%d")

            # 2. Handle Morning Digest for guilds configured in 'digest' mode (Trigger at or after 9 AM IST)
            if now_ist.hour >= 9:
                for guild_id, cfg in list(eligible_guilds.items()):
                    if cfg.get("mode") == "digest" and cfg.get("last_digest_date") != today_str:
                        guild = self.bot.get_guild(guild_id)
                        if not guild:
                            continue
                        channel = guild.get_channel(cfg["channel_id"])
                        if isinstance(channel, discord.TextChannel):
                            digest_card = self.bot.tech_mgr.build_digest_container(stories[:4], today_str, dot=dot)
                            try:
                                await send_container_response(channel, digest_card)
                                await self.bot.tech_mgr.update_last_digest(guild_id, today_str)
                            except Exception as d_err:
                                logger.debug(f"Notice sending digest to guild {guild_id}: {d_err}")

            # 3. Pre-flight health check: Verify candidate URLs live before broadcasting
            batch_to_send: list[TechStory] = []
            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=4)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                for candidate in stories:
                    if len(batch_to_send) >= 10:
                        break
                    is_alive = await validate_url_live(session, candidate.url)
                    if is_alive:
                        batch_to_send.append(candidate)
                    else:
                        logger.warning(f"Pre-flight check dropped unreachable URL: {candidate.url}")
                        await self.bot.tech_mgr.mark_dispatched([candidate])

            # Strictly enforce maximum 10 items per batch
            batch_to_send = batch_to_send[:10]
            logger.info(f"Dispatching batch of {len(batch_to_send)} balanced tech story/stories to {len(eligible_guilds)} scheduled guild(s).")

            # 4. Dispatch items one by one with strict 1-minute (60s) delay between each post
            for index, story in enumerate(batch_to_send):
                card = self.bot.tech_mgr.build_story_container(story, dot=dot)
                dispatched_any = False

                for guild_id, cfg in list(eligible_guilds.items()):
                    guild = self.bot.get_guild(guild_id)
                    channel = guild.get_channel(cfg.get("channel_id")) if guild else None
                    if not channel:
                        try:
                            channel = await self.bot.fetch_channel(cfg.get("channel_id"))
                        except Exception:
                            channel = None

                    if not channel or not isinstance(channel, discord.TextChannel):
                        continue

                    # In 'digest' mode, do not post real-time updates
                    if cfg.get("mode") == "digest":
                        continue

                    # Verify category matching
                    allowed_cats = cfg.get("categories", "all").split(",")
                    if "all" not in allowed_cats and story.category not in allowed_cats:
                        continue

                    try:
                        msg = await send_container_response(channel, card)
                        dispatched_any = True

                        # Auto-create discussion thread if enabled for this guild
                        if cfg.get("thread_enabled") and msg and isinstance(msg, discord.Message):
                            clean_thread_name = f"Discussion: {story.title[:80]}"
                            try:
                                await msg.create_thread(name=clean_thread_name, auto_archive_duration=1440)
                            except Exception as th_err:
                                logger.debug(f"Thread creation notice: {th_err}")
                    except Exception as ch_err:
                        logger.debug(f"Failed to dispatch tech story to guild {guild_id}: {ch_err}")

                if dispatched_any:
                    await self.bot.tech_mgr.mark_dispatched([story])
                else:
                    self.bot.tech_mgr._seen_hashes.add(story.id)
                    if story.title_hash:
                        self.bot.tech_mgr._seen_title_hashes.add(story.title_hash)
                    if story.entity_hash:
                        self.bot.tech_mgr._seen_entity_hashes.add(story.entity_hash)

                # Exactly 1 minute (60 seconds) delay between each of the posts
                if index < len(batch_to_send) - 1:
                    await asyncio.sleep(60)

        except Exception as exc:
            logger.error(f"Unexpected exception in tech news background poller: {exc}", exc_info=exc)
        finally:
            self._is_dispatching = False

    @_poller_task.before_loop
    async def _before_poller(self) -> None:
        """Wait until the bot gateway is ready before starting the background loop."""
        try:
            await self.bot.wait_until_ready()
        except (RuntimeError, Exception):
            pass



    # -------------------------------------------------------------------------
    # Unified Command: tech
    # -------------------------------------------------------------------------
    @commands.hybrid_command(
        name="tech",
        aliases=["technews", "techfeed"],
        description="Autonomous Tech Intelligence terminal & feed dashboard.",
    )
    @commands.guild_only()
    async def tech(self, ctx: CustomContext) -> None:
        """Unified Tech Dashboard: displays live controls if configured, or launches setup if not set."""
        cfg = self.bot.tech_mgr.get_config(ctx.guild.id)
        if cfg:
            container = await build_tech_dashboard(self.bot, ctx.guild, cfg)
            view = TechStatusView(
                bot=self.bot,
                author_id=ctx.author.id,
                guild_id=ctx.guild.id,
                is_active=True,
            )
            await send_container_response(ctx, container, view=view)
        elif ctx.author.guild_permissions.manage_guild:
            channel_view = TechSetupChannelView(bot=self.bot, author_id=ctx.author.id)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"### Tech Dashboard\n"
                    f"> Step 1 of 2: Select Channel"
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                "Select the text channel where real-time tech intelligence will be broadcast."
            )
            await send_container_response(ctx, container, view=channel_view)
        else:
            dot = self.bot.custom_emojis.get("heart_dot", "•")
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"### Tech Dashboard\n"
                    f"> Status: Inactive on this server"
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} Automated tech intelligence broadcasts are currently disabled.\n"
                f"{dot} Server administrators can run `{ctx.clean_prefix}tech` to configure and activate broadcasting."
            )
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Register TechFeedCog with KyroBot."""
    await bot.add_cog(TechFeedCog(bot))
