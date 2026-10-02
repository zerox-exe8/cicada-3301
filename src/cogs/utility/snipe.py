"""
Kyro Discord Bot - Clean Channel Snipe Utility
Clean, simple deleted message inspector without button clutter or complex tabs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
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

        if not message.content and not message.attachments:
            return

        channel_id = message.channel.id
        guild_id = message.guild.id

        if channel_id not in self.bot.snipe_cache:
            self.bot.snipe_cache[channel_id] = deque(maxlen=25)
        if guild_id not in self.bot.guild_snipe_cache:
            self.bot.guild_snipe_cache[guild_id] = deque(maxlen=100)

        entry = SnipeEntry(
            id=message.id,
            author_id=message.author.id,
            author_name=message.author.display_name,
            author_avatar=message.author.display_avatar.url,
            content=message.content,
            attachments=[a.url for a in message.attachments],
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
            author_avatar=before.author.display_avatar.url,
            content=before.content,
            attachments=[a.url for a in before.attachments],
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
        description="View the most recently deleted message in this channel.",
    )
    @app_commands.describe(index="Which deleted message to view (1 = latest)")
    @commands.guild_only()
    async def snipe(self, ctx: CustomContext, index: int = 1) -> None:
        """View the most recently deleted message in this channel."""
        channel_id = ctx.channel.id
        all_entries: deque[SnipeEntry] = self.bot.snipe_cache.get(channel_id, deque())
        deleted_entries = [e for e in all_entries if e.type == "delete"]

        if not deleted_entries:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**No Deleted Messages**\n"
                    f"> There are no recently deleted messages in #{ctx.channel.name}."
                )
            )
            container.add_separator(divider=True)
            await send_container_response(ctx, container)
            return

        if index < 1 or index > len(deleted_entries):
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Invalid Snipe Index**\n"
                    f"> Only `{len(deleted_entries)}` deleted message(s) are cached in this channel (valid: 1 to {len(deleted_entries)})."
                )
            )
            container.add_separator(divider=True)
            await send_container_response(ctx, container)
            return

        entry = deleted_entries[index - 1]
        rel_ts = int(entry.action_at.timestamp())
        created_ts = int(entry.created_at.timestamp())

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Deleted Message in #{ctx.channel.name}**\n"
                f"> **Author:** `{entry.author_name}` (`{entry.author_id}`)\n"
                f"> **Deleted:** <t:{rel_ts}:R> • **Sent:** <t:{created_ts}:t>"
            ),
            accessory={
                "type": 11,
                "media": {"url": entry.author_avatar},
            } if entry.author_avatar else None,
        )
        container.add_separator(divider=True)

        text_content = entry.content if entry.content else "*[No text content - Attachment only]*"
        container.add_text(f">>> {text_content[:1800]}")

        if entry.attachments:
            container.add_separator(divider=True)
            attach_lines = [f"• [Attachment {i+1}]({url})" for i, url in enumerate(entry.attachments[:5])]
            container.add_text("**Attachments:**\n" + "\n".join(attach_lines))

        if len(deleted_entries) > 1:
            container.add_separator(divider=True)
            container.add_text(f"-# Record {index} of {len(deleted_entries)} • Use `{ctx.clean_prefix}snipe <number>` for older messages")

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
                f"**Channel Snipe Cache Cleared**\n"
                f"> Successfully purged `{count}` cached message(s) from #{ctx.channel.name}."
            )
        )
        container.add_separator(divider=True)
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load SnipeCog into KyroBot."""
    await bot.add_cog(SnipeCog(bot))
