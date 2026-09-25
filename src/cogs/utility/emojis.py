"""
Kyro Discord Bot - Expression Manager (Emojis & Stickers)
Minimal, ultra-clean Components V2 dashboard for managing and deleting server expressions.
Supports both non-Nitro users (visual dropdowns for animated/static emojis) and stickers (with instant live preview).
Guaranteed zero-timeout with immediate deferred interaction acknowledgements.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Utility.Emojis")


class ExpressionManagerView(discord.ui.View):
    """Interactive view for navigating, previewing, and deleting server emojis and stickers."""

    def __init__(self, ctx: CustomContext, bot: KyroBot, initial_mode: str = "emojis") -> None:
        super().__init__(timeout=120)
        self.ctx = ctx
        self.bot = bot
        self.guild = ctx.guild
        self.author_id = ctx.author.id

        self.mode: str = initial_mode  # "emojis" or "stickers"
        self.page: int = 0
        self.selected_id: Optional[int] = None
        self.status_msg: Optional[str] = None

        self._rebuild_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "You cannot interact with this expression manager.",
                ephemeral=True,
            )
            return False

        perms = getattr(interaction.user, "guild_permissions", None)
        has_perm = perms and (
            getattr(perms, "manage_expressions", False)
            or getattr(perms, "manage_emojis_and_stickers", False)
            or perms.administrator
        )
        if not has_perm:
            await interaction.response.send_message(
                "You need `Manage Expressions` permission to delete expressions.",
                ephemeral=True,
            )
            return False

        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item) -> None:
        logger.error(f"Error in ExpressionManagerView on {item}: {error}", exc_info=error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Action failed: `{error}`", ephemeral=True)
            else:
                await interaction.followup.send(f"Action failed: `{error}`", ephemeral=True)
        except Exception:
            pass

    def _get_items(self) -> list[discord.Emoji | discord.GuildSticker]:
        """Fetch sorted list of emojis or stickers for current mode."""
        if self.mode == "emojis":
            return sorted(list(self.guild.emojis), key=lambda e: e.name.lower())
        return sorted(list(self.guild.stickers), key=lambda s: s.name.lower())

    def _get_total_pages(self) -> int:
        total = len(self._get_items())
        return max(1, math.ceil(total / 25))

    def _rebuild_components(self) -> None:
        """Reconstruct the buttons and dropdown based on current state."""
        self.clear_items()
        items = self._get_items()
        total_pages = self._get_total_pages()
        if self.page >= total_pages:
            self.page = max(0, total_pages - 1)

        # Row 0: Mode selection buttons
        btn_emoji = discord.ui.Button(
            label=f"Emojis ({len(self.guild.emojis)})",
            style=discord.ButtonStyle.primary if self.mode == "emojis" else discord.ButtonStyle.secondary,
            row=0,
        )
        btn_emoji.callback = self._on_switch_emojis
        self.add_item(btn_emoji)

        btn_sticker = discord.ui.Button(
            label=f"Stickers ({len(self.guild.stickers)})",
            style=discord.ButtonStyle.primary if self.mode == "stickers" else discord.ButtonStyle.secondary,
            row=0,
        )
        btn_sticker.callback = self._on_switch_stickers
        self.add_item(btn_sticker)

        # Row 1: Select Dropdown (up to 25 items per page)
        start_idx = self.page * 25
        page_items = items[start_idx : start_idx + 25]

        options: list[discord.SelectOption] = []
        for item in page_items:
            if self.mode == "emojis":
                is_anim = getattr(item, "animated", False)
                desc = "Animated" if is_anim else "Static"
                options.append(
                    discord.SelectOption(
                        label=item.name[:100],
                        value=str(item.id),
                        description=desc,
                        emoji=item if isinstance(item, discord.Emoji) else None,
                        default=(item.id == self.selected_id),
                    )
                )
            else:
                fmt_obj = getattr(item, "format", None)
                fmt_name = getattr(fmt_obj, "name", str(fmt_obj or "PNG")).upper()
                options.append(
                    discord.SelectOption(
                        label=item.name[:100],
                        value=str(item.id),
                        description=f"Format: {fmt_name}",
                        default=(item.id == self.selected_id),
                    )
                )

        if options:
            placeholder = (
                "Select an emoji to delete..."
                if self.mode == "emojis"
                else "Select a sticker to preview & delete..."
            )
            select = discord.ui.Select(
                placeholder=placeholder,
                min_values=1,
                max_values=1,
                options=options,
                row=1,
            )
            select.callback = self._on_select_item
            self.add_item(select)

        # Row 2: Navigation & Action Buttons
        btn_prev = discord.ui.Button(
            emoji="◀",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page <= 0),
            row=2,
        )
        btn_prev.callback = self._on_prev_page
        self.add_item(btn_prev)

        btn_indicator = discord.ui.Button(
            label=f"{self.page + 1}/{total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            row=2,
        )
        self.add_item(btn_indicator)

        btn_next = discord.ui.Button(
            emoji="▶",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page >= total_pages - 1),
            row=2,
        )
        btn_next.callback = self._on_next_page
        self.add_item(btn_next)

        btn_delete = discord.ui.Button(
            label=f"Delete {'Emoji' if self.mode == 'emojis' else 'Sticker'}",
            style=discord.ButtonStyle.danger,
            disabled=(self.selected_id is None),
            row=2,
        )
        btn_delete.callback = self._on_delete_item
        self.add_item(btn_delete)

    def build_container(self) -> KyroContainer:
        """Construct ultra-clean Components V2 presentation."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        dot = e_reg.get("heart_dot", "-") if e_reg else "-"

        container = KyroContainer(accent_color=None)

        preview_url: Optional[str] = None
        selected_text: Optional[str] = None

        if self.selected_id is not None:
            if self.mode == "emojis":
                emoji = self.guild.get_emoji(self.selected_id)
                if emoji:
                    preview_url = emoji.url
                    prefix = "a" if getattr(emoji, "animated", False) else ""
                    selected_text = (
                        f"{dot} **Selected Emoji:** <{prefix}:{emoji.name}:{emoji.id}> `{emoji.name}`\n"
                        f"{dot} **Type:** `{'Animated' if getattr(emoji, 'animated', False) else 'Static'}` {dot} **ID:** `{emoji.id}`"
                    )
            else:
                sticker = self.guild.get_sticker(self.selected_id)
                if sticker:
                    preview_url = sticker.url
                    fmt_obj = getattr(sticker, "format", None)
                    fmt_name = getattr(fmt_obj, "name", str(fmt_obj or "PNG")).upper()
                    selected_text = (
                        f"{dot} **Selected Sticker:** `{sticker.name}`\n"
                        f"{dot} **Format:** `{fmt_name}` {dot} **ID:** `{sticker.id}`"
                    )

        # Header Section
        accessory = {"type": 11, "media": {"url": preview_url}} if preview_url else None
        container.add_section(
            content=(
                f"**Expression Manager**\n"
                f"> Manage and remove server expressions."
            ),
            accessory=accessory,
        )
        container.add_separator(divider=True)

        if selected_text:
            container.add_text(selected_text)
        else:
            emoji_count = len(self.guild.emojis)
            sticker_count = len(self.guild.stickers)
            if self.mode == "stickers" and sticker_count == 0:
                container.add_text(
                    f"{dot} **Server Total:** `{sticker_count} Stickers`\n"
                    f"{dot} No custom stickers found in this server."
                )
            elif self.mode == "emojis" and emoji_count == 0:
                container.add_text(
                    f"{dot} **Server Total:** `{emoji_count} Emojis`\n"
                    f"{dot} No custom emojis found in this server."
                )
            else:
                container.add_text(
                    f"{dot} **Server Total:** `{emoji_count} Emojis` {dot} `{sticker_count} Stickers`\n"
                    f"{dot} Choose an item from the dropdown below to preview or delete."
                )

        if self.status_msg:
            container.add_separator(divider=True)
            container.add_text(self.status_msg)

        return container

    async def _on_switch_emojis(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass

        self.mode = "emojis"
        self.page = 0
        self.selected_id = None
        self.status_msg = None
        self._rebuild_components()
        container = self.build_container()
        await edit_container_response(interaction, container, view=self)

    async def _on_switch_stickers(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass

        # If cache is empty, fetch fresh stickers from API
        if not self.guild.stickers:
            try:
                await self.guild.fetch_stickers()
            except Exception:
                pass

        self.mode = "stickers"
        self.page = 0
        self.selected_id = None
        self.status_msg = None
        self._rebuild_components()
        container = self.build_container()
        await edit_container_response(interaction, container, view=self)

    async def _on_prev_page(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass

        if self.page > 0:
            self.page -= 1
            self.selected_id = None
            self.status_msg = None
            self._rebuild_components()
            container = self.build_container()
            await edit_container_response(interaction, container, view=self)

    async def _on_next_page(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass

        total = self._get_total_pages()
        if self.page < total - 1:
            self.page += 1
            self.selected_id = None
            self.status_msg = None
            self._rebuild_components()
            container = self.build_container()
            await edit_container_response(interaction, container, view=self)

    async def _on_select_item(self, interaction: discord.Interaction) -> None:
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass

        if interaction.data and "values" in interaction.data and interaction.data["values"]:
            self.selected_id = int(interaction.data["values"][0])
            self.status_msg = None
            self._rebuild_components()
            container = self.build_container()
            await edit_container_response(interaction, container, view=self)

    async def _on_delete_item(self, interaction: discord.Interaction) -> None:
        if not self.selected_id:
            await interaction.response.send_message("No item selected.", ephemeral=True)
            return

        if not self.guild.me.guild_permissions.manage_expressions:
            await interaction.response.send_message(
                "I do not have `Manage Expressions` permission in this server.",
                ephemeral=True,
            )
            return

        # Defer immediately to prevent mobile timeout
        if not interaction.response.is_done():
            try:
                await interaction.response.defer()
            except Exception:
                pass

        e_reg = getattr(self.bot, "custom_emojis", None)
        dot = e_reg.get("heart_dot", "-") if e_reg else "-"

        try:
            if self.mode == "emojis":
                emoji = self.guild.get_emoji(self.selected_id)
                if not emoji:
                    self.status_msg = f"{dot} Emoji was not found or already deleted."
                else:
                    name = emoji.name
                    await emoji.delete(reason=f"Deleted by {interaction.user} via Kyro Manager")
                    self.status_msg = f"{dot} Successfully deleted emoji `{name}`."
            else:
                sticker = self.guild.get_sticker(self.selected_id)
                if not sticker:
                    self.status_msg = f"{dot} Sticker was not found or already deleted."
                else:
                    name = sticker.name
                    await sticker.delete(reason=f"Deleted by {interaction.user} via Kyro Manager")
                    self.status_msg = f"{dot} Successfully deleted sticker `{name}`."

            self.selected_id = None
            self._rebuild_components()
            container = self.build_container()
            await edit_container_response(interaction, container, view=self)

        except discord.Forbidden:
            await interaction.followup.send(
                "Failed to delete: Missing permissions to manage server expressions.",
                ephemeral=True,
            )
        except discord.HTTPException as err:
            await interaction.followup.send(
                f"Failed to delete: {err}",
                ephemeral=True,
            )


class Emojis(commands.Cog):
    """Server expressions management (Emojis & Stickers) with Components V2 dashboard."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(
        name="emojis",
        aliases=["expr", "expressions", "emojimanager", "stickers", "delemoji"],
        help="Interactive studio to browse, preview, and delete server emojis or stickers.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_expressions=True)
    async def emojis_command(self, ctx: CustomContext) -> None:
        """Launch the interactive Expression Manager."""
        if not ctx.guild.me.guild_permissions.manage_expressions:
            e_reg = getattr(self.bot, "custom_emojis", None)
            dot = e_reg.get("heart_dot", "-") if e_reg else "-"
            container = KyroContainer()
            container.add_text(f"{dot} I need **Manage Expressions** permission to manage server emojis/stickers.")
            await send_container_response(ctx, container)
            return

        # Ensure stickers are fetched from Discord REST API if not yet in cache
        if not ctx.guild.stickers:
            try:
                await ctx.guild.fetch_stickers()
            except Exception:
                pass

        # If user invoked with ?stickers, directly start in stickers mode
        initial_mode = "stickers" if ctx.invoked_with in ("stickers", "delsticker") else "emojis"

        view = ExpressionManagerView(ctx, self.bot, initial_mode=initial_mode)
        container = view.build_container()
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Emojis(bot))
