"""
Kyro Discord Bot - Developer Opportunities & Career Autonomous Feed Cog
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

logger = logging.getLogger("Kyro.Utility.DevPulse")

VALID_CATEGORIES: set[str] = {"all", "bounties", "jobs", "hackathons", "perks", "tools"}

DEV_MODULE_OPTIONS: list[dict[str, str]] = [
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
            placeholder="Select developer opportunities channel...",
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
                "**Developer Pulse Setup Cancelled**\n"
                "> No changes were saved to server feed configurations."
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
        channel = self.selected_channel
        step2_view = DevSetupModuleView(self.bot, self.author_id, channel)
        step2_container = step2_view.build_step2_container()
        await edit_container_response(interaction, step2_container, view=step2_view)


class DevSetupModuleView(discord.ui.View):
    """Step 2: Multi-select modules with live switch state display."""

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
        if existing and existing.get("categories") and existing.get("categories") != "all":
            self.active_modules: set[str] = set(existing["categories"].split(","))
        else:
            self.active_modules: set[str] = {opt["value"] for opt in DEV_MODULE_OPTIONS}

        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()

        options = [
            discord.SelectOption(
                label=opt["label"],
                value=opt["value"],
                description=opt["description"],
                default=(opt["value"] in self.active_modules),
            )
            for opt in DEV_MODULE_OPTIONS
        ]

        self.module_select = discord.ui.Select(
            placeholder="Choose modules to enable or disable...",
            min_values=0,
            max_values=len(DEV_MODULE_OPTIONS),
            options=options,
            row=0,
        )
        self.module_select.callback = self._on_module_select
        self.add_item(self.module_select)

        self.back_button = discord.ui.Button(
            label="Back",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.back_button.callback = self._on_back
        self.add_item(self.back_button)

        self.save_button = discord.ui.Button(
            label="Save Feed",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.save_button.callback = self._on_save
        self.add_item(self.save_button)

    def build_step2_container(self) -> KyroContainer:
        """Render clean Step 2 configuration view."""
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_on = self.bot.custom_emojis.get("switch_on", "[ON]")
        sw_off = self.bot.custom_emojis.get("switch_off", "[OFF]")

        module_lines: list[str] = []
        for opt in DEV_MODULE_OPTIONS:
            is_on = opt["value"] in self.active_modules
            status_icon = sw_on if is_on else sw_off
            module_lines.append(
                f"{status_icon} **{opt['label']}**\n"
                f"> {dot} *{opt['description']}*"
            )

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Developer Pulse Dashboard — Opportunities Setup (Step 2/2)**\n"
                f"> Broadcast Target: {self.channel.mention}\n"
                "> Toggle the developer modules you want active in your community feed:"
            )
        )
        container.add_separator(divider=True)
        container.add_text("\n\n".join(module_lines))
        return container

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not (
            interaction.user.guild_permissions.manage_guild
            if isinstance(interaction.user, discord.Member)
            else False
        ):
            await interaction.response.send_message(
                "Only the command author or server administrators can modify feed settings.",
                ephemeral=True,
            )
            return False
        return True

    async def _on_module_select(self, interaction: discord.Interaction) -> None:
        self.active_modules = set(self.module_select.values)
        self._build_components()
        container = self.build_step2_container()
        await edit_container_response(interaction, container, view=self)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        self.stop()
        step1_view = DevSetupChannelView(self.bot, self.author_id)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Developer Pulse Dashboard — Step 1/2**\n"
                "> Select a text channel where developer opportunities should be broadcasted:"
            )
        )
        await edit_container_response(interaction, container, view=step1_view)

    async def _on_save(self, interaction: discord.Interaction) -> None:
        self.stop()
        if not self.active_modules:
            cat_string = "none"
        elif len(self.active_modules) == len(DEV_MODULE_OPTIONS):
            cat_string = "all"
        else:
            cat_string = ",".join(sorted(self.active_modules))

        guild_id = self.channel.guild.id
        channel_id = self.channel.id

        success = await self.bot.dev_mgr.set_channel(
            guild_id=guild_id,
            channel_id=channel_id,
            categories=cat_string,
        )

        container = KyroContainer(accent_color=None)
        if success:
            dot = self.bot.custom_emojis.get("heart_dot", "•")
            sw_on = self.bot.custom_emojis.get("switch_on", "[ON]")
            active_labels = [
                opt["label"]
                for opt in DEV_MODULE_OPTIONS
                if opt["value"] in self.active_modules
            ]
            cats_display = f" {dot} ".join(active_labels) if active_labels else "None (Feed Muted)"

            container.add_section(
                content=(
                    f"**{sw_on} Developer Pulse Feed Active**\n"
                    f"> **Channel:** {self.channel.mention}\n"
                    f"> **Modules:** {cats_display}\n"
                    f"> **Mode:** Real-time Autonomous Live Stream"
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"> {dot} Verified opportunities will be broadcasted here automatically.\n"
                f"> {dot} Members can save cards directly to DMs using the **Save to DM** button.\n"
                f"> {dot} Use `/devpulse` or `!devpulse` anytime to edit modules or disable feed."
            )
        else:
            container.add_section(
                content=(
                    "**Database Error Encountered**\n"
                    "> Failed to save developer opportunities preferences. Please try again later."
                )
            )

        await edit_container_response(interaction, container, view=None)


class DevDashboardView(discord.ui.View):
    """Active Dev Dashboard control view."""

    def __init__(self, bot: KyroBot, author_id: int, guild_id: int, timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not (
            interaction.user.guild_permissions.manage_guild
            if isinstance(interaction.user, discord.Member)
            else False
        ):
            await interaction.response.send_message(
                "Only the command author or server administrators can manage this feed.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Edit Settings", style=discord.ButtonStyle.secondary, row=0)
    async def edit_settings(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        cfg = self.bot.dev_mgr.get_guild_config(self.guild_id)
        current_ch = interaction.guild.get_channel(cfg["channel_id"]) if (interaction.guild and cfg) else None
        
        if current_ch and isinstance(current_ch, discord.TextChannel):
            step2_view = DevSetupModuleView(self.bot, self.author_id, current_ch)
            container = step2_view.build_step2_container()
            await edit_container_response(interaction, container, view=step2_view)
        else:
            step1_view = DevSetupChannelView(self.bot, self.author_id)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Developer Pulse Dashboard — Setup (Step 1/2)**\n"
                    "> Select a text channel where developer opportunities should be broadcasted:"
                )
            )
            await edit_container_response(interaction, container, view=step1_view)

    @discord.ui.button(label="Disable Feed", style=discord.ButtonStyle.secondary, row=0)
    async def disable_feed(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.stop()
        await self.bot.dev_mgr.disable_feed(self.guild_id)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Developer Pulse Feed Disabled**\n"
                "> Broadcasts have been stopped. Use `/devpulse` anytime to re-enable."
            )
        )
        await edit_container_response(interaction, container, view=None)


class DevPulseCog(commands.Cog):
    """Developer Pulse Autonomous Broadcast and Management Cog."""

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
            logger.error(f"Error in DevPulse background poller: {e}", exc_info=e)

    # -------------------------------------------------------------------------
    # Unified Command
    # -------------------------------------------------------------------------
    @commands.hybrid_command(
        name="devpulse",
        aliases=["dev", "opportunities", "bounties", "devjobs"],
        description="Configure or view the real-time developer opportunities feed (bounties, jobs, hackathons, perks).",
    )
    @commands.has_permissions(manage_guild=True)
    async def devpulse(self, ctx: CustomContext) -> None:
        """Open the Developer Pulse Dashboard."""
        if not ctx.guild:
            await ctx.send("This command can only be used inside a server.")
            return

        cfg = self.bot.dev_mgr.get_guild_config(ctx.guild.id)

        if cfg and cfg.get("channel_id"):
            channel = ctx.guild.get_channel(cfg["channel_id"])
            channel_str = channel.mention if channel else f"<#{cfg['channel_id']}>"
            dot = self.bot.custom_emojis.get("heart_dot", "•")
            sw_on = self.bot.custom_emojis.get("switch_on", "[ON]")

            cats_raw = cfg.get("categories", "all")
            if cats_raw == "all":
                active_labels = [opt["label"] for opt in DEV_MODULE_OPTIONS]
            elif cats_raw == "none":
                active_labels = []
            else:
                active_labels = [
                    opt["label"]
                    for opt in DEV_MODULE_OPTIONS
                    if opt["value"] in cats_raw.split(",")
                ]

            cats_display = f" {dot} ".join(active_labels) if active_labels else "None (Feed Muted)"

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**{sw_on} Developer Pulse Dashboard**\n"
                    f"> **Channel:** {channel_str}\n"
                    f"> **Active Modules:** {cats_display}\n"
                    f"> **Broadcast Frequency:** Real-time Autonomous Stream"
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"> {dot} Verified developer opportunities are streamed into your configured channel.\n"
                f"> {dot} Click **Edit Settings** below to toggle modules or change channel.\n"
                f"> {dot} Click **Disable Feed** to stop opportunity broadcasts."
            )

            view = DevDashboardView(self.bot, ctx.author.id, ctx.guild.id)
            await send_container_response(ctx, container, view=view)
            return

        # Not configured yet -> Launch Step 1
        view = DevSetupChannelView(self.bot, ctx.author.id)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Developer Pulse Dashboard — Setup (Step 1/2)**\n"
                "> Select a text channel where developer opportunities should be broadcasted:"
            )
        )
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    """Standard extension loader entrypoint."""
    await bot.add_cog(DevPulseCog(bot))
