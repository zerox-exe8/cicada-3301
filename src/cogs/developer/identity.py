"""
Kyro Discord Bot - Bot Identity & Persona Customization Module
Allows Bot Owners and Developers to live-update the bot's avatar, username, and status
using clean Components V2 cards, interactive Modals, and direct CLI shortcuts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import aiohttp
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Developer.Identity")


# =========================================================
# Interactive Discord Modals (Pop-up Forms)
# =========================================================

class EditNameModal(discord.ui.Modal, title="Bot Persona: Edit Username"):
    """Pop-up modal to change bot username."""

    new_name = discord.ui.TextInput(
        label="New Bot Username",
        placeholder="e.g. Kyro",
        min_length=2,
        max_length=32,
        required=True,
    )

    def __init__(self, bot: KyroBot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        name_val = str(self.new_name.value).strip()

        try:
            await self.bot.user.edit(username=name_val)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Bot Username Updated**\n"
                    f"> **New Username:** `{name_val}`\n"
                    f"> **Status:** `Applied Across Network`"
                )
            )
            await interaction.followup.send(embed=container.to_embed(), ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(
                f"**Failed to update username:** `{e}`\n"
                f"-# Note: Discord restricts bot name updates to 2 times per hour.",
                ephemeral=True,
            )


class EditAvatarModal(discord.ui.Modal, title="Bot Persona: Edit Avatar"):
    """Pop-up modal to change bot avatar."""

    avatar_url = discord.ui.TextInput(
        label="Direct Image URL",
        placeholder="https://example.com/avatar.png (PNG, JPG, WEBP)",
        min_length=10,
        max_length=500,
        required=True,
    )

    def __init__(self, bot: KyroBot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        url_val = str(self.avatar_url.value).strip()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url_val) as resp:
                    if resp.status != 200:
                        await interaction.followup.send(
                            f"**Error:** Could not download image (HTTP {resp.status}).",
                            ephemeral=True,
                        )
                        return
                    img_bytes = await resp.read()

            await self.bot.user.edit(avatar=img_bytes)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Bot Avatar Updated**\n"
                    f"> **Status:** `Live Avatar Applied Successfully`"
                ),
                accessory={"type": 11, "media": {"url": self.bot.user.display_avatar.url}},
            )
            await interaction.followup.send(embed=container.to_embed(), ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"**Failed to update avatar:** `{e}`", ephemeral=True)


class EditStatusModal(discord.ui.Modal, title="Bot Persona: Edit Status"):
    """Pop-up modal to change bot activity text."""

    status_text = discord.ui.TextInput(
        label="Activity Status Text",
        placeholder="e.g. Listening to ?help",
        min_length=1,
        max_length=128,
        required=True,
    )

    def __init__(self, bot: KyroBot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        text_val = str(self.status_text.value).strip()

        try:
            await self.bot.change_presence(
                status=discord.Status.dnd,
                activity=discord.CustomActivity(name=text_val),
            )
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Bot Activity Status Updated**\n"
                    f"> **Activity:** `{text_val}`\n"
                    f"> **Status:** `Do Not Disturb (DND)`"
                )
            )
            await interaction.followup.send(embed=container.to_embed(), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"**Failed to update status:** `{e}`", ephemeral=True)


# =========================================================
# Interactive View with Clean Action Buttons
# =========================================================

class BotEditView(discord.ui.View):
    """Interactive button action row to edit bot identity."""

    def __init__(self, bot: KyroBot, author_id: int) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "**Access Denied:** Only the developer who initiated this console can interact.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Edit Avatar", style=discord.ButtonStyle.secondary, custom_id="btn_botedit_avatar")
    async def btn_avatar(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = EditAvatarModal(self.bot)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.secondary, custom_id="btn_botedit_name")
    async def btn_name(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = EditNameModal(self.bot)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Status", style=discord.ButtonStyle.secondary, custom_id="btn_botedit_status")
    async def btn_status(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = EditStatusModal(self.bot)
        await interaction.response.send_modal(modal)


# =========================================================
# Identity Cog & Commands
# =========================================================

class IdentityCog(commands.Cog, name="Developer-Identity"):
    """Bot persona, avatar, username, and live presence manager."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.group(
        name="botedit",
        aliases=["setbot", "identity", "botset"],
        invoke_without_command=True,
        description="Interactive Bot Identity & Persona console with Edit buttons.",
    )
    @is_developer()
    async def botedit(self, ctx: CustomContext) -> None:
        """Overview and interactive control panel for bot persona."""
        bot_user = self.bot.user
        avatar_url = bot_user.display_avatar.url if bot_user else None
        current_name = bot_user.name if bot_user else "Kyro"

        # Resolve current custom activity name
        activity_str = "Listening to ?help"
        if self.bot.guilds and self.bot.guilds[0].me.activity:
            act = self.bot.guilds[0].me.activity
            activity_str = getattr(act, "name", str(act))

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### {current_name} Persona Console\n"
                f"> **Username** • `{current_name}`\n"
                f"> **Status** • `{activity_str}`\n"
                f"> **Mode** • `Do Not Disturb (DND)`"
            ),
            accessory={"type": 11, "media": {"url": avatar_url}} if avatar_url else None,
        )
        container.add_separator(divider=True)
        container.add_text(
            f"> Use buttons below or CLI shortcuts:\n"
            f"> `?botedit avatar <url>` • `?botedit name <name>` • `?botedit status <text>`\n\n"
            f"-# Root Identity Customization • Instant Live Effect"
        )

        view = BotEditView(self.bot, ctx.author.id)
        await send_container_response(ctx, container, view=view)

    @botedit.command(name="avatar")
    @is_developer()
    async def edit_avatar(self, ctx: CustomContext, url: Optional[str] = None) -> None:
        """Update bot avatar via direct URL or attached image."""
        img_url = url

        # Check attachment if no URL provided
        if not img_url and ctx.message.attachments:
            img_url = ctx.message.attachments[0].url

        if not img_url:
            container = KyroContainer(accent_color=None)
            container.add_text("**Error:** Provide an image URL or attach an image to your message.")
            await send_container_response(ctx, container)
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(img_url) as resp:
                    if resp.status != 200:
                        await ctx.send_error(f"Failed to fetch image: HTTP {resp.status}")
                        return
                    img_bytes = await resp.read()

            await self.bot.user.edit(avatar=img_bytes)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Bot Avatar Updated**\n"
                    f"> **Status:** `Live Avatar Applied Successfully`"
                ),
                accessory={"type": 11, "media": {"url": self.bot.user.display_avatar.url}},
            )
            await send_container_response(ctx, container)
        except Exception as e:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Failed to update avatar:** `{e}`")
            await send_container_response(ctx, container)

    @botedit.command(name="name")
    @is_developer()
    async def edit_name(self, ctx: CustomContext, *, new_name: str) -> None:
        """Update bot username."""
        clean_name = new_name.strip()
        try:
            await self.bot.user.edit(username=clean_name)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Bot Username Updated**\n"
                    f"> **New Username:** `{clean_name}`\n"
                    f"> **Status:** `Applied Across Network`"
                )
            )
            await send_container_response(ctx, container)
        except Exception as e:
            container = KyroContainer(accent_color=None)
            container.add_text(
                f"**Failed to update username:** `{e}`\n"
                f"-# Note: Discord restricts bot name changes to 2 times per hour."
            )
            await send_container_response(ctx, container)

    @botedit.command(name="status")
    @is_developer()
    async def edit_status(self, ctx: CustomContext, *, new_status: str) -> None:
        """Update bot presence status text."""
        clean_status = new_status.strip()
        try:
            await self.bot.change_presence(
                status=discord.Status.dnd,
                activity=discord.CustomActivity(name=clean_status),
            )
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Bot Activity Status Updated**\n"
                    f"> **Activity:** `{clean_status}`\n"
                    f"> **Status:** `Do Not Disturb (DND)`"
                )
            )
            await send_container_response(ctx, container)
        except Exception as e:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Failed to update status:** `{e}`")
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(IdentityCog(bot))
