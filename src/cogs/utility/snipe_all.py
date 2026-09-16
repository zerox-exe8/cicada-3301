"""
Kyro Discord Bot - Server-Wide Snipe All Suite
Inspects all recently deleted and edited messages across every channel in the server.
Restricted to server moderators with Manage Messages permissions.
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


class SnipeAllPaginationView(discord.ui.View):
    """Server-wide interactive snipe browser across all guild channels."""

    def __init__(
        self,
        bot: KyroBot,
        author_id: int,
        entries: List[SnipeEntry],
        guild_name: str,
        current_index: int = 0,
    ) -> None:
        super().__init__(timeout=120.0)
        self.bot = bot
        self.author_id = author_id
        self.entries = entries
        self.guild_name = guild_name
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

        badge = "[DELETED]" if entry.type == "delete" else "[EDITED]"
        channel_ref = f"<#{entry.channel_id}>" if entry.channel_id else f"#{entry.channel_name}"

        container.add_section(
            content=(
                f"**{badge} Message in {channel_ref}**\n"
                f"> **Author:** `{entry.author_name}` (`{entry.author_id}`)\n"
                f"> **Action Time:** <t:{rel_ts}:R> • **Sent:** <t:{created_ts}:t>"
            ),
            accessory={
                "type": 11,
                "media": {
                    "url": entry.author_avatar,
                },
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
        container.add_text(f"-# Server Snipe {self.index + 1} of {len(self.entries)} • {self.guild_name}")
        return container

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the moderator who requested this server snipe can navigate through it.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="sall:prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.index > 0:
            self.index -= 1
            self._update_buttons()
            container = self.build_container()
            await edit_container_response(interaction, container, view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.primary, disabled=True, custom_id="sall:counter")
    async def counter_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pass

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, custom_id="sall:next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.index < len(self.entries) - 1:
            self.index += 1
            self._update_buttons()
            container = self.build_container()
            await edit_container_response(interaction, container, view=self)


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
    async def snipe_all_cmd(self, ctx: CustomContext, index: int = 1) -> None:
        """
        Browse recently deleted or edited messages across all channels in this guild.
        Requires Manage Messages permission.
        Usage:
          ?snipeall       -> Shows latest server-wide sniped message
          ?snipeall 3     -> Shows 3rd latest server-wide sniped message
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
            await send_container_response(ctx, container)
            return

        target_idx = max(1, min(index, len(entries))) - 1
        entry_list = list(entries)

        view = SnipeAllPaginationView(
            bot=self.bot,
            author_id=ctx.author.id,
            entries=entry_list,
            guild_name=ctx.guild.name,
            current_index=target_idx,
        )
        container = view.build_container()
        await send_container_response(ctx, container, view=view)

    @commands.command(
        name="clearsnipeall",
        aliases=["clearglobalsnipe", "clearsall"],
        description="Purge the entire server's sniped message audit history.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def clear_snipe_all(self, ctx: CustomContext) -> None:
        """Purge all tracked snipes across every channel in the server."""
        guild_id = ctx.guild.id
        guild_cache = getattr(self.bot, "guild_snipe_cache", {})
        count = len(guild_cache.get(guild_id, []))

        if guild_id in guild_cache:
            guild_cache[guild_id].clear()

        # Also purge channel caches for this guild
        channel_cache = getattr(self.bot, "snipe_cache", {})
        for channel in ctx.guild.channels:
            if channel.id in channel_cache:
                channel_cache[channel.id].clear()

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Server Snipe Cache Cleared**\n"
                f"> Removed `{count}` tracked message records across all channels in `{ctx.guild.name}`."
            )
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load SnipeAllCog into KyroBot."""
    await bot.add_cog(SnipeAllCog(bot))
