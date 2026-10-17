from __future__ import annotations

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Optional
import urllib.parse

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import dispatch_mod_log
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.Media")

MEDIA_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm",
    ".mov", ".mkv", ".mp3", ".wav", ".ogg", ".m4a", ".flac"
)

MEDIA_DOMAINS = (
    "tenor.com",
    "giphy.com",
    "imgur.com",
    "instagram.com/reel",
    "instagram.com/p",
    "tiktok.com",
    "youtube.com/shorts",
    "youtu.be",
    "youtube.com/watch",
    "cdn.discordapp.com",
    "media.discordapp.net",
    "prnt.sc",
    "streamable.com",
    "pinterest.com/pin",
    "pinterest.com",
    "reddit.com/gallery",
    "i.redd.it",
    "v.redd.it",
)

URL_REGEX = re.compile(
    r"https?://(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s]*)?",
    re.IGNORECASE,
)


class MediaChannels(commands.Cog):
    """Media-only channels system: strictly confines configured channels to media content."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    def _contains_media(self, message: discord.Message) -> bool:
        """Analyze message attachments and embedded links for media formats."""
        # 1. Direct attachments
        if message.attachments:
            return True

        # 2. Check for URLs in message content
        urls = URL_REGEX.findall(message.content)
        if not urls:
            return False

        for url_str in urls:
            parsed = urllib.parse.urlparse(url_str)
            path = parsed.path.lower()
            full_url = url_str.lower()

            # Direct file extensions
            if any(path.endswith(ext) for ext in MEDIA_EXTENSIONS):
                return True

            # Trusted media hostnames or specific path patterns
            if any(dom in full_url for dom in MEDIA_DOMAINS):
                return True

        return False

    def extract_channels(self, ctx: CustomContext, fallback: Optional[discord.TextChannel] = None) -> list[discord.TextChannel]:
        """
        Extract all targeted text channels from context.
        Supports single or multiple channel mentions (#ch1 #ch2), raw IDs, or fallback.
        """
        targets: list[discord.TextChannel] = []
        seen_ids: set[int] = set()

        # 1. From message mentions if prefix command
        if ctx.message and ctx.message.channel_mentions:
            for ch in ctx.message.channel_mentions:
                if isinstance(ch, discord.TextChannel) and ch.id not in seen_ids:
                    targets.append(ch)
                    seen_ids.add(ch.id)

        # 2. From raw IDs/tokens in message content (e.g. .media setup 123456789 987654321)
        if ctx.message and ctx.message.content:
            tokens = ctx.message.content.split()[2:]
            for tok in tokens:
                clean = tok.strip("<#>").strip()
                if clean.isdigit():
                    ch = ctx.guild.get_channel(int(clean))
                    if isinstance(ch, discord.TextChannel) and ch.id not in seen_ids:
                        targets.append(ch)
                        seen_ids.add(ch.id)

        # 3. Fallback from slash command parameter
        if fallback and isinstance(fallback, discord.TextChannel) and fallback.id not in seen_ids:
            targets.append(fallback)
            seen_ids.add(fallback.id)

        return targets

    def _build_usage_card(self, ctx: CustomContext) -> KyroContainer:
        """Construct the Components V2 usage guide matching role command layout."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Media Commands**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} `{prefix}media setup <#channel>`\n"
            f"{dot} `{prefix}media disable <#channel>`\n"
            f"{dot} `{prefix}media show`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    # ─── ON_MESSAGE ENFORCEMENT LISTENER ─────────────────────────────────────

    @commands.Cog.listener("on_message")
    async def on_media_message(self, message: discord.Message) -> None:
        """Sub-microsecond validation on message creation in media channels."""
        # Fast exits: ignore bots, DMs, or non-guild channels
        if message.author.bot or not message.guild:
            return

        # Microsecond in-memory check
        if not self.bot.media_mgr.is_media_channel(message.guild.id, message.channel.id):
            return

        # Staff bypass check (Manage Messages / Administrator / Bot Devs)
        if isinstance(message.author, discord.Member):
            perms = message.author.guild_permissions
            if perms.manage_messages or perms.administrator or perms.manage_guild:
                return

        if self.bot.perm_mgr.is_developer_sync(message.author.id):
            return

        # Verify media content
        if self._contains_media(message):
            return

        # Non-media message detected: delete and send auto-expiring notice
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound):
            pass
        except Exception as e:
            logger.debug(f"Failed to delete non-media message in {message.channel.id}: {e}")

        # Send temporary warning card that auto-deletes after 4 seconds
        try:
            media_emoji = self.bot.custom_emojis.get("media", "📸")
            dot = self.bot.custom_emojis.get("heart_dot", "•")
            container = KyroContainer(accent_color=0xED4245)
            container.add_section(
                content=(
                    f"{media_emoji} **Media Only Channel**\n"
                    f"{dot} {message.author.mention}, you can only send images, videos, GIFs, or links here."
                )
            )
            notice = await send_container_response(message.channel, container)
            await asyncio.sleep(4)
            if isinstance(notice, discord.Message):
                await notice.delete()
        except Exception:
            pass

    # ─── COMMANDS ────────────────────────────────────────────────────────────

    @commands.hybrid_group(
        name="media",
        invoke_without_command=True,
        description="Configure and manage media-only channels in the server.",
    )
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def media_group(self, ctx: CustomContext) -> None:
        """Display media commands usage guide if invoked without subcommand."""
        if ctx.invoked_subcommand is not None:
            return
        container = self._build_usage_card(ctx)
        await send_container_response(ctx, container)

    @media_group.command(
        name="setup",
        description="Configure one or more channels as media-only (images/videos/GIFs only).",
    )
    @app_commands.describe(channel="Channel to configure as media-only")
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def media_setup(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Setup one or more channels as media-only."""
        targets = self.extract_channels(ctx, fallback=channel)
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)

        # Channel is mandatory!
        if not targets:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Channel Required**")
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} Please mention a channel to set up as media-only.\n"
                f"> Example: `{prefix}media setup #media`\n"
                f"> Multiple: `{prefix}media setup #memes #clips`"
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, ephemeral=True)
            return

        added: list[discord.TextChannel] = []
        already_set: list[discord.TextChannel] = []

        for ch in targets:
            success = await self.bot.media_mgr.add_channel(ctx.guild.id, ch.id, added_by=ctx.author.id)
            if success:
                added.append(ch)
            else:
                already_set.append(ch)

        container = KyroContainer(accent_color=None)

        # Single channel setup
        if len(targets) == 1:
            target_ch = targets[0]
            if not added:
                container.add_section(content="**Already Set Up**")
                container.add_separator(divider=True)
                container.add_text(f"{dot} {target_ch.mention} is already set as a media channel.")
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container, ephemeral=True)
                return

            container.add_section(content="**Media Channel Added**")
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} **Channel:** {target_ch.mention}\n"
                f"{dot} **Type:** Images, Videos & GIFs Only\n"
                f"{dot} **Moderator:** {ctx.author.mention}"
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
        else:
            # Multiple channels setup
            if not added:
                container.add_section(content="**Already Set Up**")
                container.add_separator(divider=True)
                container.add_text(f"{dot} All selected channels are already media channels.")
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container, ephemeral=True)
                return

            lines = [f"{dot} {ch.mention}" for ch in added]
            container.add_section(content=f"**Media Channels Added ({len(added)})**")
            container.add_separator(divider=True)
            container.add_text("\n".join(lines))
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} **Type:** Images, Videos & GIFs Only\n"
                f"{dot} **Moderator:** {ctx.author.mention}"
            )
            if already_set:
                already_str = ", ".join(c.mention for c in already_set)
                container.add_text(f"-# Already set up: {already_str}")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)

        if added:
            ch_names = ", ".join(f"#{c.name}" for c in added)
            await dispatch_mod_log(
                self.bot,
                ctx.guild,
                "Media Channel Setup",
                target=None,
                moderator=ctx.author,
                reason=f"Configured {ch_names} as media-only",
                channel=added[0] if len(added) == 1 else None,
            )

    @media_group.command(
        name="disable",
        description="Disable media-only restriction for one or more channels.",
    )
    @app_commands.describe(channel="Channel to disable from media-only")
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def media_disable(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Disable media-only restriction for one or more channels (channel parameter required)."""
        targets = self.extract_channels(ctx, fallback=channel)
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)

        # Channel is mandatory!
        if not targets:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Channel Required**")
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} Please mention which channel to disable.\n"
                f"> Example: `{prefix}media disable #media`\n"
                f"> Multiple: `{prefix}media disable #memes #clips`"
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, ephemeral=True)
            return

        removed: list[discord.TextChannel] = []
        not_set: list[discord.TextChannel] = []

        for ch in targets:
            success = await self.bot.media_mgr.remove_channel(ctx.guild.id, ch.id)
            if success:
                removed.append(ch)
            else:
                not_set.append(ch)

        container = KyroContainer(accent_color=None)

        # Single channel disable
        if len(targets) == 1:
            target_ch = targets[0]
            if not removed:
                container.add_section(content="**Channel Not Found**")
                container.add_separator(divider=True)
                container.add_text(f"{dot} {target_ch.mention} is not set as a media channel.")
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container, ephemeral=True)
                return

            container.add_section(content="**Media Channel Removed**")
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} **Channel:** {target_ch.mention}\n"
                f"{dot} **Status:** Normal Chat Allowed\n"
                f"{dot} **Moderator:** {ctx.author.mention}"
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
        else:
            # Multiple channels disable
            if not removed:
                container.add_section(content="**Channels Not Found**")
                container.add_separator(divider=True)
                container.add_text(f"{dot} None of these channels are currently media channels.")
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container, ephemeral=True)
                return

            lines = [f"{dot} {ch.mention}" for ch in removed]
            container.add_section(content=f"**Media Channels Removed ({len(removed)})**")
            container.add_separator(divider=True)
            container.add_text("\n".join(lines))
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} **Status:** Normal Chat Allowed\n"
                f"{dot} **Moderator:** {ctx.author.mention}"
            )
            if not_set:
                not_set_str = ", ".join(c.mention for c in not_set)
                container.add_text(f"-# Not a media channel: {not_set_str}")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)

        if removed:
            ch_names = ", ".join(f"#{c.name}" for c in removed)
            await dispatch_mod_log(
                self.bot,
                ctx.guild,
                "Media Channel Disabled",
                target=None,
                moderator=ctx.author,
                reason=f"Disabled media-only on {ch_names}",
                channel=removed[0] if len(removed) == 1 else None,
            )

    @media_group.command(
        name="show",
        description="Show all configured media-only channels in this server.",
    )
    @commands.has_permissions(manage_channels=True)
    @commands.guild_only()
    async def media_show(self, ctx: CustomContext) -> None:
        """Display all media-only channels configured in this server."""
        channel_ids = self.bot.media_mgr.get_channels(ctx.guild.id)
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        container = KyroContainer(accent_color=None)

        container.add_section(content="**Media Channels**")
        container.add_separator(divider=True)

        if not channel_ids:
            container.add_text(
                f"{dot} No media channels set up yet.\n"
                f"> Use `{prefix}media setup #channel` to add one!"
            )
        else:
            lines = []
            for cid in sorted(channel_ids):
                ch = ctx.guild.get_channel(cid)
                ch_mention = ch.mention if ch else f"<#{cid}>"
                lines.append(f"{dot} {ch_mention}")
            container.add_text("\n".join(lines))

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(MediaChannels(bot))
