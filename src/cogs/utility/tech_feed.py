"""
Kyro Discord Bot - Tech Intelligence Autonomous Feed Cog
Background ingestion and dispatch engine delivering zero-noise engineering, AI, security, and hardware intel.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

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

VALID_CATEGORIES: set[str] = {"all", "github", "ai", "security", "systems", "hardware", "tech"}

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
        "label": "Security Alerts",
        "value": "security",
        "description": "Zero-day disclosures, critical CVEs & cyber outage advisories",
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
        # Start with all modules active so user can easily toggle off/on individually
        self.active_categories: set[str] = {opt["value"] for opt in MODULE_OPTIONS}

        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()

        # Single-select toggle picker: user selects a module one by one to toggle ON / OFF
        select_options = [
            discord.SelectOption(
                label=opt["label"],
                value=opt["value"],
                description=f"Toggle {opt['label']} ON / OFF",
            )
            for opt in MODULE_OPTIONS
        ]

        self.module_select = discord.ui.Select(
            placeholder="Select a module to toggle ON / OFF...",
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
        """Render container showing module toggle state upar with switch emojis."""
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

        lines = [
            f"**Target Channel:** {self.channel.mention}\n",
            "Select which intelligence modules to stream into this channel. "
            "Use the menu below to toggle modules ON or OFF individually:\n",
        ]

        for opt in MODULE_OPTIONS:
            val = opt["value"]
            lbl = opt["label"]
            is_active = val in self.active_categories
            emoji = sw_on if is_active else sw_off
            status = "**ON**" if is_active else "*OFF*"
            lines.append(f"{emoji} **{lbl}** • {status}")

        container.add_text("\n".join(lines))
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

        formatted_mods = ", ".join(
            CATEGORY_BADGES.get(c, c.title()) for c in self.active_categories
        )

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Tech Dashboard\n"
                f"> Intelligence broadcasting is now active for this server."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"• Target Channel: {self.channel.mention}\n"
            f"• Active Modules: {formatted_mods}\n"
            f"• Broadcast Cadence: Every 15 Minutes (Zero Spam Quality Gate)"
        )
        await edit_container_response(interaction, container, view=None)


class TechStatusView(discord.ui.View):
    """Status panel view with Edit and Disable buttons."""

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


class TechFeedCog(commands.Cog):
    """Autonomous Tech Intelligence feed dispatcher and interactive setup."""
    category: str = "Utility"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self._poller_task.start()

    def cog_unload(self) -> None:
        """Cancel background loop cleanly upon cog unload."""
        self._poller_task.cancel()

    # -------------------------------------------------------------------------
    # Autonomous Background Dispatcher Loop (Every 15 minutes)
    # -------------------------------------------------------------------------
    @tasks.loop(minutes=15)
    async def _poller_task(self) -> None:
        """Background poller harvesting tech intelligence, handling Live streams, Digests, and Critical Alerts."""
        try:
            await self.bot.wait_until_ready()
        except (RuntimeError, Exception):
            return

        guild_configs = self.bot.tech_mgr.get_all_configs()
        if not guild_configs:
            return  # Zero active subscriptions; avoid unnecessary network requests

        try:
            stories = await self.bot.tech_mgr.harvest_all()
            if not stories:
                return

            dot = self.bot.custom_emojis.get("heart_dot", "•")
            now_utc = discord.utils.utcnow()
            today_str = now_utc.strftime("%Y-%m-%d")

            # 1. Handle Morning Digest for guilds configured in 'digest' mode (Trigger at or after 9 AM UTC)
            if now_utc.hour >= 9:
                for guild_id, cfg in list(guild_configs.items()):
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

            # 2. Filter unseen stories for live feeds
            fresh_stories: list[TechStory] = [
                s for s in stories if not self.bot.tech_mgr.is_hash_seen(s.id)
            ]
            if not fresh_stories:
                return

            logger.info(f"Discovered {len(fresh_stories)} new tech intelligence story/stories.")
            dispatched: list[TechStory] = []

            # Prioritize critical threats first, followed by top fresh stories
            critical_items = [s for s in fresh_stories if s.is_critical]
            normal_items = [s for s in fresh_stories if not s.is_critical]
            candidate_batch = (critical_items + normal_items)[:5]

            # Pre-flight health check: Verify candidate URLs live before broadcasting
            batch_to_send: list[TechStory] = []
            connector = aiohttp.TCPConnector(ssl=False)
            timeout = aiohttp.ClientTimeout(total=4)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                for candidate in candidate_batch:
                    if len(batch_to_send) >= 3:
                        break
                    is_alive = await validate_url_live(session, candidate.url)
                    if is_alive:
                        batch_to_send.append(candidate)
                    else:
                        logger.warning(f"Pre-flight check dropped unreachable URL: {candidate.url}")
                        await self.bot.tech_mgr.mark_dispatched([candidate])

            for story in batch_to_send:
                card = self.bot.tech_mgr.build_story_container(story, dot=dot)

                for guild_id, cfg in list(guild_configs.items()):
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        continue

                    # In 'digest' mode, ONLY critical threat alerts are broadcast in real-time
                    if cfg.get("mode") == "digest" and not story.is_critical:
                        continue

                    # Verify category matching
                    allowed_cats = cfg.get("categories", "all").split(",")
                    if "all" not in allowed_cats and story.category not in allowed_cats:
                        continue

                    channel_id = cfg.get("channel_id")
                    channel = guild.get_channel(channel_id)
                    if not isinstance(channel, discord.TextChannel):
                        continue

                    # Priority ping role for critical alerts if configured
                    mention_text = None
                    if story.is_critical and cfg.get("alert_role_id"):
                        mention_text = f"<@&{cfg['alert_role_id']}>"

                    try:
                        msg = await send_container_response(channel, card, content=mention_text)

                        # Auto-create discussion thread if enabled for this guild
                        if cfg.get("thread_enabled") and msg and isinstance(msg, discord.Message):
                            clean_thread_name = f"Discussion: {story.title[:80]}"
                            try:
                                await msg.create_thread(name=clean_thread_name, auto_archive_duration=1440)
                            except Exception as th_err:
                                logger.debug(f"Thread creation notice: {th_err}")
                    except Exception as ch_err:
                        logger.debug(f"Failed to dispatch tech story to guild {guild_id}: {ch_err}")

                dispatched.append(story)

            # Record dispatched stories in memory and PostgreSQL
            if dispatched:
                await self.bot.tech_mgr.mark_dispatched(dispatched)
        except Exception as exc:
            logger.error(f"Unexpected exception in tech news background poller: {exc}", exc_info=exc)

    @_poller_task.before_loop
    async def _before_poller(self) -> None:
        """Wait until the bot gateway is ready before starting the background loop."""
        try:
            await self.bot.wait_until_ready()
        except (RuntimeError, Exception):
            pass

    # -------------------------------------------------------------------------
    # Command Group: tech
    # -------------------------------------------------------------------------
    @commands.hybrid_group(
        name="tech",
        aliases=["technews", "techfeed"],
        description="Autonomous Tech Intelligence terminal & feed setup.",
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def tech(self, ctx: CustomContext) -> None:
        """Interactive 2-step setup: select channel, then select modules."""
        if ctx.author.guild_permissions.manage_guild:
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
            await ctx.invoke(self.status)

    @tech.command(
        name="setup",
        description="Configure tech news broadcasting channel and module filters.",
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def setup_cmd(self, ctx: CustomContext) -> None:
        """Interactive 2-step setup: select channel, then select modules."""
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

    @tech.command(
        name="status",
        aliases=["config", "info"],
        description="View current tech broadcast configuration and settings.",
    )
    @commands.guild_only()
    async def status(self, ctx: CustomContext) -> None:
        """Display the active tech intelligence configuration with Edit & Disable options."""
        cfg = self.bot.tech_mgr.get_config(ctx.guild.id)
        container = KyroContainer(accent_color=None)

        if not cfg:
            container.add_section(
                content=(
                    f"### Tech Dashboard\n"
                    f"> Status: Inactive on this server"
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"Automated tech intelligence broadcasts are currently disabled.\n"
                f"Use the button below or run `{ctx.clean_prefix}tech setup` to activate broadcasting."
            )
            view = TechStatusView(
                bot=self.bot,
                author_id=ctx.author.id,
                guild_id=ctx.guild.id,
                is_active=False,
            )
            await send_container_response(ctx, container, view=view)
            return

        channel = ctx.guild.get_channel(cfg["channel_id"])
        ch_mention = channel.mention if channel else f"Unknown ({cfg['channel_id']})"
        raw_cats = cfg.get("categories", "all").split(",")
        formatted_mods = ", ".join(CATEGORY_BADGES.get(c.strip(), c.strip().title()) for c in raw_cats)

        container.add_section(
            content=(
                f"### Tech Dashboard\n"
                f"> Status: Active & Broadcasting"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"• Target Channel: {ch_mention}\n"
            f"• Active Modules: {formatted_mods}\n"
            f"• Broadcast Cadence: Every 15 Minutes (Zero Spam Quality Gate)"
        )

        view = TechStatusView(
            bot=self.bot,
            author_id=ctx.author.id,
            guild_id=ctx.guild.id,
            is_active=True,
        )
        await send_container_response(ctx, container, view=view)

    @tech.command(
        name="latest",
        aliases=["today", "pulse", "now"],
        description="Fetch fresh top tech stories on demand right now.",
    )
    @app_commands.describe(category="Category: all, github, ai, security, systems, hardware, tech")
    async def latest(self, ctx: CustomContext, category: str = "all") -> None:
        """Instant on-demand intelligence brief."""
        cat_clean = category.strip().lower()
        if cat_clean not in VALID_CATEGORIES:
            cat_clean = "all"

        stories = await self.bot.tech_mgr.fetch_category(cat_clean, limit=2)
        if not stories:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=f"### No Stories Available\n> Could not retrieve fresh stories for {cat_clean} right now."
            )
            await send_container_response(ctx, container)
            return

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        for s in stories:
            card = self.bot.tech_mgr.build_story_container(s, dot=dot)
            await send_container_response(ctx, card)


async def setup(bot: KyroBot) -> None:
    """Register TechFeedCog with KyroBot."""
    await bot.add_cog(TechFeedCog(bot))
