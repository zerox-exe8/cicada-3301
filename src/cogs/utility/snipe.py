"""
Kyro Discord Bot - Clean Channel Snipe Utility
Clean, focused deleted message inspector with direct highlighted content and zero clutter.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


@dataclass
class SnipeEntry:
    """Structure storing captured deleted or edited message data."""
    id: int
    author_id: int
    author_name: str
    author_avatar: str
    content: str
    attachments: list[str]
    created_at: datetime
    action_at: datetime
    type: str  # 'delete' or 'edit'
    before: Optional[str] = None
    after: Optional[str] = None
    guild_id: int = 0
    channel_id: int = 0
    channel_name: str = ""


class SnipeCog(commands.Cog, name="Utility-Snipe"):
    """Channel message retention inspector for deleted messages."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        if not hasattr(self.bot, "snipe_cache"):
            self.bot.snipe_cache = {}
        if not hasattr(self.bot, "guild_snipe_cache"):
            self.bot.guild_snipe_cache = {}

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Capture deleted messages in memory buffer."""
        if not message.guild or message.author.bot:
            return

        content = message.content or ""
        attachments = [a.url for a in message.attachments if a.url]
        stickers = [s.url for s in message.stickers if s.url]

        if not content and not attachments and not stickers:
            if message.embeds:
                content = "*[Embed]*"
            else:
                return

        channel_id = message.channel.id
        guild_id = message.guild.id

        if channel_id not in self.bot.snipe_cache:
            self.bot.snipe_cache[channel_id] = deque(maxlen=25)
        if guild_id not in self.bot.guild_snipe_cache:
            self.bot.guild_snipe_cache[guild_id] = deque(maxlen=100)

        all_media = attachments + stickers

        entry = SnipeEntry(
            id=message.id,
            author_id=message.author.id,
            author_name=message.author.display_name,
            author_avatar=message.author.display_avatar.url if message.author.display_avatar else "",
            content=content,
            attachments=all_media,
            created_at=message.created_at,
            action_at=discord.utils.utcnow(),
            type="delete",
            guild_id=guild_id,
            channel_id=channel_id,
            channel_name=message.channel.name,
        )

        self.bot.snipe_cache[channel_id].appendleft(entry)
        self.bot.guild_snipe_cache[guild_id].appendleft(entry)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Capture edited messages in memory buffer."""
        if not before.guild or before.author.bot:
            return

        if before.content == after.content:
            return

        channel_id = before.channel.id
        guild_id = before.guild.id

        if channel_id not in self.bot.snipe_cache:
            self.bot.snipe_cache[channel_id] = deque(maxlen=25)
        if guild_id not in self.bot.guild_snipe_cache:
            self.bot.guild_snipe_cache[guild_id] = deque(maxlen=100)

        entry = SnipeEntry(
            id=before.id,
            author_id=before.author.id,
            author_name=before.author.display_name,
            author_avatar=before.author.display_avatar.url if before.author.display_avatar else "",
            content=before.content,
            attachments=[a.url for a in before.attachments if a.url],
            created_at=before.created_at,
            action_at=discord.utils.utcnow(),
            type="edit",
            before=before.content,
            after=after.content,
            guild_id=guild_id,
            channel_id=channel_id,
            channel_name=before.channel.name,
        )

        self.bot.snipe_cache[channel_id].appendleft(entry)
        self.bot.guild_snipe_cache[guild_id].appendleft(entry)

    @commands.hybrid_command(
        name="snipe",
        aliases=["sn"],
        description="View recently deleted messages in this channel.",
    )
    @commands.guild_only()
    async def snipe(self, ctx: CustomContext) -> None:
        """View recently deleted messages in this channel."""
        channel_id = ctx.channel.id
        all_entries: deque[SnipeEntry] = self.bot.snipe_cache.get(channel_id, deque())
        deleted_entries = [e for e in all_entries if e.type == "delete"]

        if not deleted_entries:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**No Deleted Messages**\n"
                    f"> No recently deleted messages found in #{ctx.channel.name}."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        # Fetch recent deleted messages (all deleted within 3 minutes of latest, or up to top 5)
        latest_ts = deleted_entries[0].action_at.timestamp()
        recent_threshold = latest_ts - 180  # 3 minutes window
        entries_to_show = [
            e for e in deleted_entries
            if e.action_at.timestamp() >= recent_threshold
        ][:5]

        if not entries_to_show:
            entries_to_show = deleted_entries[:3]

        container = KyroContainer(accent_color=None)

        for idx, entry in enumerate(entries_to_show):
            if idx > 0:
                container.add_separator(divider=True)

            rel_ts = int(entry.action_at.timestamp())
            container.add_text(f"**{entry.author_name}** • <t:{rel_ts}:R>")
            container.add_separator(divider=True)

            msg_text = entry.content if entry.content else "*[Media / Attachment]*"
            if "\n" in msg_text:
                highlighted = f"```{msg_text[:1500]}```"
            else:
                highlighted = f"`{msg_text[:1500]}`"

            container.add_text(highlighted)

            # Render image directly if available
            image_exts = (".png", ".jpg", ".jpeg", ".gif", ".webp")
            images = [u for u in entry.attachments if any(u.lower().split("?")[0].endswith(ext) for ext in image_exts)]
            for img in images[:1]:
                container.add_media(img)

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="clearsnipe",
        aliases=["csnipe"],
        description="Purge the deleted message snipe cache for this channel.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def clearsnipe(self, ctx: CustomContext) -> None:
        """Purge the deleted message snipe cache for this channel."""
        channel_id = ctx.channel.id
        count = len(self.bot.snipe_cache.get(channel_id, []))
        if channel_id in self.bot.snipe_cache:
            self.bot.snipe_cache[channel_id].clear()

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Snipe Cache Cleared**\n"
                f"> Successfully purged `{count}` cached message(s) from #{ctx.channel.name}."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load SnipeCog into KyroBot."""
    await bot.add_cog(SnipeCog(bot))
