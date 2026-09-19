"""
Kyro Discord Bot - Tech Intelligence Autonomous Feed Cog
Background ingestion and dispatch engine delivering zero-noise engineering, AI, security, and hardware intel.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from datetime import datetime, timezone
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

        top_lines = [
            f"**Channel:** {self.channel.mention}  {dot}  **Cadence:** `Every 15m`  {dot}  **Status:** `Active`"
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

            self.health_button = discord.ui.Button(
                label="Cloud Health",
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            self.health_button.callback = self._on_health_check
            self.add_item(self.health_button)
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

    # -------------------------------------------------------------------------
    # Autonomous Background Dispatcher Loop (Hourly Batch: 10 Items, 1m Delay)
    # -------------------------------------------------------------------------
    @tasks.loop(hours=1)
    async def _poller_task(self) -> None:
        """Background poller harvesting a balanced 10-item tech intelligence batch and dispatching with 1-minute pacing."""
        try:
            await self.bot.wait_until_ready()
        except (RuntimeError, Exception):
            return

        guild_configs = self.bot.tech_mgr.get_all_configs()
        if not guild_configs:
            return  # Zero active subscriptions; avoid unnecessary network requests

        if self._is_dispatching:
            return

        self._is_dispatching = True
        try:
            # 1. Harvest balanced batch of up to 10 top-signal items across all categories
            stories = await self.bot.tech_mgr.harvest_balanced_batch(target_total=10)
            if not stories:
                return

            dot = self.bot.custom_emojis.get("heart_dot", "•")
            now_utc = discord.utils.utcnow()
            today_str = now_utc.strftime("%Y-%m-%d")

            # 2. Handle Morning Digest for guilds configured in 'digest' mode (Trigger at or after 9 AM UTC)
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

            logger.info(f"Dispatching batch of {len(batch_to_send)} balanced tech story/stories with 60s pacing delay.")

            # 4. Dispatch 10 items one by one with strict 1-minute (60s) delay between each post
            for index, story in enumerate(batch_to_send):
                card = self.bot.tech_mgr.build_story_container(story, dot=dot)
                dispatched_any = False

                for guild_id, cfg in list(guild_configs.items()):
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

                # Exactly 1 minute (60 seconds) delay between each of the 10 posts
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
            channel = ctx.guild.get_channel(cfg["channel_id"])
            ch_mention = channel.mention if channel else f"Unknown ({cfg['channel_id']})"
            raw_cats = {c.strip() for c in cfg.get("categories", "all").split(",")}

            sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
            sw_off = self.bot.custom_emojis.get("icon_switch_off", "[OFF]")
            dot = self.bot.custom_emojis.get("heart_dot", "•")

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"### Tech Dashboard\n"
                    f"> Status: Active & Broadcasting"
                )
            )
            container.add_separator(divider=True)

            health = await self.bot.tech_realtime_mgr.get_global_health_summary()
            health_summary_parts = [f"{prov} `{stat}`" for prov, stat in health.items()]
            health_line = f"**Cloud Health:** " + f"  {dot}  ".join(health_summary_parts)

            top_lines = [
                f"**Channel:** {ch_mention}  {dot}  **Cadence:** `Hourly Batch (10 Items • 1m Delay)`  {dot}  **Status:** `Active`",
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
