"""
Kyro Discord Bot - Server-Wide Snipe All Suite
Single unified `?snipeall` command for staff with interactive controls:
- Tab filters for All, Deleted only, or Edited only
- Multi-page server navigation
- In-place server snipe wipe button for administrators
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, List
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response, edit_container_response
from src.cogs.utility.snipe import SnipeEntry

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class SnipeAllView(discord.ui.View):
    """Server-wide interactive audit browser across all guild channels."""

    def __init__(
        self,
        bot: KyroBot,
        author_id: int,
        guild: discord.Guild,
        initial_filter: str = "all",
    ) -> None:
        super().__init__(timeout=120.0)
        self.bot = bot
        self.author_id = author_id
        self.guild = guild
        self.filter = initial_filter  # "all", "delete", "edit"
        self.index = 0
        self._refresh_state()

    def _get_filtered_entries(self) -> List[SnipeEntry]:
        all_entries: deque[SnipeEntry] = getattr(self.bot, "guild_snipe_cache", {}).get(self.guild.id, deque())
        if self.filter == "delete":
            return [e for e in all_entries if e.type == "delete"]
        elif self.filter == "edit":
            return [e for e in all_entries if e.type == "edit"]
        return list(all_entries)

    def _refresh_state(self) -> None:
        all_entries: deque[SnipeEntry] = getattr(self.bot, "guild_snipe_cache", {}).get(self.guild.id, deque())
        total_all = len(all_entries)
        del_count = sum(1 for e in all_entries if e.type == "delete")
        edit_count = sum(1 for e in all_entries if e.type == "edit")

        self.tab_all_btn.label = f"All ({total_all})"
        self.tab_all_btn.style = (
            discord.ButtonStyle.primary if self.filter == "all" else discord.ButtonStyle.secondary
        )

        self.tab_del_btn.label = f"Deleted ({del_count})"
        self.tab_del_btn.style = (
            discord.ButtonStyle.primary if self.filter == "delete" else discord.ButtonStyle.secondary
        )

        self.tab_edit_btn.label = f"Edited ({edit_count})"
        self.tab_edit_btn.style = (
            discord.ButtonStyle.primary if self.filter == "edit" else discord.ButtonStyle.secondary
        )

        entries = self._get_filtered_entries()
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
        entries = self._get_filtered_entries()
        container = KyroContainer(accent_color=None)
        e_reg = getattr(self.bot, "custom_emojis", {})
        dot = e_reg.get("heart_dot", "-")

        if not entries:
            container.add_section(
                content=(
                    "**No Server Snipes Found**\n"
                    f"> No {self.filter} records currently match across channels in `{self.guild.name}`."
                )
            )
            container.add_separator(divider=True)
            container.add_text("-# Server Retention Auditor")
            return container

        entry = entries[self.index]
        rel_ts = int(entry.action_at.timestamp())
        created_ts = int(entry.created_at.timestamp())

        badge = "[DELETED]" if entry.type == "delete" else "[EDITED]"
        channel_ref = f"<#{entry.channel_id}>" if entry.channel_id else f"#{entry.channel_name}"

        container.add_section(
            content=(
                f"**{badge} Message in {channel_ref}**\n"
                f"> **Author:** `{entry.author_name}` (`{entry.author_id}`)\n"
                f"> **Action:** <t:{rel_ts}:R> • **Sent:** <t:{created_ts}:t>"
            ),
            accessory={
                "type": 11,
                "media": {"url": entry.author_avatar},
            } if entry.author_avatar else None,
        )
        container.add_separator(divider=True)

        if entry.type == "delete":
            text_content = entry.content if entry.content else "*[No text content - Attachment only]*"
            container.add_text(f">>> {text_content[:1800]}")
        else:
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
        container.add_text(f"-# Server Audit {self.index + 1} of {len(entries)} • {self.guild.name}")
        return container

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the staff member who initiated this server audit can use its controls.",
                ephemeral=True,
            )
            return False
        return True

    # --- Row 0: Filters & Wipe ---
    @discord.ui.button(label="All", style=discord.ButtonStyle.primary, row=0, custom_id="sall:tab_all")
    async def tab_all_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.filter != "all":
            self.filter = "all"
            self.index = 0
            self._refresh_state()
            await edit_container_response(interaction, self.build_container(), view=self)

    @discord.ui.button(label="Deleted", style=discord.ButtonStyle.secondary, row=0, custom_id="sall:tab_del")
    async def tab_del_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.filter != "delete":
            self.filter = "delete"
            self.index = 0
            self._refresh_state()
            await edit_container_response(interaction, self.build_container(), view=self)

    @discord.ui.button(label="Edited", style=discord.ButtonStyle.secondary, row=0, custom_id="sall:tab_edit")
    async def tab_edit_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.filter != "edit":
            self.filter = "edit"
            self.index = 0
            self._refresh_state()
            await edit_container_response(interaction, self.build_container(), view=self)

    @discord.ui.button(label="Wipe All", style=discord.ButtonStyle.danger, row=0, custom_id="sall:btn_wipe")
    async def wipe_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            await interaction.response.send_message(
                "You need `Manage Server` or `Administrator` permission to wipe server snipes.",
                ephemeral=True,
            )
            return

        guild_id = self.guild.id
        guild_cache = getattr(self.bot, "guild_snipe_cache", {})
        count = len(guild_cache.get(guild_id, []))
        if guild_id in guild_cache:
            guild_cache[guild_id].clear()

        channel_cache = getattr(self.bot, "snipe_cache", {})
        for ch in self.guild.channels:
            if ch.id in channel_cache:
                channel_cache[ch.id].clear()

        self._refresh_state()
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Server Snipe Cache Cleared**\n"
                f"> Removed `{count}` tracked message records across all channels in `{self.guild.name}`."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Wiped by {interaction.user.display_name}")
        await edit_container_response(interaction, container, view=None)

    # --- Row 1: Pagination ---
    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=1, custom_id="sall:nav_prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.index > 0:
            self.index -= 1
            self._refresh_state()
            await edit_container_response(interaction, self.build_container(), view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True, row=1, custom_id="sall:nav_counter")
    async def counter_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=1, custom_id="sall:nav_next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        entries = self._get_filtered_entries()
        if self.index < len(entries) - 1:
            self.index += 1
            self._refresh_state()
            await edit_container_response(interaction, self.build_container(), view=self)


class SnipeAllCog(commands.Cog, name="Utility-SnipeAll"):
    """Server-wide message retention auditor across all channels."""
    category: str = "Utility"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="snipeall",
        aliases=["sall", "globalsnipe", "serversnipe"],
        description="Inspect all recently deleted and edited messages across the server.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def snipeall(self, ctx: CustomContext) -> None:
        """
        Open the interactive server-wide snipe browser.
        Requires Manage Messages permission.
        Use buttons to switch between All / Deleted / Edited tabs, or wipe all records.
        """
        guild_id = ctx.guild.id
        entries: deque[SnipeEntry] = getattr(self.bot, "guild_snipe_cache", {}).get(guild_id, deque())

        if not entries:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**No Server Snipes Found**\n"
                    "> No deleted or edited messages have been tracked across this server yet."
                )
            )
            container.add_separator(divider=True)
            container.add_text("-# Server Retention Auditor")
            await send_container_response(ctx, container)
            return

        view = SnipeAllView(
            bot=self.bot,
            author_id=ctx.author.id,
            guild=ctx.guild,
            initial_filter="all",
        )
        container = view.build_container()
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    """Load SnipeAllCog into KyroBot."""
    await bot.add_cog(SnipeAllCog(bot))
