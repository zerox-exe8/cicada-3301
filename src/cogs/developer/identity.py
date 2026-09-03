"""
Kyro Discord Bot - Bot Identity & Persona Customization Module
Allows Bot Owners and Developers to live-update the bot's avatar, username, and status
using clean Components V2 embed prompt flows, interactive buttons, and direct CLI shortcuts.
"""

from __future__ import annotations

import asyncio
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
# Interactive View with Embed Prompt Buttons
# =========================================================

class BotEditView(discord.ui.View):
    """Interactive button action row to trigger embed-based input prompts."""

    def __init__(self, bot: KyroBot, author_id: int, channel_id: int) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.author_id = author_id
        self.channel_id = channel_id

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
        prompt_card = KyroContainer(accent_color=None)
        prompt_card.add_section(
            content=(
                "**Edit Bot Avatar**\n"
                "> Upload an image attachment or paste a direct image URL in this channel.\n"
                "> Type `cancel` to abort."
            )
        )
        prompt_card.add_separator(divider=True)
        prompt_card.add_text("-# Waiting for input • 60s timeout")
        await send_container_response(interaction, prompt_card, ephemeral=True)

        def check(m: discord.Message) -> bool:
            return m.author.id == self.author_id and m.channel.id == self.channel_id

        try:
            msg: discord.Message = await self.bot.wait_for("message", check=check, timeout=60.0)
        except asyncio.TimeoutError:
            timeout_card = KyroContainer(accent_color=None)
            timeout_card.add_text("**Avatar Update Timed Out:** No input received within 60 seconds.")
            await send_container_response(interaction.channel, timeout_card)
            return

        if msg.content.strip().lower() == "cancel":
            cancel_card = KyroContainer(accent_color=None)
            cancel_card.add_text("**Cancelled:** Avatar update aborted.")
            await send_container_response(interaction.channel, cancel_card)
            return

        img_url = None
        if msg.attachments:
            img_url = msg.attachments[0].url
        elif msg.content.strip().startswith("http"):
            img_url = msg.content.strip()

        if not img_url:
            err_card = KyroContainer(accent_color=None)
            err_card.add_text("**Error:** No valid image attachment or URL found.")
            await send_container_response(interaction.channel, err_card)
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(img_url) as resp:
                    if resp.status != 200:
                        err_card = KyroContainer(accent_color=None)
                        err_card.add_text(f"**Error:** Could not download image (HTTP {resp.status}).")
                        await send_container_response(interaction.channel, err_card)
                        return
                    img_bytes = await resp.read()

            await self.bot.user.edit(avatar=img_bytes)
            success_card = KyroContainer(accent_color=None)
            success_card.add_section(
                content=(
                    "**Bot Avatar Updated**\n"
                    "> **Status:** `Live Avatar Applied Successfully`"
                ),
                accessory={"type": 11, "media": {"url": self.bot.user.display_avatar.url}},
            )
            success_card.add_separator(divider=True)
            success_card.add_text("-# Powered by Kyro Studio")
            await send_container_response(interaction.channel, success_card)
        except discord.HTTPException as e:
            err_card = KyroContainer(accent_color=None)
            err_card.add_text(
                f"**Failed to update avatar:** `{e}`\n"
                f"-# Note: Discord restricts avatar changes to 2 times per 10 minutes."
            )
            await send_container_response(interaction.channel, err_card)

    @discord.ui.button(label="Edit Banner", style=discord.ButtonStyle.secondary, custom_id="btn_botedit_banner")
    async def btn_banner(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        prompt_card = KyroContainer(accent_color=None)
        prompt_card.add_section(
            content=(
                "**Edit Bot Banner**\n"
                "> Upload a banner image attachment or paste a direct image URL in this channel.\n"
                "> Type `cancel` to abort."
            )
        )
        prompt_card.add_separator(divider=True)
        prompt_card.add_text("-# Waiting for input • 60s timeout")
        await send_container_response(interaction, prompt_card, ephemeral=True)

        def check(m: discord.Message) -> bool:
            return m.author.id == self.author_id and m.channel.id == self.channel_id

        try:
            msg: discord.Message = await self.bot.wait_for("message", check=check, timeout=60.0)
        except asyncio.TimeoutError:
            timeout_card = KyroContainer(accent_color=None)
            timeout_card.add_text("**Banner Update Timed Out:** No input received within 60 seconds.")
            await send_container_response(interaction.channel, timeout_card)
            return

        if msg.content.strip().lower() == "cancel":
            cancel_card = KyroContainer(accent_color=None)
            cancel_card.add_text("**Cancelled:** Banner update aborted.")
            await send_container_response(interaction.channel, cancel_card)
            return

        img_url = None
        if msg.attachments:
            img_url = msg.attachments[0].url
        elif msg.content.strip().startswith("http"):
            img_url = msg.content.strip()

        if not img_url:
            err_card = KyroContainer(accent_color=None)
            err_card.add_text("**Error:** No valid banner image attachment or URL found.")
            await send_container_response(interaction.channel, err_card)
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(img_url) as resp:
                    if resp.status != 200:
                        err_card = KyroContainer(accent_color=None)
                        err_card.add_text(f"**Error:** Could not download banner image (HTTP {resp.status}).")
                        await send_container_response(interaction.channel, err_card)
                        return
                    img_bytes = await resp.read()

            await self.bot.user.edit(banner=img_bytes)
            success_card = KyroContainer(accent_color=None)
            success_card.add_section(
                content=(
                    "**Bot Banner Updated**\n"
                    "> **Status:** `Live Banner Applied Successfully`"
                )
            )
            success_card.add_separator(divider=True)
            success_card.add_text("-# Powered by Kyro Studio")
            await send_container_response(interaction.channel, success_card)
        except discord.HTTPException as e:
            err_card = KyroContainer(accent_color=None)
            err_card.add_text(f"**Failed to update banner:** `{e}`")
            await send_container_response(interaction.channel, err_card)

    @discord.ui.button(label="Edit Name", style=discord.ButtonStyle.secondary, custom_id="btn_botedit_name")
    async def btn_name(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        prompt_card = KyroContainer(accent_color=None)
        prompt_card.add_section(
            content=(
                "**Edit Bot Username**\n"
                "> Type the new bot username in this channel.\n"
                "> Type `cancel` to abort."
            )
        )
        prompt_card.add_separator(divider=True)
        prompt_card.add_text("-# Waiting for input • 60s timeout")
        await send_container_response(interaction, prompt_card, ephemeral=True)

        def check(m: discord.Message) -> bool:
            return m.author.id == self.author_id and m.channel.id == self.channel_id

        try:
            msg: discord.Message = await self.bot.wait_for("message", check=check, timeout=60.0)
        except asyncio.TimeoutError:
            timeout_card = KyroContainer(accent_color=None)
            timeout_card.add_text("**Username Update Timed Out:** No input received within 60 seconds.")
            await send_container_response(interaction.channel, timeout_card)
            return

        name_val = msg.content.strip()
        if name_val.lower() == "cancel":
            cancel_card = KyroContainer(accent_color=None)
            cancel_card.add_text("**Cancelled:** Username update aborted.")
            await send_container_response(interaction.channel, cancel_card)
            return

        if len(name_val) < 2 or len(name_val) > 32:
            err_card = KyroContainer(accent_color=None)
            err_card.add_text("**Error:** Username must be between 2 and 32 characters.")
            await send_container_response(interaction.channel, err_card)
            return

        try:
            await self.bot.user.edit(username=name_val)
            success_card = KyroContainer(accent_color=None)
            success_card.add_section(
                content=(
                    f"**Bot Username Updated**\n"
                    f"> **New Username:** `{name_val}`\n"
                    f"> **Status:** `Applied Across Network`"
                )
            )
            success_card.add_separator(divider=True)
            success_card.add_text("-# Powered by Kyro Studio")
            await send_container_response(interaction.channel, success_card)
        except discord.HTTPException as e:
            err_card = KyroContainer(accent_color=None)
            err_card.add_text(
                f"**Failed to update username:** `{e}`\n"
                f"-# Note: Discord restricts bot name changes to 2 times per hour."
            )
            await send_container_response(interaction.channel, err_card)

    @discord.ui.button(label="Edit Status", style=discord.ButtonStyle.secondary, custom_id="btn_botedit_status")
    async def btn_status(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        prompt_card = KyroContainer(accent_color=None)
        prompt_card.add_section(
            content=(
                "**Edit Bot Status**\n"
                "> Type the new activity/status text in this channel (e.g. `Listening to ?help`).\n"
                "> Type `cancel` to abort."
            )
        )
        prompt_card.add_separator(divider=True)
        prompt_card.add_text("-# Waiting for input • 60s timeout")
        await send_container_response(interaction, prompt_card, ephemeral=True)

        def check(m: discord.Message) -> bool:
            return m.author.id == self.author_id and m.channel.id == self.channel_id

        try:
            msg: discord.Message = await self.bot.wait_for("message", check=check, timeout=60.0)
        except asyncio.TimeoutError:
            timeout_card = KyroContainer(accent_color=None)
            timeout_card.add_text("**Status Update Timed Out:** No input received within 60 seconds.")
            await send_container_response(interaction.channel, timeout_card)
            return

        text_val = msg.content.strip()
        if text_val.lower() == "cancel":
            cancel_card = KyroContainer(accent_color=None)
            cancel_card.add_text("**Cancelled:** Status update aborted.")
            await send_container_response(interaction.channel, cancel_card)
            return

        is_reset = text_val.lower() in ("reset", "default", "none")
        target_text = f"Listening to {Config.DEFAULT_PREFIX}help" if is_reset else text_val

        try:
            self.bot.custom_status = None if is_reset else text_val
            if is_reset:
                await self.bot.db.execute("DELETE FROM system_state WHERE key = 'bot_status';")
            else:
                await self.bot.db.execute(
                    "INSERT INTO system_state (key, value) VALUES ('bot_status', $1) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;",
                    text_val,
                )

            await self.bot.change_presence(
                status=discord.Status.dnd,
                activity=discord.CustomActivity(name=target_text),
            )
            success_card = KyroContainer(accent_color=None)
            success_card.add_section(
                content=(
                    f"**Bot Activity Status Updated**\n"
                    f"> **Activity:** `{target_text}`\n"
                    f"> **Mode:** `Do Not Disturb (DND)`\n"
                    f"> **Persistence:** `Active & Saved to Database`"
                )
            )
            success_card.add_separator(divider=True)
            success_card.add_text("-# Powered by Kyro Studio")
            await send_container_response(interaction.channel, success_card)
        except Exception as e:
            err_card = KyroContainer(accent_color=None)
            err_card.add_text(f"**Failed to update status:** `{e}`")
            await send_container_response(interaction.channel, err_card)


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
        description="Interactive Bot Identity & Persona console with Embed prompts.",
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
            f"> `?botedit avatar <url>` • `?botedit banner <url>` • `?botedit name <name>` • `?botedit status <text>`\n\n"
            f"-# Root Identity Customization • Instant Live Effect"
        )

        view = BotEditView(self.bot, ctx.author.id, ctx.channel.id)
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
            container.add_text("**Error:** Provide an image URL or attach an image to your message.\n> Example: `?botedit avatar <url>`")
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
            container.add_separator(divider=True)
            container.add_text("-# Powered by Kyro Studio")
            await send_container_response(ctx, container)
        except discord.HTTPException as e:
            container = KyroContainer(accent_color=None)
            container.add_text(
                f"**Failed to update avatar:** `{e}`\n"
                f"-# Note: Discord restricts avatar changes to 2 times per 10 minutes."
            )
            await send_container_response(ctx, container)

    @botedit.command(name="banner")
    @is_developer()
    async def edit_banner(self, ctx: CustomContext, url: Optional[str] = None) -> None:
        """Update bot banner via direct URL or attached image."""
        img_url = url

        # Check attachment if no URL provided
        if not img_url and ctx.message.attachments:
            img_url = ctx.message.attachments[0].url

        if not img_url:
            container = KyroContainer(accent_color=None)
            container.add_text("**Error:** Provide an image URL or attach a banner image to your message.\n> Example: `?botedit banner <url>`")
            await send_container_response(ctx, container)
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(img_url) as resp:
                    if resp.status != 200:
                        await ctx.send_error(f"Failed to fetch image: HTTP {resp.status}")
                        return
                    img_bytes = await resp.read()

            await self.bot.user.edit(banner=img_bytes)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Bot Banner Updated**\n"
                    f"> **Status:** `Live Banner Applied Successfully`"
                ),
            )
            container.add_separator(divider=True)
            container.add_text("-# Powered by Kyro Studio")
            await send_container_response(ctx, container)
        except discord.HTTPException as e:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Failed to update banner:** `{e}`")
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
        is_reset = clean_status.lower() in ("reset", "default", "none")
        target_text = f"Listening to {Config.DEFAULT_PREFIX}help" if is_reset else clean_status

        try:
            self.bot.custom_status = None if is_reset else clean_status
            if is_reset:
                await self.bot.db.execute("DELETE FROM system_state WHERE key = 'bot_status';")
            else:
                await self.bot.db.execute(
                    "INSERT INTO system_state (key, value) VALUES ('bot_status', $1) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;",
                    clean_status,
                )

            await self.bot.change_presence(
                status=discord.Status.dnd,
                activity=discord.CustomActivity(name=target_text),
            )
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Bot Activity Status Updated**\n"
                    f"> **Activity:** `{target_text}`\n"
                    f"> **Mode:** `Do Not Disturb (DND)`\n"
                    f"> **Persistence:** `Active & Saved to Database`"
                )
            )
            container.add_separator(divider=True)
            container.add_text("-# Powered by Kyro Studio")
            await send_container_response(ctx, container)
        except Exception as e:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Failed to update status:** `{e}`")
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(IdentityCog(bot))
