"""
Kyro Discord Bot - Dev Dashboard & Opportunities Autonomous Feed Cog
Background ingestion delivering live paid bounties, fresher jobs, hackathons, free perks, and AI tools.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import re
from typing import TYPE_CHECKING, Optional, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.core.context import CustomContext
from src.managers.dev_pulse_manager import CATEGORY_BADGES, DevPulseStory
from src.utils.containers import (
    KyroContainer,
    edit_container_response,
    send_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Utility.DevFeed")

VALID_CATEGORIES: set[str] = {"all", "bounties", "jobs", "hackathons", "perks", "tools"}

CADENCE_OPTIONS: list[dict[str, str]] = [
    {
        "label": "Every 15 Minutes",
        "value": "15m",
        "description": "Continuous real-time stream as new developer opportunities arrive",
    },
    {
        "label": "Hourly Batch (Default)",
        "value": "hourly",
        "description": "10 curated top opportunities delivered hourly with 1m pacing",
    },
    {
        "label": "Morning 9:00 AM UTC",
        "value": "09:00",
        "description": "Daily morning developer digest drop at 9:00 AM UTC",
    },
    {
        "label": "Midnight 12:00 AM UTC",
        "value": "00:00",
        "description": "Daily midnight opportunity recap drop at 12:00 AM UTC",
    },
    {
        "label": "Custom Time (UTC)",
        "value": "custom",
        "description": "Specify custom 24-hour daily delivery time (HH:MM UTC)",
    },
]


def format_cadence_label(cadence: str) -> str:
    c = str(cadence or "hourly").lower().strip()
    if c == "15m":
        return "Every 15 Minutes"
    if c == "hourly":
        return "Hourly Batch (1h)"
    if c == "09:00":
        return "Morning 9:00 AM UTC"
    if c == "00:00":
        return "Midnight 12:00 AM UTC"
    if c.startswith("custom:") or ":" in c:
        raw_time = c.replace("custom:", "").strip()
        return f"Daily at {raw_time} UTC"
    return "Hourly Batch (1h)"


def is_cadence_eligible(cfg: dict[str, Any], now_utc: datetime) -> bool:
    cadence = str(cfg.get("cadence") or "hourly").lower().strip()
    last_dispatch = cfg.get("last_dispatch_ts")
    today_str = now_utc.strftime("%Y-%m-%d")

    if isinstance(last_dispatch, str):
        try:
            last_dispatch = datetime.fromisoformat(last_dispatch)
        except Exception:
            last_dispatch = None

    if last_dispatch and last_dispatch.tzinfo is None:
        last_dispatch = last_dispatch.replace(tzinfo=timezone.utc)

    # 1. Real-time every 15 minutes
    if cadence == "15m":
        if last_dispatch is None:
            return True
        return (now_utc - last_dispatch).total_seconds() >= 800

    # 2. Morning 9:00 AM UTC
    if cadence == "09:00":
        if now_utc.hour == 9:
            if last_dispatch is None:
                return True
            return last_dispatch.strftime("%Y-%m-%d") != today_str
        return False

    # 3. Midnight 12:00 AM UTC
    if cadence == "00:00":
        if now_utc.hour == 0:
            if last_dispatch is None:
                return True
            return last_dispatch.strftime("%Y-%m-%d") != today_str
        return False

    # 4. Custom 24h Time: "custom:HH:MM" or "HH:MM"
    if cadence.startswith("custom:") or ":" in cadence:
        raw_time = cadence.replace("custom:", "").strip()
        try:
            parts = raw_time.split(":")
            h, m = int(parts[0]), int(parts[1])
            target_mins = h * 60 + m
            curr_mins = now_utc.hour * 60 + now_utc.minute
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
    return (now_utc - last_dispatch).total_seconds() >= 3500


async def build_dev_dashboard(bot: KyroBot, guild: discord.Guild, cfg: dict[str, Any]) -> KyroContainer:
    channel = guild.get_channel(cfg["channel_id"])
    ch_mention = channel.mention if channel else f"Unknown ({cfg['channel_id']})"
    raw_cats = {c.strip() for c in cfg.get("categories", "all").split(",")}

    sw_on = bot.custom_emojis.get("icon_switch_on", "[ON]")
    sw_off = bot.custom_emojis.get("icon_switch_off", "[OFF]")
    dot = bot.custom_emojis.get("heart_dot", "•")

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"### Dev Dashboard\n"
            f"> Status: Active & Broadcasting"
        )
    )
    container.add_separator(divider=True)

    cadence_raw = cfg.get("cadence", "hourly")
    cadence_label = format_cadence_label(cadence_raw)

    top_lines = [
        f"**Channel:** {ch_mention}  {dot}  **Cadence:** `{cadence_label} (10 Items • 1m Delay)`  {dot}  **Status:** `Active`"
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
        "label": "Paid Bounties",
        "value": "bounties",
        "description": "Open-source GitHub issues with verified $50-$500 cash rewards",
    },
    {
        "label": "Fresher Jobs",
        "value": "jobs",
        "description": "Entry-level software engineering roles & paid remote internships",
    },
    {
        "label": "Hackathons",
        "value": "hackathons",
        "description": "Global coding competitions, prize pools & team matching",
    },
    {
        "label": "Dev Perks",
        "value": "perks",
        "description": "Free cloud credits, domain vouchers & 100% off dev courses",
    },
    {
        "label": "AI Dev Tools",
        "value": "tools",
        "description": "Practical developer AI tools with generous free tiers",
    },
]


class DevSetupChannelView(discord.ui.View):
    """Step 1: Select text channel for developer opportunities broadcasts."""

    def __init__(self, bot: KyroBot, author_id: int, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id
        self.selected_channel: discord.TextChannel | None = None

        self.channel_select = discord.ui.ChannelSelect(
            channel_types=[discord.ChannelType.text],
            placeholder="Select a channel...",
            min_values=1,
            max_values=1,
            row=0,
        )
        self.channel_select.callback = self._on_channel_select
        self.add_item(self.channel_select)

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
        else:
            self.selected_channel = interaction.guild.get_channel(selected.id) if interaction.guild else None

        await interaction.response.defer()

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        self.stop()
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Dev Dashboard\n"
                f"> Setup cancelled. No changes were saved."
            )
        )
        await edit_container_response(interaction, container, view=None)

    async def _on_continue(self, interaction: discord.Interaction) -> None:
        if not self.selected_channel:
            await interaction.response.send_message(
                "Please select a text channel first before proceeding to Step 2.",
                ephemeral=True,
            )
            return

        self.stop()
        modules_view = DevSetupModulesView(
            bot=self.bot,
            author_id=self.author_id,
            channel=self.selected_channel,
        )
        container = modules_view.build_container()
        await edit_container_response(interaction, container, view=modules_view)


class DevSetupModulesView(discord.ui.View):
    """Step 2: Toggle developer modules individually with switch emojis."""

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

        existing = self.bot.dev_mgr.get_guild_config(channel.guild.id) if channel.guild else None
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
        """Render container showing module state with switch emojis only."""
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "[OFF]")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Dev Dashboard\n"
                f"> Step 2 of 2: Select Modules"
            )
        )
        container.add_separator(divider=True)

        info_lines = [
            f"**Target Channel:** {self.channel.mention}\n",
            "Select which developer modules to stream into this channel. "
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

        self._build_components()
        container = self.build_container()
        await edit_container_response(interaction, container, view=self)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        channel_view = DevSetupChannelView(bot=self.bot, author_id=self.author_id)
        channel_view.selected_channel = self.channel
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Dev Dashboard\n"
                f"> Step 1 of 2: Select Channel"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"Select the text channel where real-time developer opportunities will be broadcast."
        )
        await edit_container_response(interaction, container, view=channel_view)

    async def _on_done(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            return

        if not self.active_categories:
            await interaction.response.send_message(
                "Please enable at least one module before completing setup.",
                ephemeral=True,
            )
            return

        cat_str = ",".join(self.active_categories)
        success = await self.bot.dev_mgr.set_channel(
            guild_id=interaction.guild.id,
            channel_id=self.channel.id,
            categories=cat_str,
            thread_enabled=False,
        )

        if not success:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content="### Configuration Error\n> Failed to persist dev feed settings to database."
            )
            await edit_container_response(interaction, container, view=None)
            return

        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "[OFF]")
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Dev Dashboard\n"
                f"> Opportunities broadcasting is now active."
            )
        )
        container.add_separator(divider=True)

        cfg = self.bot.dev_mgr.get_guild_config(interaction.guild.id) or {}
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


class CustomDevCadenceModal(discord.ui.Modal, title="Custom Delivery Schedule"):
    time_input = discord.ui.TextInput(
        label="Delivery Time (24-Hour UTC)",
        placeholder="e.g. 14:30 or 21:00",
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
                "Invalid time format. Please enter a valid 24-hour time between 00:00 and 23:59 (e.g., 09:00, 14:30, 21:15).",
                ephemeral=True,
            )
            return

        h = int(m.group(1))
        mins = int(m.group(2))
        cadence_val = f"custom:{h:02d}:{mins:02d}"
        await self.bot.dev_mgr.set_cadence(self.guild_id, cadence_val)

        cadence_view = DevCadenceView(self.bot, self.author_id, self.guild_id)
        container = cadence_view.build_container(note=f"Schedule updated to **Daily at {h:02d}:{mins:02d} UTC**.")
        await edit_container_response(interaction, container, view=cadence_view)


class DevCadenceView(discord.ui.View):
    """View to select dispatch cadence/timing for Developer Opportunities."""

    def __init__(self, bot: KyroBot, author_id: int, guild_id: int, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id
        self.guild_id = guild_id
        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()
        cfg = self.bot.dev_mgr.get_guild_config(self.guild_id) or {}
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
        cfg = self.bot.dev_mgr.get_guild_config(self.guild_id) or {}
        current_label = format_cadence_label(cfg.get("cadence", "hourly"))
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Dev Opportunities Radar\n"
                f"> Schedule & Cadence Settings"
            )
        )
        container.add_separator(divider=True)

        lines = [
            f"**Current Schedule:** `{current_label}`\n",
            "Choose how frequently developer opportunities are broadcast to your channel:",
            f"{dot} **Every 15 Minutes:** Continuous stream as fresh opportunities appear.",
            f"{dot} **Hourly Batch:** Top 10 opportunities delivered hourly with 1-minute pacing.",
            f"{dot} **Morning 9:00 AM:** Daily morning digest drop at 9:00 AM UTC.",
            f"{dot} **Midnight 12:00 AM:** Daily midnight opportunity recap at 12:00 AM UTC.",
            f"{dot} **Custom Time:** Specify any exact daily delivery time in 24-hour UTC.",
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
                "Only server administrators can modify dev feed settings.",
                ephemeral=True,
            )
            return False
        return True

    async def _on_select_cadence(self, interaction: discord.Interaction) -> None:
        if not self.cadence_select.values:
            return
        chosen = self.cadence_select.values[0]
        if chosen == "custom":
            modal = CustomDevCadenceModal(self.bot, self.author_id, self.guild_id)
            await interaction.response.send_modal(modal)
            return

        await self.bot.dev_mgr.set_cadence(self.guild_id, chosen)
        self._build_components()
        container = self.build_container(note=f"Schedule successfully updated to **{format_cadence_label(chosen)}**.")
        await edit_container_response(interaction, container, view=self)

    async def _on_custom_button(self, interaction: discord.Interaction) -> None:
        modal = CustomDevCadenceModal(self.bot, self.author_id, self.guild_id)
        await interaction.response.send_modal(modal)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        if interaction.guild:
            cfg = self.bot.dev_mgr.get_guild_config(self.guild_id)
            if cfg:
                container = await build_dev_dashboard(self.bot, interaction.guild, cfg)
                view = DevStatusView(
                    bot=self.bot,
                    author_id=self.author_id,
                    guild_id=self.guild_id,
                    is_active=True,
                )
                await edit_container_response(interaction, container, view=view)


class DevStatusView(discord.ui.View):
    """Status panel view with Edit Settings, Schedule, and Disable Feed buttons."""

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
                "Only server administrators can modify dev feed settings.",
                ephemeral=True,
            )
            return False
        return True

    async def _on_edit(self, interaction: discord.Interaction) -> None:
        channel_view = DevSetupChannelView(bot=self.bot, author_id=self.author_id)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Dev Dashboard\n"
                f"> Step 1 of 2: Select Channel"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"Select the text channel where real-time developer opportunities will be broadcast."
        )
        await edit_container_response(interaction, container, view=channel_view)

    async def _on_schedule(self, interaction: discord.Interaction) -> None:
        cadence_view = DevCadenceView(self.bot, self.author_id, self.guild_id)
        container = cadence_view.build_container()
        await edit_container_response(interaction, container, view=cadence_view)

    async def _on_disable(self, interaction: discord.Interaction) -> None:
        await self.bot.dev_mgr.disable_feed(self.guild_id)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Dev Dashboard\n"
                f"> Automated broadcasting has been deactivated for this server."
            )
        )
        await edit_container_response(interaction, container, view=None)


class DevFeedCog(commands.Cog):
    """Autonomous Developer Opportunities & Career feed dispatcher."""
    category: str = "Utility"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self._is_dispatching: bool = False
        self._poller_task.start()

    def cog_unload(self) -> None:
        self._poller_task.cancel()

    # -------------------------------------------------------------------------
    # Bookmark Listener (Save to DM)
    # -------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Handle 'Save to DM' bookmark button clicks on developer opportunity cards."""
        custom_id = (interaction.data or {}).get("custom_id")
        if not custom_id or not isinstance(custom_id, str) or not custom_id.startswith("dev_bm:"):
            return

        story_id = custom_id.replace("dev_bm:", "")
        story = self.bot.dev_mgr.get_story(story_id)
        if not story:
            try:
                await interaction.response.send_message(
                    "This opportunity card has expired from active cache. You can view it directly using the primary link button.",
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        try:
            dot = self.bot.custom_emojis.get("heart_dot", "•")
            dm_card = self.bot.dev_mgr.build_story_container(story, dot=dot)
            await send_container_response(interaction.user, dm_card)
            await interaction.response.send_message(
                "Saved this developer opportunity card to your private DM inbox!",
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

    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # Background Ingestion & Dispatch Loop (15-Minute Cadence Check)
    # -------------------------------------------------------------------------
    @tasks.loop(minutes=15)
    async def _poller_task(self) -> None:
        """Background loop checking guild schedules and dispatching curated opportunity batches."""
        try:
            await self.bot.wait_until_ready()
        except (RuntimeError, Exception):
            return

        configs = self.bot.dev_mgr.get_all_configs()
        if not configs:
            return

        if self._is_dispatching:
            return

        now_utc = discord.utils.utcnow()
        eligible_guilds = {
            g_id: cfg for g_id, cfg in configs.items()
            if is_cadence_eligible(cfg, now_utc)
        }
        if not eligible_guilds:
            return

        self._is_dispatching = True
        try:
            # 1. Harvest balanced batch of up to 10 top-signal items across all categories
            candidates = await self.bot.dev_mgr.harvest_balanced_batch(target_total=10)
            if not candidates:
                return

            dot = self.bot.custom_emojis.get("heart_dot", "•")
            logger.info(f"Dispatching batch of {len(candidates)} balanced dev opportunities to {len(eligible_guilds)} scheduled guild(s).")

            dispatched_guild_ids: set[int] = set()

            # 2. Dispatch items one by one with strict 1-minute (60s) delay between each post
            for index, story in enumerate(candidates):
                card = self.bot.dev_mgr.build_story_container(story, dot=dot)
                dispatched_any = False

                for guild_id, cfg in eligible_guilds.items():
                    channel_id = cfg.get("channel_id")
                    cats_allowed = cfg.get("categories", "all")
                    if not channel_id or cats_allowed == "none":
                        continue

                    if cats_allowed != "all" and story.category not in cats_allowed.split(","):
                        continue

                    guild = self.bot.get_guild(guild_id)
                    channel = guild.get_channel(channel_id) if guild else None
                    if not channel:
                        try:
                            channel = await self.bot.fetch_channel(channel_id)
                        except Exception:
                            channel = None

                    if not channel or not isinstance(channel, discord.TextChannel):
                        continue

                    try:
                        await send_container_response(channel, card)
                        dispatched_any = True
                        dispatched_guild_ids.add(guild_id)
                    except Exception as send_err:
                        logger.debug(f"Notice dispatching opportunity {story.id} to guild {guild_id}: {send_err}")

                if dispatched_any:
                    # Persist immediately to prevent repeats or race conditions
                    await self.bot.dev_mgr.record_dispatched([story])
                else:
                    self.bot.dev_mgr._seen_hashes.add(story.id)
                    if story.title_hash:
                        self.bot.dev_mgr._seen_title_hashes.add(story.title_hash)
                    if story.entity_hash:
                        self.bot.dev_mgr._seen_entity_hashes.add(story.entity_hash)

                # Exactly 1 minute (60 seconds) delay between each of the posts
                if index < len(candidates) - 1:
                    await asyncio.sleep(60)

            for g_id in dispatched_guild_ids:
                await self.bot.dev_mgr.update_last_dispatch(g_id, now_utc)

        except Exception as e:
            logger.error(f"Error in DevFeed background poller: {e}", exc_info=e)
        finally:
            self._is_dispatching = False

    # -------------------------------------------------------------------------
    # Single Unified Command: dev
    # -------------------------------------------------------------------------
    @commands.hybrid_command(
        name="dev",
        aliases=["devpulse", "opportunities", "bounties", "devjobs"],
        description="Autonomous Developer Opportunities & Career Dashboard.",
    )
    @app_commands.describe(
        category="Optional category to fetch live right now (bounties, jobs, hackathons, perks, tools)"
    )
    @commands.guild_only()
    async def dev(self, ctx: CustomContext, category: Optional[str] = None) -> None:
        """Unified Dev Dashboard: displays live controls, launches setup, or fetches live opportunities on demand."""
        if category:
            cat_clean = category.strip().lower()
            valid_cats = {"bounties", "bounty", "jobs", "job", "careers", "internships", "hackathons", "hackathon", "perks", "perk", "tools", "tool"}
            if cat_clean in valid_cats:
                await ctx.defer(ephemeral=False)
                stories = await self.bot.dev_mgr.fetch_category(cat_clean, limit=1)
                if not stories:
                    container = KyroContainer(accent_color=None)
                    container.add_section(
                        content=f"### Dev Radar\n> No fresh opportunities found right now for `{cat_clean}`. Please check back shortly."
                    )
                    await send_container_response(ctx, container)
                    return

                story_to_send = stories[0]
                dot = self.bot.custom_emojis.get("heart_dot", "•")
                card = self.bot.dev_mgr.build_story_container(story_to_send, dot=dot)
                await send_container_response(ctx, card)
                # Mark dispatched so subsequent calls or background cycles never repeat this story
                await self.bot.dev_mgr.record_dispatched([story_to_send])
                return

        cfg = self.bot.dev_mgr.get_guild_config(ctx.guild.id)
        if cfg:
            container = await build_dev_dashboard(self.bot, ctx.guild, cfg)
            view = DevStatusView(
                bot=self.bot,
                author_id=ctx.author.id,
                guild_id=ctx.guild.id,
                is_active=True,
            )
            await send_container_response(ctx, container, view=view)
            return

        # Not configured yet -> Launch Step 1
        channel_view = DevSetupChannelView(bot=self.bot, author_id=ctx.author.id)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Dev Dashboard\n"
                f"> Step 1 of 2: Select Channel"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"Select the text channel where real-time developer opportunities will be broadcast."
        )
        await send_container_response(ctx, container, view=channel_view)


async def setup(bot: KyroBot) -> None:
    """Standard extension loader entrypoint."""
    await bot.add_cog(DevFeedCog(bot))
