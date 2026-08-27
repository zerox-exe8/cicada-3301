"""
Cicada 3301 Discord Bot - Server Auto-Events (Welcome, Leave, Boost) Cog
Binds saved named Components V2 container cards and outer ping messages with dynamic variables
to member join, member leave, and server boost events.
"""

from __future__ import annotations

import logging
import re
from typing import Any
import discord
from discord.ext import commands

from src.core.bot import CicadaBot
from src.core.context import CustomContext
from src.cogs.utility.embed_builder import ContainerDraft
from src.utils.containers import CicadaContainer, send_container_response
from src.utils.placeholders import resolve_placeholders

logger = logging.getLogger("Cicada.Events")


class AutoEvents(commands.Cog):
    """Automated Welcome, Farewell/Leave, and Boost Container Dispatcher."""
    category: str = "Utility"

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot

    async def _send_event_card(
        self,
        event_type: str,
        guild: discord.Guild,
        member: discord.Member | discord.User,
        extra: dict[str, Any] | None = None,
        test_channel: discord.TextChannel | None = None,
    ) -> bool:
        """Helper to render and dispatch an event container card + outer message."""
        config = await self.bot.event_mgr.get_event_config(guild.id, event_type)
        if not config and not test_channel:
            return False

        if not test_channel and not config.get("is_enabled", True):
            return False

        channel_id = test_channel.id if test_channel else config.get("channel_id")
        if not channel_id:
            return False

        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return False

        # Permissions check
        perms = channel.permissions_for(guild.me)
        if not perms.send_messages:
            logger.warning(f"Missing send_messages perms in #{channel.name} ({guild.name}) for {event_type}")
            return False

        embed_name = config.get("embed_name") if config else None
        msg_template = config.get("message_content") if config else None

        # 1. Resolve Outer Message Content (Ping message)
        outer_content = None
        if msg_template:
            outer_content = resolve_placeholders(msg_template, user=member, guild=guild, extra=extra)

        # 2. Build Container from saved embed or fallback container
        container = None
        if embed_name:
            template_data = await self.bot.embed_mgr.get_template(guild.id, embed_name)
            if template_data:
                draft = ContainerDraft.from_dict(template_data)
                avatar_url = str(self.bot.user.display_avatar.url) if self.bot and self.bot.user else ""
                container = draft.to_container(
                    user=member,
                    guild=guild,
                    channel=channel,
                    bot=self.bot,
                    default_avatar=avatar_url,
                )

        if not container and not outer_content:
            # Basic fallback if no embed is bound
            container = CicadaContainer(accent_color=None)
            if event_type == "welcome":
                container.add_section(
                    content=(
                        f"**Welcome to {guild.name}!**\n"
                        f"> Hey {member.mention}, welcome to the server!\n"
                        f"> You are our **{guild.member_count:,}th** member."
                    )
                )
            elif event_type == "leave":
                container.add_section(
                    content=(
                        f"**Goodbye!**\n"
                        f"> **{member.name}** has left **{guild.name}**.\n"
                        f"> We now have **{guild.member_count:,}** members."
                    )
                )
            elif event_type == "boost":
                container.add_section(
                    content=(
                        f"**Server Boost!**\n"
                        f"> Thank you {member.mention} for boosting **{guild.name}**!\n"
                        f"> We are now at **{guild.premium_subscription_count}** boosts ({guild.premium_tier})."
                    )
                )
            container.add_separator(divider=True)
            container.add_text(f"-# {guild.name}")

        try:
            target_msg = await send_container_response(
                channel,
                container if container else CicadaContainer(),
                content=outer_content,
            )
            # If template has interactive modules, register card for page switching
            msg_id = None
            if isinstance(target_msg, dict) and "id" in target_msg:
                msg_id = int(target_msg["id"])
            elif hasattr(target_msg, "id"):
                msg_id = int(target_msg.id)

            if container and embed_name and msg_id:
                draft_data = await self.bot.embed_mgr.get_template(guild.id, embed_name)
                if draft_data:
                    await self.bot.embed_mgr.record_interactive_card(
                        guild_id=guild.id,
                        message_id=msg_id,
                        template_name=embed_name,
                        payload=draft_data,
                    )
            return True
        except Exception as e:
            logger.error(f"Failed to dispatch {event_type} card in {guild.name}: {e}", exc_info=e)
            return False

    # ─── Event Listeners ─────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Handle welcome greeting on member join."""
        if member.bot:
            return
        await self._send_event_card("welcome", member.guild, member)

        # Handle DM Welcome if enabled
        config = await self.bot.event_mgr.get_event_config(member.guild.id, "welcome")
        if config and config.get("dm_enabled") and config.get("dm_embed_name"):
            dm_name = config["dm_embed_name"]
            dm_data = await self.bot.embed_mgr.get_template(member.guild.id, dm_name)
            if dm_data:
                try:
                    draft = ContainerDraft.from_dict(dm_data)
                    avatar_url = str(self.bot.user.display_avatar.url) if self.bot and self.bot.user else ""
                    dm_container = draft.to_container(
                        user=member,
                        guild=member.guild,
                        bot=self.bot,
                        default_avatar=avatar_url,
                    )
                    await send_container_response(member, dm_container)
                except Exception:
                    pass  # User DMs closed

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Handle farewell on member leave."""
        if member.bot:
            return
        await self._send_event_card("leave", member.guild, member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Handle server boost event."""
        if not before.premium_since and after.premium_since:
            extra = {
                "booster": after.mention,
                "boost_count": getattr(after.guild, "premium_subscription_count", 0),
                "boost_tier": f"Level {getattr(after.guild, 'premium_tier', 0)}",
            }
            await self._send_event_card("boost", after.guild, after, extra=extra)

    # ─── Welcome Command Group ───────────────────────────────────────────────

    @commands.hybrid_group(
        name="welcome",
        aliases=["greet"],
        description="Configure automated server welcome container cards.",
        fallback="status",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_group(self, ctx: CustomContext) -> None:
        """View the current welcome configuration dashboard."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "welcome")

        ch_id = config.get("channel_id") if config else None
        channel = ctx.guild.get_channel(ch_id) if ch_id else None
        ch_str = channel.mention if channel else "`Not Configured`"
        emb_str = f"`{config.get('embed_name')}`" if (config and config.get("embed_name")) else "`Default Card`"
        msg_str = f"`{config.get('message_content')}`" if (config and config.get("message_content")) else "`None (Embed Only)`"
        status_str = "`Enabled`" if (config and config.get("is_enabled", True)) else "`Disabled`"
        dm_str = f"`{config.get('dm_embed_name')}`" if (config and config.get("dm_enabled")) else "`Disabled`"

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Welcome Configuration**\n"
                f"> Manage automated welcome messages & container cards for **{ctx.guild.name}**."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"**Channel:** {ch_str} | **Status:** {status_str}\n"
            f"**Bound Embed:** {emb_str} | **DM Welcome:** {dm_str}\n"
            f"**Outer Ping Text:** {msg_str}"
        )
        container.add_separator(divider=True)
        container.add_text(
            f"`{prefix}welcome set #channel {{user}} <embed_name>`\n"
            f"`{prefix}welcome test` , `{prefix}welcome toggle` , `{prefix}welcome reset`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @welcome_group.command(
        name="set",
        description="Bind channel, outer text, and custom embed for welcome messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_set(
        self,
        ctx: CustomContext,
        *,
        args: str = "",
    ) -> None:
        """Bind channel, message content, and named embed template."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        raw_text = args.strip()

        target_channel = None
        if ctx.message.channel_mentions:
            target_channel = ctx.message.channel_mentions[0]
            raw_text = re.sub(rf"<#{target_channel.id}>", "", raw_text).strip()
        else:
            words = raw_text.split()
            if words:
                first_w = words[0].lstrip("#")
                if first_w.isdigit():
                    ch = ctx.guild.get_channel(int(first_w))
                    if isinstance(ch, discord.TextChannel):
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()
                if not target_channel:
                    ch = discord.utils.get(ctx.guild.text_channels, name=first_w.lower())
                    if ch:
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()

        if not target_channel:
            target_channel = ctx.channel

        words = raw_text.split()
        embed_name = None
        message_content = None

        if len(words) == 1:
            clean_word = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
            template = await self.bot.embed_mgr.get_template(ctx.guild.id, clean_word)
            if template:
                embed_name = clean_word
            else:
                message_content = raw_text
        elif len(words) > 1:
            last_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[-1].lower())
            template_last = await self.bot.embed_mgr.get_template(ctx.guild.id, last_clean)
            if template_last:
                embed_name = last_clean
                message_content = raw_text[:-len(words[-1])].strip() or None
            else:
                first_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
                template_first = await self.bot.embed_mgr.get_template(ctx.guild.id, first_clean)
                if template_first:
                    embed_name = first_clean
                    message_content = raw_text[len(words[0]):].strip() or None
                else:
                    message_content = raw_text

        success = await self.bot.event_mgr.save_event_config(
            guild_id=ctx.guild.id,
            event_type="welcome",
            channel_id=target_channel.id,
            embed_name=embed_name,
            message_content=message_content,
            is_enabled=True,
        )

        if not success:
            await ctx.send("Failed to save welcome configuration. Please try again.")
            return

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Welcome System Configured**\n"
                f"> New members will be greeted in {target_channel.mention}."
            )
        )
        container.add_separator(divider=True)
        emb_display = f"`{embed_name}`" if embed_name else "`Default Card`"
        msg_display = f"`{message_content}`" if message_content else "`None (Embed Only)`"
        container.add_text(
            f"**Channel:** {target_channel.mention}\n"
            f"**Bound Embed:** {emb_display}\n"
            f"**Outer Text:** {msg_display}\n\n"
            f"> Run `{prefix}welcome test` to preview the message live!"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @welcome_group.command(
        name="test",
        description="Test the current welcome message and embed live in channel.",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_test(self, ctx: CustomContext) -> None:
        """Send a test welcome card."""
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "welcome")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not config or not config.get("channel_id"):
            await ctx.send(f"Welcome is not configured yet! Use `{prefix}welcome set #channel {{user}} <embed_name>`.")
            return

        target_ch = ctx.guild.get_channel(config["channel_id"])
        if not target_ch or not isinstance(target_ch, discord.TextChannel):
            await ctx.send(f"Configured welcome channel not found. Please set a new channel with `{prefix}welcome set`.")
            return

        sent = await self._send_event_card("welcome", ctx.guild, ctx.author, test_channel=target_ch)
        if sent:
            await ctx.send(f"Test welcome card dispatched to {target_ch.mention}!")
        else:
            await ctx.send(f"Failed to dispatch test card. Check bot permissions in {target_ch.mention}.")

    @welcome_group.command(
        name="toggle",
        description="Enable or disable the welcome message.",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_toggle(self, ctx: CustomContext) -> None:
        """Toggle welcome event on/off."""
        res = await self.bot.event_mgr.toggle_event(ctx.guild.id, "welcome")
        if res is None:
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            await ctx.send(f"No welcome configuration found. Set it up using `{prefix}welcome set`.")
            return

        state = "Enabled" if res else "Disabled"
        await ctx.send(f"Welcome event has been **{state}**.")

    @welcome_group.command(
        name="reset",
        aliases=["clear", "delete"],
        description="Reset and disable welcome messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_reset(self, ctx: CustomContext) -> None:
        """Clear welcome configuration."""
        await self.bot.event_mgr.delete_event_config(ctx.guild.id, "welcome")
        await ctx.send("Welcome event configuration has been reset.")

    # ─── Leave / Goodbye Command Group ───────────────────────────────────────

    @commands.hybrid_group(
        name="leave",
        aliases=["goodbye", "farewell"],
        description="Configure automated server leave / goodbye container cards.",
        fallback="status",
    )
    @commands.has_permissions(manage_guild=True)
    async def leave_group(self, ctx: CustomContext) -> None:
        """View the current leave configuration dashboard."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "leave")

        ch_id = config.get("channel_id") if config else None
        channel = ctx.guild.get_channel(ch_id) if ch_id else None
        ch_str = channel.mention if channel else "`Not Configured`"
        emb_str = f"`{config.get('embed_name')}`" if (config and config.get("embed_name")) else "`Default Card`"
        msg_str = f"`{config.get('message_content')}`" if (config and config.get("message_content")) else "`None (Embed Only)`"
        status_str = "`Enabled`" if (config and config.get("is_enabled", True)) else "`Disabled`"

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Leave / Goodbye Configuration**\n"
                f"> Manage automated departure cards for **{ctx.guild.name}**."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"**Channel:** {ch_str} | **Status:** {status_str}\n"
            f"**Bound Embed:** {emb_str}\n"
            f"**Outer Text:** {msg_str}"
        )
        container.add_separator(divider=True)
        container.add_text(
            f"`{prefix}leave set #channel {{user.name}} <embed_name>`\n"
            f"`{prefix}leave test` , `{prefix}leave toggle` , `{prefix}leave reset`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @leave_group.command(
        name="set",
        description="Bind channel, outer text, and custom embed for departure messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def leave_set(
        self,
        ctx: CustomContext,
        *,
        args: str = "",
    ) -> None:
        """Bind leave channel, message content, and named embed template."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        raw_text = args.strip()

        target_channel = None
        if ctx.message.channel_mentions:
            target_channel = ctx.message.channel_mentions[0]
            raw_text = re.sub(rf"<#{target_channel.id}>", "", raw_text).strip()
        else:
            words = raw_text.split()
            if words:
                first_w = words[0].lstrip("#")
                if first_w.isdigit():
                    ch = ctx.guild.get_channel(int(first_w))
                    if isinstance(ch, discord.TextChannel):
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()
                if not target_channel:
                    ch = discord.utils.get(ctx.guild.text_channels, name=first_w.lower())
                    if ch:
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()

        if not target_channel:
            target_channel = ctx.channel

        words = raw_text.split()
        embed_name = None
        message_content = None

        if len(words) == 1:
            clean_word = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
            template = await self.bot.embed_mgr.get_template(ctx.guild.id, clean_word)
            if template:
                embed_name = clean_word
            else:
                message_content = raw_text
        elif len(words) > 1:
            last_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[-1].lower())
            template_last = await self.bot.embed_mgr.get_template(ctx.guild.id, last_clean)
            if template_last:
                embed_name = last_clean
                message_content = raw_text[:-len(words[-1])].strip() or None
            else:
                first_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
                template_first = await self.bot.embed_mgr.get_template(ctx.guild.id, first_clean)
                if template_first:
                    embed_name = first_clean
                    message_content = raw_text[len(words[0]):].strip() or None
                else:
                    message_content = raw_text

        success = await self.bot.event_mgr.save_event_config(
            guild_id=ctx.guild.id,
            event_type="leave",
            channel_id=target_channel.id,
            embed_name=embed_name,
            message_content=message_content,
            is_enabled=True,
        )

        if not success:
            await ctx.send("Failed to save leave configuration.")
            return

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Leave System Configured**\n"
                f"> Departure messages will be posted in {target_channel.mention}."
            )
        )
        container.add_separator(divider=True)
        emb_display = f"`{embed_name}`" if embed_name else "`Default Card`"
        msg_display = f"`{message_content}`" if message_content else "`None (Embed Only)`"
        container.add_text(
            f"**Channel:** {target_channel.mention}\n"
            f"**Bound Embed:** {emb_display}\n"
            f"**Outer Text:** {msg_display}\n\n"
            f"> Run `{prefix}leave test` to preview the message live!"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @leave_group.command(
        name="test",
        description="Test the current leave message live in channel.",
    )
    @commands.has_permissions(manage_guild=True)
    async def leave_test(self, ctx: CustomContext) -> None:
        """Send a test leave card."""
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "leave")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not config or not config.get("channel_id"):
            await ctx.send(f"Leave is not configured yet! Use `{prefix}leave set #channel {{user.name}} <embed_name>`.")
            return

        target_ch = ctx.guild.get_channel(config["channel_id"])
        if not target_ch or not isinstance(target_ch, discord.TextChannel):
            await ctx.send(f"Configured leave channel not found. Set a new channel with `{prefix}leave set`.")
            return

        sent = await self._send_event_card("leave", ctx.guild, ctx.author, test_channel=target_ch)
        if sent:
            await ctx.send(f"Test leave card dispatched to {target_ch.mention}!")
        else:
            await ctx.send(f"Failed to dispatch test card. Check permissions in {target_ch.mention}.")

    @leave_group.command(
        name="toggle",
        description="Enable or disable leave messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def leave_toggle(self, ctx: CustomContext) -> None:
        """Toggle leave event on/off."""
        res = await self.bot.event_mgr.toggle_event(ctx.guild.id, "leave")
        if res is None:
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            await ctx.send(f"No leave configuration found. Set it up using `{prefix}leave set`.")
            return

        state = "Enabled" if res else "Disabled"
        await ctx.send(f"Leave event has been **{state}**.")

    @leave_group.command(
        name="reset",
        aliases=["clear", "delete"],
        description="Reset and disable leave messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def leave_reset(self, ctx: CustomContext) -> None:
        """Clear leave configuration."""
        await self.bot.event_mgr.delete_event_config(ctx.guild.id, "leave")
        await ctx.send("Leave event configuration has been reset.")

    # ─── Boost Command Group ─────────────────────────────────────────────────

    @commands.hybrid_group(
        name="boost",
        description="Configure automated server boost celebration container cards.",
        fallback="status",
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_group(self, ctx: CustomContext) -> None:
        """View the current boost configuration dashboard."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "boost")

        ch_id = config.get("channel_id") if config else None
        channel = ctx.guild.get_channel(ch_id) if ch_id else None
        ch_str = channel.mention if channel else "`Not Configured`"
        emb_str = f"`{config.get('embed_name')}`" if (config and config.get("embed_name")) else "`Default Card`"
        msg_str = f"`{config.get('message_content')}`" if (config and config.get("message_content")) else "`None (Embed Only)`"
        status_str = "`Enabled`" if (config and config.get("is_enabled", True)) else "`Disabled`"

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Server Boost Celebration Configuration**\n"
                f"> Manage automated boost announcements for **{ctx.guild.name}**."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"**Channel:** {ch_str} | **Status:** {status_str}\n"
            f"**Bound Embed:** {emb_str}\n"
            f"**Outer Text:** {msg_str}"
        )
        container.add_separator(divider=True)
        container.add_text(
            f"`{prefix}boost set #channel {{user}} <embed_name>`\n"
            f"`{prefix}boost test` , `{prefix}boost toggle` , `{prefix}boost reset`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @boost_group.command(
        name="set",
        description="Bind channel, outer text, and custom embed for boost announcements.",
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_set(
        self,
        ctx: CustomContext,
        *,
        args: str = "",
    ) -> None:
        """Bind boost channel, message content, and named embed template."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        raw_text = args.strip()

        target_channel = None
        if ctx.message.channel_mentions:
            target_channel = ctx.message.channel_mentions[0]
            raw_text = re.sub(rf"<#{target_channel.id}>", "", raw_text).strip()
        else:
            words = raw_text.split()
            if words:
                first_w = words[0].lstrip("#")
                if first_w.isdigit():
                    ch = ctx.guild.get_channel(int(first_w))
                    if isinstance(ch, discord.TextChannel):
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()
                if not target_channel:
                    ch = discord.utils.get(ctx.guild.text_channels, name=first_w.lower())
                    if ch:
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()

        if not target_channel:
            target_channel = ctx.channel

        words = raw_text.split()
        embed_name = None
        message_content = None

        if len(words) == 1:
            clean_word = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
            template = await self.bot.embed_mgr.get_template(ctx.guild.id, clean_word)
            if template:
                embed_name = clean_word
            else:
                message_content = raw_text
        elif len(words) > 1:
            last_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[-1].lower())
            template_last = await self.bot.embed_mgr.get_template(ctx.guild.id, last_clean)
            if template_last:
                embed_name = last_clean
                message_content = raw_text[:-len(words[-1])].strip() or None
            else:
                first_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
                template_first = await self.bot.embed_mgr.get_template(ctx.guild.id, first_clean)
                if template_first:
                    embed_name = first_clean
                    message_content = raw_text[len(words[0]):].strip() or None
                else:
                    message_content = raw_text

        success = await self.bot.event_mgr.save_event_config(
            guild_id=ctx.guild.id,
            event_type="boost",
            channel_id=target_channel.id,
            embed_name=embed_name,
            message_content=message_content,
            is_enabled=True,
        )

        if not success:
            await ctx.send("Failed to save boost configuration.")
            return

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Boost Celebration System Configured**\n"
                f"> Boost announcements will be posted in {target_channel.mention}."
            )
        )
        container.add_separator(divider=True)
        emb_display = f"`{embed_name}`" if embed_name else "`Default Card`"
        msg_display = f"`{message_content}`" if message_content else "`None (Embed Only)`"
        container.add_text(
            f"**Channel:** {target_channel.mention}\n"
            f"**Bound Embed:** {emb_display}\n"
            f"**Outer Text:** {msg_display}\n\n"
            f"> Run `{prefix}boost test` to preview the message live!"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @boost_group.command(
        name="test",
        description="Test the boost celebration message live in channel.",
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_test(self, ctx: CustomContext) -> None:
        """Send a test boost celebration card."""
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "boost")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not config or not config.get("channel_id"):
            await ctx.send(f"Boost is not configured yet! Use `{prefix}boost set #channel {{user}} <embed_name>`.")
            return

        target_ch = ctx.guild.get_channel(config["channel_id"])
        if not target_ch or not isinstance(target_ch, discord.TextChannel):
            await ctx.send(f"Configured boost channel not found. Set a new channel with `{prefix}boost set`.")
            return

        extra = {
            "booster": ctx.author.mention,
            "boost_count": getattr(ctx.guild, "premium_subscription_count", 1),
            "boost_tier": f"Level {getattr(ctx.guild, 'premium_tier', 1)}",
        }
        sent = await self._send_event_card("boost", ctx.guild, ctx.author, extra=extra, test_channel=target_ch)
        if sent:
            await ctx.send(f"Test boost card dispatched to {target_ch.mention}!")
        else:
            await ctx.send(f"Failed to dispatch test card. Check permissions in {target_ch.mention}.")

    @boost_group.command(
        name="toggle",
        description="Enable or disable boost celebration messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_toggle(self, ctx: CustomContext) -> None:
        """Toggle boost event on/off."""
        res = await self.bot.event_mgr.toggle_event(ctx.guild.id, "boost")
        if res is None:
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            await ctx.send(f"No boost configuration found. Set it up using `{prefix}boost set`.")
            return

        state = "Enabled" if res else "Disabled"
        await ctx.send(f"Boost event has been **{state}**.")

    @boost_group.command(
        name="reset",
        aliases=["clear", "delete"],
        description="Reset and disable boost messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_reset(self, ctx: CustomContext) -> None:
        """Clear boost configuration."""
        await self.bot.event_mgr.delete_event_config(ctx.guild.id, "boost")
        await ctx.send("Boost event configuration has been reset.")


async def setup(bot: CicadaBot) -> None:
    await bot.add_cog(AutoEvents(bot))
