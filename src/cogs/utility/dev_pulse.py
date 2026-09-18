"""
Kyro Discord Bot - Dev Dashboard & Opportunities Autonomous Feed Cog
Background ingestion delivering live paid bounties, fresher jobs, hackathons, free perks, and AI tools.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

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

        top_lines = [
            f"**Channel:** {self.channel.mention}  {dot}  **Cadence:** `Every 20m`  {dot}  **Status:** `Active`"
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


class DevStatusView(discord.ui.View):
    """Status panel view with Edit Settings and Disable Feed buttons matching Tech design."""

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
    # Background Ingestion & Dispatch Loop (Every 20 Minutes)
    # -------------------------------------------------------------------------
    @tasks.loop(minutes=20)
    async def _poller_task(self) -> None:
        """Background loop harvesting bounties, jobs, hackathons, perks, and AI tools."""
        try:
            await self.bot.wait_until_ready()
        except (RuntimeError, Exception):
            return

        configs = self.bot.dev_mgr.get_all_configs()
        if not configs:
            return

        try:
            stories = await self.bot.dev_mgr.harvest_all()
            if not stories:
                return

            unseen = [s for s in stories if not self.bot.dev_mgr.is_seen(s.id)]
            if not unseen:
                return

            dot = self.bot.custom_emojis.get("heart_dot", "•")
            dispatched: list[DevPulseStory] = []

            for story in unseen[:8]:
                card = self.bot.dev_mgr.build_story_container(story, dot=dot)
                dispatched_any = False

                for guild_id, cfg in configs.items():
                    channel_id = cfg.get("channel_id")
                    cats_allowed = cfg.get("categories", "all")
                    if not channel_id or cats_allowed == "none":
                        continue

                    if cats_allowed != "all" and story.category not in cats_allowed.split(","):
                        continue

                    channel = self.bot.get_channel(channel_id)
                    if not channel or not isinstance(channel, discord.TextChannel):
                        continue

                    try:
                        await send_container_response(channel, card)
                        dispatched_any = True
                    except Exception as send_err:
                        logger.debug(f"Notice dispatching opportunity {story.id} to guild {guild_id}: {send_err}")

                if dispatched_any:
                    dispatched.append(story)

            if dispatched:
                await self.bot.dev_mgr.record_dispatched(dispatched)

        except Exception as e:
            logger.error(f"Error in DevFeed background poller: {e}", exc_info=e)

    # -------------------------------------------------------------------------
    # Single Unified Command: dev
    # -------------------------------------------------------------------------
    @commands.hybrid_command(
        name="dev",
        aliases=["devpulse", "opportunities", "bounties", "devjobs"],
        description="Autonomous Developer Opportunities & Career Dashboard.",
    )
    @commands.guild_only()
    async def dev(self, ctx: CustomContext) -> None:
        """Unified Dev Dashboard: displays live controls if configured, or launches setup if not set."""
        cfg = self.bot.dev_mgr.get_guild_config(ctx.guild.id)
        if cfg:
            channel = ctx.guild.get_channel(cfg["channel_id"])
            ch_mention = channel.mention if channel else f"Unknown ({cfg['channel_id']})"
            raw_cats = {c.strip() for c in cfg.get("categories", "all").split(",")}

            sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
            sw_off = self.bot.custom_emojis.get("icon_switch_off", "[OFF]")
            dot = self.bot.custom_emojis.get("heart_dot", "•")

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"### Dev Dashboard\n"
                    f"> Status: Active & Broadcasting"
                )
            )
            container.add_separator(divider=True)

            top_lines = [
                f"**Channel:** {ch_mention}  {dot}  **Cadence:** `Every 20m`  {dot}  **Status:** `Active`"
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
