"""
Kyro Discord Bot - Interactive Channel Snipe Suite
Single unified `?snipe` command with button controls:
- Tab toggle for Deleted vs Edited messages
- Pagination navigation (Previous / Next)
- In-place channel cache purge button for moderators
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
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


class SnipeView(discord.ui.View):
    """UI-driven interactive card controller for channel snipes."""

    def __init__(
        self,
        bot: KyroBot,
        author_id: int,
        channel: discord.TextChannel,
        initial_tab: str = "delete",
    ) -> None:
        super().__init__(timeout=120.0)
        self.bot = bot
        self.author_id = author_id
        self.channel = channel
        self.tab = initial_tab  # "delete" or "edit"
        self.index = 0
        self._refresh_state()

    def _get_current_entries(self) -> List[SnipeEntry]:
        all_entries: deque[SnipeEntry] = self.bot.snipe_cache.get(self.channel.id, deque())
        if self.tab == "delete":
            return [e for e in all_entries if e.type == "delete"]
        return [e for e in all_entries if e.type == "edit"]

    def _refresh_state(self) -> None:
        all_entries: deque[SnipeEntry] = self.bot.snipe_cache.get(self.channel.id, deque())
        del_count = sum(1 for e in all_entries if e.type == "delete")
        edit_count = sum(1 for e in all_entries if e.type == "edit")

        # Tab button styling & labels
        self.del_tab_btn.label = f"Deleted ({del_count})"
        self.del_tab_btn.style = (
            discord.ButtonStyle.primary if self.tab == "delete" else discord.ButtonStyle.secondary
        )

        self.edit_tab_btn.label = f"Edited ({edit_count})"
        self.edit_tab_btn.style = (
            discord.ButtonStyle.primary if self.tab == "edit" else discord.ButtonStyle.secondary
        )

        entries = self._get_current_entries()
        total = len(entries)

        if total == 0:
            self.index = 0
            self.prev_btn.disabled = True
            self.next_btn.disabled = True
            self.counter_btn.label = "0 / 0"
        else:
            self.index = max(0, min(self.index, total - 1))
            self.prev_btn.disabled = self.index <= 0
            self.next_btn.disabled = self.index >= total - 1
            self.counter_btn.label = f"{self.index + 1} / {total}"

    def build_container(self) -> KyroContainer:
        entries = self._get_current_entries()
        container = KyroContainer(accent_color=None)
        e_reg = getattr(self.bot, "custom_emojis", {})
        dot = e_reg.get("heart_dot", "-")

        if not entries:
            label = "deleted" if self.tab == "delete" else "edited"
            container.add_section(
                content=(
                    f"**No {label.title()} Messages Found**\n"
                    f"> There are no tracked {label} messages currently recorded in #{self.channel.name}."
                )
            )
            container.add_separator(divider=True)
            container.add_text("-# Kyro Retention Auditor")
            return container

        entry = entries[self.index]
        rel_ts = int(entry.action_at.timestamp())
        created_ts = int(entry.created_at.timestamp())

        if entry.type == "delete":
            container.add_section(
                content=(
                    f"**Deleted Message in #{self.channel.name}**\n"
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
        else:
            container.add_section(
                content=(
                    f"**Edited Message in #{self.channel.name}**\n"
                    f"> **Author:** `{entry.author_name}` (`{entry.author_id}`)\n"
                    f"> **Edited:** <t:{rel_ts}:R> • **Sent:** <t:{created_ts}:t>"
                ),
                accessory={
                    "type": 11,
                    "media": {"url": entry.author_avatar},
                } if entry.author_avatar else None,
            )
            container.add_separator(divider=True)
            b_text = entry.before if entry.before else "*[Empty]*"
            a_text = entry.after if entry.after else "*[Empty]*"
            container.add_text(
                f"**Before:**\n>>> {b_text[:850]}\n\n"
                f"**After:**\n>>> {a_text[:850]}"
            )

        if entry.attachments:
            container.add_separator(divider=True)
            attach_lines = [f"{dot} [Attachment {i+1}]({url})" for i, url in enumerate(entry.attachments[:5])]
            container.add_text("**Attachments:**\n" + "\n".join(attach_lines))

        container.add_separator(divider=True)
        container.add_text(f"-# Record {self.index + 1} of {len(entries)} • #{self.channel.name}")
        return container

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the user who invoked this snipe menu can interact with its controls.",
                ephemeral=True,
            )
            return False
        return True

    # --- Row 1: Filter Tabs & Clear ---
    @discord.ui.button(label="Deleted", style=discord.ButtonStyle.primary, row=0, custom_id="snipe:tab_del")
    async def del_tab_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.tab != "delete":
            self.tab = "delete"
            self.index = 0
            self._refresh_state()
            await edit_container_response(interaction, self.build_container(), view=self)

    @discord.ui.button(label="Edited", style=discord.ButtonStyle.secondary, row=0, custom_id="snipe:tab_edit")
    async def edit_tab_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.tab != "edit":
            self.tab = "edit"
            self.index = 0
            self._refresh_state()
            await edit_container_response(interaction, self.build_container(), view=self)

    @discord.ui.button(label="Clear", style=discord.ButtonStyle.danger, row=0, custom_id="snipe:btn_clear")
    async def clear_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not member.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "You need `Manage Messages` permission to purge channel snipes.",
                ephemeral=True,
            )
            return

        count = len(self.bot.snipe_cache.get(self.channel.id, []))
        if self.channel.id in self.bot.snipe_cache:
            self.bot.snipe_cache[self.channel.id].clear()

        self._refresh_state()
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Channel Snipe History Cleared**\n"
                f"> Successfully purged `{count}` tracked message(s) from #{self.channel.name}."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Cleared by {interaction.user.display_name}")
        await edit_container_response(interaction, container, view=None)

    # --- Row 2: Pagination ---
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=1, custom_id="snipe:nav_prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.index > 0:
            self.index -= 1
            self._refresh_state()
            await edit_container_response(interaction, self.build_container(), view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True, row=1, custom_id="snipe:nav_counter")
    async def counter_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=1, custom_id="snipe:nav_next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        entries = self._get_current_entries()
        if self.index < len(entries) - 1:
            self.index += 1
            self._refresh_state()
            await edit_container_response(interaction, self.build_container(), view=self)


class SnipeCog(commands.Cog, name="Utility-Snipe"):
    """Channel message retention inspector for deleted and edited messages."""
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
        description="Inspect recently deleted and edited messages in this channel.",
    )
    @commands.guild_only()
    async def snipe(self, ctx: CustomContext) -> None:
        """
        Open the interactive channel snipe controller.
        Use buttons to switch between Deleted/Edited tabs, navigate pages, or clear history.
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
            container.add_separator(divider=True)
            container.add_text("-# Kyro Retention Auditor")
            await send_container_response(ctx, container)
            return

        # Default to whichever tab has data (prefer deleted if present)
        has_deleted = any(e.type == "delete" for e in entries)
        initial_tab = "delete" if has_deleted else "edit"

        view = SnipeView(
            bot=self.bot,
            author_id=ctx.author.id,
            channel=ctx.channel,
            initial_tab=initial_tab,
        )
        container = view.build_container()
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    """Load SnipeCog into KyroBot."""
    await bot.add_cog(SnipeCog(bot))
