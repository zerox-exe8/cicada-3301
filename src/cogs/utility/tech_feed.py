"""
Kyro Discord Bot - Tech Intelligence Autonomous Feed Cog
Background ingestion and dispatch engine delivering zero-noise engineering, AI, security, and hardware intel.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.core.context import CustomContext
from src.managers.tech_manager import TechStory
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Utility.TechFeed")

VALID_CATEGORIES: set[str] = {"all", "github", "ai", "security", "systems", "hardware"}


class TechFeedCog(commands.Cog):
    """Autonomous Tech Intelligence feed dispatcher and on-demand search."""
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
        """Background poller harvesting fresh tech intelligence and broadcasting to subscribed channels."""
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

            # Filter unseen stories
            fresh_stories: list[TechStory] = [
                s for s in stories if not self.bot.tech_mgr.is_hash_seen(s.id)
            ]
            if not fresh_stories:
                return

            logger.info(f"Discovered {len(fresh_stories)} new tech intelligence story/stories.")

            dot = self.bot.custom_emojis.get("heart_dot", "•")
            dispatched: list[TechStory] = []

            # Staggered delivery: post top 3 freshest stories per cycle to prevent channel spam
            for story in fresh_stories[:3]:
                card = self.bot.tech_mgr.build_story_container(story, dot=dot)

                for guild_id, cfg in list(guild_configs.items()):
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        continue

                    # Verify category matching
                    allowed_cats = cfg.get("categories", "all").split(",")
                    if "all" not in allowed_cats and story.category not in allowed_cats:
                        continue

                    channel_id = cfg.get("channel_id")
                    channel = guild.get_channel(channel_id)
                    if not isinstance(channel, discord.TextChannel):
                        continue

                    try:
                        msg = await send_container_response(channel, card)

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
    # Command Group: technews
    # -------------------------------------------------------------------------
    @commands.hybrid_group(
        name="technews",
        aliases=["techfeed", "techintel", "intel"],
        description="Autonomous Tech Intelligence terminal and real-time feeds.",
        invoke_without_command=True,
    )
    async def technews(self, ctx: CustomContext) -> None:
        """Default view showing tech intelligence capabilities and status."""
        await ctx.invoke(self.status)

    @technews.command(
        name="set",
        aliases=["channel"],
        description="Bind a channel for autonomous real-time tech news updates.",
    )
    @app_commands.describe(
        channel="The text channel where tech intelligence will be broadcast",
        categories="Category filter: all, github, ai, security, systems, hardware (default: all)",
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def set_channel(
        self,
        ctx: CustomContext,
        channel: discord.TextChannel,
        categories: str = "all",
    ) -> None:
        """Set up automated tech news broadcasting in a designated channel."""
        cat_clean = categories.strip().lower()
        cat_list = [c.strip() for c in cat_clean.split(",") if c.strip()]
        for c in cat_list:
            if c not in VALID_CATEGORIES:
                container = KyroContainer(accent_color=0xFF3333)
                container.add_section(
                    content=(
                        f"**Invalid Category: `{c}`**\n"
                        f"> Supported: `all`, `github`, `ai`, `security`, `systems`, `hardware`\n"
                        f"> Example: `{ctx.clean_prefix}technews set #{channel.name} ai,github`"
                    )
                )
                await send_container_response(ctx, container)
                return

        bot_perms = channel.permissions_for(ctx.guild.me)
        if not (bot_perms.send_messages and bot_perms.embed_links):
            container = KyroContainer(accent_color=0xFF3333)
            container.add_section(
                content=f"**Missing Permissions**\n> I require `Send Messages` and `Embed Links` in {channel.mention}."
            )
            await send_container_response(ctx, container)
            return

        success = await self.bot.tech_mgr.set_channel(
            guild_id=ctx.guild.id,
            channel_id=channel.id,
            categories=",".join(cat_list),
            thread_enabled=False,
        )

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        if success:
            container = KyroContainer(accent_color=0x00FF66)
            container.add_section(
                content=(
                    f"**Tech Intelligence Feed Activated**\n"
                    f"> Real-time intelligence will now be broadcast to {channel.mention}."
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} **Channel:** {channel.mention} (`{channel.id}`)\n"
                f"{dot} **Subscribed Fields:** `{', '.join(cat_list).upper()}`\n"
                f"{dot} **Discussion Threads:** `Disabled` (Enable via `{ctx.clean_prefix}technews thread on`)\n"
                f"{dot} **Cadence:** `Every 15 Minutes (Zero-Spam Quality Gate)`"
            )
            container.add_separator(divider=True)
            container.add_text("-# Kyro Tech Sentinel • Autonomous Terminal")
            await send_container_response(ctx, container)
        else:
            container = KyroContainer(accent_color=0xFF3333)
            container.add_section(content="**Database Error**\n> Failed to persist tech news configuration.")
            await send_container_response(ctx, container)

    @technews.command(
        name="disable",
        aliases=["off", "stop", "remove"],
        description="Disable automated tech news broadcasts in this server.",
    )
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def disable(self, ctx: CustomContext) -> None:
        """Stop and unbind the automated tech feed."""
        existing = self.bot.tech_mgr.get_config(ctx.guild.id)
        if not existing:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**No Active Feed**\n> Tech news is not currently configured on this server.")
            await send_container_response(ctx, container)
            return

        await self.bot.tech_mgr.remove_channel(ctx.guild.id)
        container = KyroContainer(accent_color=0x00FF66)
        container.add_section(
            content=(
                f"**Tech Intelligence Feed Disabled**\n"
                f"> Automated broadcasts have been deactivated for this server."
            )
        )
        await send_container_response(ctx, container)

    @technews.command(
        name="thread",
        description="Toggle auto-creation of discussion threads under each news drop.",
    )
    @app_commands.describe(state="Enable or disable threads (on/off)")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def thread(self, ctx: CustomContext, state: str) -> None:
        """Toggle automatic discussion threads for each dispatched news card."""
        cfg = self.bot.tech_mgr.get_config(ctx.guild.id)
        if not cfg:
            container = KyroContainer(accent_color=0xFF3333)
            container.add_section(
                content=f"**No Active Feed**\n> Set up a channel first using `{ctx.clean_prefix}technews set #channel`."
            )
            await send_container_response(ctx, container)
            return

        enable = state.strip().lower() in {"on", "true", "enable", "yes"}
        await self.bot.tech_mgr.set_channel(
            guild_id=ctx.guild.id,
            channel_id=cfg["channel_id"],
            categories=cfg["categories"],
            thread_enabled=enable,
        )

        state_str = "Enabled" if enable else "Disabled"
        container = KyroContainer(accent_color=0x00FF66)
        container.add_section(
            content=(
                f"**Discussion Threads {state_str}**\n"
                f"> New tech dispatches will {'now automatically attach' if enable else 'no longer create'} discussion threads."
            )
        )
        await send_container_response(ctx, container)

    @technews.command(
        name="latest",
        aliases=["today", "pulse", "now"],
        description="Fetch fresh top tech stories on demand right now.",
    )
    @app_commands.describe(category="Category: all, github, ai, security, systems, hardware (default: all)")
    async def latest(self, ctx: CustomContext, category: str = "all") -> None:
        """Instant on-demand intelligence brief."""
        cat_clean = category.strip().lower()
        if cat_clean not in VALID_CATEGORIES:
            cat_clean = "all"

        # Temporary loading response
        stories = await self.bot.tech_mgr.fetch_category(cat_clean, limit=2)
        if not stories:
            container = KyroContainer(accent_color=0xFFA500)
            container.add_section(
                content=f"**No Active Stories Found**\n> Could not retrieve fresh stories for `{cat_clean}` right now."
            )
            await send_container_response(ctx, container)
            return

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        for s in stories:
            card = self.bot.tech_mgr.build_story_container(s, dot=dot)
            await send_container_response(ctx, card)

    @technews.command(
        name="status",
        aliases=["config", "info"],
        description="View the current server tech news configuration.",
    )
    @commands.guild_only()
    async def status(self, ctx: CustomContext) -> None:
        """Display the active tech intelligence configuration."""
        cfg = self.bot.tech_mgr.get_config(ctx.guild.id)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        if not cfg:
            container.add_section(
                content=(
                    f"**Tech Intelligence Terminal**\n"
                    f"> Status: `Inactive on this server`\n\n"
                    f"{dot} **Setup Command:** `{ctx.clean_prefix}technews set #channel [category]`\n"
                    f"{dot} **Supported Fields:** `GitHub Trending`, `AI Research`, `Security CVEs`, `Linux Kernel`, `Systems`\n"
                    f"{dot} **Instant Query:** `{ctx.clean_prefix}technews latest`"
                )
            )
        else:
            channel = ctx.guild.get_channel(cfg["channel_id"])
            ch_mention = channel.mention if channel else f"`Unknown ({cfg['channel_id']})`"
            th_str = "Enabled" if cfg.get("thread_enabled") else "Disabled"

            container.add_section(
                content=(
                    f"**Tech Intelligence Terminal**\n"
                    f"> Status: `Active & Broadcasting`"
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} **Target Channel:** {ch_mention}\n"
                f"{dot} **Categories:** `{cfg['categories'].upper()}`\n"
                f"{dot} **Auto-Threads:** `{th_str}`\n"
                f"{dot} **Cadence:** `Every 15 Minutes (Zero-Spam Curated)`"
            )

        container.add_separator(divider=True)
        container.add_text("-# Kyro Tech Intelligence • Enterprise Radar")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Register TechFeedCog with KyroBot."""
    await bot.add_cog(TechFeedCog(bot))
