"""
Kyro Discord Bot - Comprehensive Channel Snipe Suite
Tracks deleted and edited messages per channel with rich Components V2 cards,
attachment previews, relative timestamps, and interactive button pagination.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional, List
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

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


class SnipePaginationView(discord.ui.View):
    """Interactive multi-item snipe browser with filter and page navigation."""

    def __init__(
        self,
        bot: KyroBot,
        author_id: int,
        entries: List[SnipeEntry],
        channel_name: str,
        current_index: int = 0,
    ) -> None:
        super().__init__(timeout=90.0)
        self.bot = bot
        self.author_id = author_id
        self.entries = entries
        self.channel_name = channel_name
        self.index = current_index
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_btn.disabled = self.index <= 0
        self.next_btn.disabled = self.index >= len(self.entries) - 1
        self.counter_btn.label = f"{self.index + 1} / {len(self.entries)}"

    def build_container(self) -> KyroContainer:
        entry = self.entries[self.index]
        e_reg = getattr(self.bot, "custom_emojis", {})
        dot = e_reg.get("heart_dot", "-")

        container = KyroContainer(accent_color=None)
        rel_ts = int(entry.action_at.timestamp())
        created_ts = int(entry.created_at.timestamp())

        if entry.type == "delete":
            container.add_section(
                content=(
                    f"**Deleted Message in #{entry.channel_name or self.channel_name}**\n"
                    f"> **Author:** `{entry.author_name}` (`{entry.author_id}`)\n"
                    f"> **Deleted:** <t:{rel_ts}:R> • **Sent:** <t:{created_ts}:t>"
                ),
                accessory={
                    "type": 11,
                    "media": {
                        "url": entry.author_avatar,
                    },
                } if entry.author_avatar else None,
            )
            container.add_separator(divider=True)

            text_content = entry.content if entry.content else "*[No text content - Attachment only]*"
            container.add_text(f">>> {text_content[:1800]}")

        else:  # edit
            container.add_section(
                content=(
                    f"**Edited Message in #{entry.channel_name or self.channel_name}**\n"
                    f"> **Author:** `{entry.author_name}` (`{entry.author_id}`)\n"
                    f"> **Edited:** <t:{rel_ts}:R> • **Sent:** <t:{created_ts}:t>"
                ),
                accessory={
                    "type": 11,
                    "media": {
                        "url": entry.author_avatar,
                    },
                } if entry.author_avatar else None,
            )
            container.add_separator(divider=True)

            b_text = entry.before if entry.before else "*[Empty]*"
            a_text = entry.after if entry.after else "*[Empty]*"
            container.add_text(
                f"**Before:**\n>>> {b_text[:850]}\n\n"
                f"**After:**\n>>> {a_text[:850]}"
            )

        # Attachments preview
        if entry.attachments:
            container.add_separator(divider=True)
            attach_lines = [f"{dot} [Attachment {i+1}]({url})" for i, url in enumerate(entry.attachments[:5])]
            container.add_text("**Attachments:**\n" + "\n".join(attach_lines))

        container.add_separator(divider=True)
        container.add_text(f"-# Snipe {self.index + 1} of {len(self.entries)} • Kyro Utility")
        return container

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the user who requested this snipe can navigate through it.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="snipe:prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.index > 0:
            self.index -= 1
            self._update_buttons()
            container = self.build_container()
            await edit_container_response(interaction, container, view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.primary, disabled=True, custom_id="snipe:counter")
    async def counter_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="snipe:next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.index < len(self.entries) - 1:
            self.index += 1
            self._update_buttons()
            container = self.build_container()
            await edit_container_response(interaction, container, view=self)


class SnipeCog(commands.Cog, name="Utility-Snipe"):
    """Channel message retention inspector for deleted and edited text."""
    category: str = "Utility"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        if not hasattr(self.bot, "snipe_cache"):
            self.bot.snipe_cache = {}  # channel_id -> deque[SnipeEntry](maxlen=25)
        if not hasattr(self.bot, "guild_snipe_cache"):
            self.bot.guild_snipe_cache = {}  # guild_id -> deque[SnipeEntry](maxlen=100)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Capture deleted messages in memory buffer."""
        if not message.guild or message.author.bot:
            return

        # Skip messages with zero content and zero attachments
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

        # Store newest at the beginning (index 0)
        self.bot.snipe_cache[channel_id].appendleft(entry)
        self.bot.guild_snipe_cache[guild_id].appendleft(entry)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Capture edited messages in memory buffer."""
        if not before.guild or before.author.bot:
            return

        # Skip if content didn't change (e.g. link embed preview was added)
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

    @commands.hybrid_group(
        name="snipe",
        aliases=["s"],
        description="Inspect recently deleted or edited messages in this channel.",
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def snipe_group(self, ctx: CustomContext, index: int = 1) -> None:
        """
        Retrieve recently deleted or edited messages in the current channel.
        Usage:
          ?snipe       -> Shows most recently deleted/edited message
          ?snipe 2     -> Shows 2nd latest sniped message
        """
        channel_id = ctx.channel.id
        entries: deque[SnipeEntry] = self.bot.snipe_cache.get(channel_id, deque())

        if not entries:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**No Sniped Messages Found**\n"
                    f"> There are no tracked deleted or edited messages in #{ctx.channel.name}."
                )
            )
            await send_container_response(ctx, container)
            return

        target_idx = max(1, min(index, len(entries))) - 1
        entry_list = list(entries)

        view = SnipePaginationView(
            bot=self.bot,
            author_id=ctx.author.id,
            entries=entry_list,
            channel_name=ctx.channel.name,
            current_index=target_idx,
        )
        container = view.build_container()
        await send_container_response(ctx, container, view=view)

    @snipe_group.command(
        name="edit",
        aliases=["edits", "e"],
        description="Retrieve recently edited messages in this channel.",
    )
    @commands.guild_only()
    async def snipe_edit(self, ctx: CustomContext, index: int = 1) -> None:
        """Filter and retrieve only edited messages in this channel."""
        channel_id = ctx.channel.id
        all_entries: deque[SnipeEntry] = self.bot.snipe_cache.get(channel_id, deque())
        edit_entries = [e for e in all_entries if e.type == "edit"]

        if not edit_entries:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**No Edited Messages Found**\n"
                    f"> No tracked edited messages found in #{ctx.channel.name}."
                )
            )
            await send_container_response(ctx, container)
            return

        target_idx = max(1, min(index, len(edit_entries))) - 1
        view = SnipePaginationView(
            bot=self.bot,
            author_id=ctx.author.id,
            entries=edit_entries,
            channel_name=ctx.channel.name,
            current_index=target_idx,
        )
        container = view.build_container()
        await send_container_response(ctx, container, view=view)

    @snipe_group.command(
        name="delete",
        aliases=["deleted", "d"],
        description="Retrieve recently deleted messages in this channel.",
    )
    @commands.guild_only()
    async def snipe_delete(self, ctx: CustomContext, index: int = 1) -> None:
        """Filter and retrieve only deleted messages in this channel."""
        channel_id = ctx.channel.id
        all_entries: deque[SnipeEntry] = self.bot.snipe_cache.get(channel_id, deque())
        del_entries = [e for e in all_entries if e.type == "delete"]

        if not del_entries:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**No Deleted Messages Found**\n"
                    f"> No tracked deleted messages found in #{ctx.channel.name}."
                )
            )
            await send_container_response(ctx, container)
            return

        target_idx = max(1, min(index, len(del_entries))) - 1
        view = SnipePaginationView(
            bot=self.bot,
            author_id=ctx.author.id,
            entries=del_entries,
            channel_name=ctx.channel.name,
            current_index=target_idx,
        )
        container = view.build_container()
        await send_container_response(ctx, container, view=view)

    @snipe_group.command(
        name="clear",
        aliases=["clean", "purge"],
        description="Clear this channel's sniped message history.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def snipe_clear(self, ctx: CustomContext) -> None:
        """Purge all tracked snipes for the current channel."""
        channel_id = ctx.channel.id
        count = len(self.bot.snipe_cache.get(channel_id, []))
        if channel_id in self.bot.snipe_cache:
            self.bot.snipe_cache[channel_id].clear()

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Channel Snipe History Cleared**\n"
                f"> Removed `{count}` tracked sniped message(s) from #{ctx.channel.name}."
            )
        )
        await send_container_response(ctx, container)

    @snipe_group.command(
        name="all",
        aliases=["server"],
        description="Inspect recently deleted or edited messages across all server channels.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def snipe_all_sub(self, ctx: CustomContext) -> None:
        """Shortcut to server-wide snipe inspector."""
        snipe_all_cog = self.bot.get_cog("Utility-SnipeAll")
        if snipe_all_cog and hasattr(snipe_all_cog, "snipe_all_cmd"):
            await snipe_all_cog.snipe_all_cmd.callback(snipe_all_cog, ctx)
        else:
            await ctx.send_error("SnipeAll module is currently unavailable.")


async def setup(bot: KyroBot) -> None:
    """Load SnipeCog into KyroBot."""
    await bot.add_cog(SnipeCog(bot))
