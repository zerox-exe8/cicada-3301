"""
Kyro Discord Bot - Interactive Steal Studio
Allows server managers to steal emojis and stickers from messages, replies, or chat history
using an interactive Discord Components V2 Dashboard with real-time thumbnail previews and in-place edits.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from typing import TYPE_CHECKING, Optional, List
from dataclasses import dataclass

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageSequence

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Utility.Steal")

# Discord custom emoji regex: <:name:id> or <a:name:id>
EMOJI_REGEX = re.compile(r"<(a)?:([a-zA-Z0-9_]{2,32}):([0-9]{17,20})>")
# Standard direct image/gif URL regex
URL_REGEX = re.compile(r"https?://\S+\.(?:png|jpe?g|gif|webp)(?:\?\S*)?", re.IGNORECASE)


@dataclass
class StealTarget:
    """Structure holding discovered emoji, sticker, or image metadata."""
    name: str
    url: str
    is_animated: bool
    is_sticker: bool = False
    sticker_id: Optional[int] = None
    custom_name: Optional[str] = None


def sanitize_name(name: str, max_len: int = 32) -> str:
    """Clean a string so it adheres to Discord's alphanumeric naming rules (2-32 for emojis, 2-30 for stickers)."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    cleaned = cleaned.strip("_")
    if len(cleaned) < 2:
        cleaned = f"item_{cleaned}" if cleaned else "stolen_item"
    return cleaned[:max_len]


async def fetch_and_compress_image(
    session: aiohttp.ClientSession, url: str, is_sticker: bool = False
) -> bytes:
    """Fetch image bytes from URL and compress with PIL if exceeding Discord size limits."""
    headers = {"User-Agent": "KyroBot/2.0 (Discord Bot)"}
    async with session.get(url, headers=headers) as resp:
        if resp.status != 200:
            raise ValueError(f"Failed to download asset from Discord CDN (HTTP {resp.status})")
        data = await resp.read()

    max_size = 512 * 1024 if is_sticker else 256 * 1024

    # If within limits and not requiring special sticker dimensions, return as is
    if len(data) <= max_size and not is_sticker and not url.lower().endswith(".webp"):
        return data

    def _process_sync() -> bytes:
        img = Image.open(io.BytesIO(data))
        out = io.BytesIO()

        if is_sticker:
            # Discord stickers must be exactly 320x320 pixels PNG
            img = img.convert("RGBA")
            img = img.resize((320, 320), Image.Resampling.LANCZOS)
            img.save(out, format="PNG", optimize=True)
            return out.getvalue()

        # Handle animated GIFs compression
        if getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1:
            frames = []
            durations = []
            for frame in ImageSequence.Iterator(img):
                f = frame.convert("RGBA")
                f.thumbnail((128, 128), Image.Resampling.LANCZOS)
                frames.append(f)
                durations.append(frame.info.get("duration", 100))

            frames[0].save(
                out,
                format="GIF",
                save_all=True,
                append_images=frames[1:],
                duration=durations,
                loop=img.info.get("loop", 0),
                optimize=True,
            )
            val = out.getvalue()
            # If still exceeds 256KB, reduce resolution iteratively
            if len(val) > max_size:
                out = io.BytesIO()
                reduced_frames = [f.resize((96, 96), Image.Resampling.NEAREST) for f in frames]
                reduced_frames[0].save(
                    out,
                    format="GIF",
                    save_all=True,
                    append_images=reduced_frames[1:],
                    duration=durations,
                    loop=img.info.get("loop", 0),
                    optimize=True,
                )
                val = out.getvalue()
            return val

        # Handle static image (convert WebP/JPG/PNG to optimized PNG)
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            img = img.convert("RGBA")
        else:
            img = img.convert("RGB")

        img.thumbnail((128, 128), Image.Resampling.LANCZOS)
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _process_sync)


class StealDashboardView(discord.ui.View):
    """Interactive Discord Components V2 Studio for stealing emojis and stickers with live in-place edits."""

    def __init__(
        self,
        bot: KyroBot,
        author: discord.Member | discord.User,
        guild: discord.Guild,
        emojis: list[StealTarget],
        stickers: list[StealTarget],
        timeout: float = 120.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author = author
        self.guild = guild
        self.emojis = emojis
        self.stickers = stickers
        self.message: Optional[discord.Message] = None

        # Track active selection index
        self.current_emoji_idx = 0
        self.current_sticker_idx = 0

        self._build_components()

    def _build_components(self) -> None:
        """Construct interactive buttons and selection menus based on discovered targets."""
        self.clear_items()

        # If multiple emojis exist, show a selection dropdown
        if len(self.emojis) > 1:
            options = []
            for i, em in enumerate(self.emojis[:25]):
                type_label = "Animated GIF" if em.is_animated else "Static PNG"
                options.append(
                    discord.SelectOption(
                        label=f"{em.name[:25]}",
                        description=f"Type: {type_label}",
                        value=str(i),
                        default=(i == self.current_emoji_idx),
                    )
                )
            select = discord.ui.Select(
                placeholder="Choose specific emoji to preview & steal...",
                min_values=1,
                max_values=1,
                options=options,
                row=0,
            )
            select.callback = self._on_select_emoji
            self.add_item(select)

        # Main Action Buttons
        row = 1 if len(self.emojis) > 1 else 0

        if self.emojis:
            active_emoji = self.emojis[self.current_emoji_idx]
            btn_emoji = discord.ui.Button(
                label=f"Steal Emoji ({active_emoji.name[:18]})",
                style=discord.ButtonStyle.success,
                custom_id="btn_steal_emoji",
                emoji="📥",
                row=row,
            )
            btn_emoji.callback = self._on_steal_emoji
            self.add_item(btn_emoji)

        if self.stickers:
            active_sticker = self.stickers[self.current_sticker_idx]
            btn_sticker = discord.ui.Button(
                label=f"Steal Sticker ({active_sticker.name[:18]})",
                style=discord.ButtonStyle.primary,
                custom_id="btn_steal_sticker",
                emoji="🏷️",
                row=row,
            )
            btn_sticker.callback = self._on_steal_sticker
            self.add_item(btn_sticker)

        # Steal All button if multiple emojis are discovered
        if len(self.emojis) > 1:
            btn_all = discord.ui.Button(
                label=f"Steal All ({len(self.emojis)} Emojis)",
                style=discord.ButtonStyle.secondary,
                custom_id="btn_steal_all",
                emoji="⚡",
                row=row + 1,
            )
            btn_all.callback = self._on_steal_all
            self.add_item(btn_all)

        # Cancel Button
        btn_cancel = discord.ui.Button(
            label="Cancel",
            style=discord.ButtonStyle.secondary,
            custom_id="btn_cancel",
            row=row + 1 if len(self.emojis) > 1 else row,
        )
        btn_cancel.callback = self._on_cancel
        self.add_item(btn_cancel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforce author-lock: only the invoker can interact with the studio."""
        if interaction.user.id != self.author.id:
            e_reg = getattr(self.bot, "custom_emojis", None)
            err_icon = e_reg.get("icons_wrong", "") if e_reg else ""
            await interaction.response.send_message(
                f"{err_icon} Only {self.author.mention} can interact with this Steal Studio.",
                ephemeral=True,
            )
            return False

        if not interaction.user.guild_permissions.manage_guild_expressions:
            await interaction.response.send_message(
                "You need `Manage Expressions` permission to add emojis or stickers to this server.",
                ephemeral=True,
            )
            return False

        return True

    def _get_capacity_string(self) -> str:
        """Calculate and return formatted remaining emoji/sticker slots."""
        static_count = len([e for e in self.guild.emojis if not e.animated])
        anim_count = len([e for e in self.guild.emojis if e.animated])
        sticker_count = len(self.guild.stickers)
        limit = self.guild.emoji_limit
        s_limit = getattr(self.guild, "sticker_limit", 5)

        return (
            f"• **Static Slots:** `{static_count}/{limit}`\n"
            f"• **Animated Slots:** `{anim_count}/{limit}`\n"
            f"• **Sticker Slots:** `{sticker_count}/{s_limit}`"
        )

    def build_initial_container(self) -> KyroContainer:
        """Build the primary visual Components V2 dashboard with image thumbnail preview."""
        container = KyroContainer(accent_color=None)

        # Determine prominent preview item (selected emoji or sticker)
        target_preview = self.emojis[self.current_emoji_idx] if self.emojis else (self.stickers[0] if self.stickers else None)
        preview_url = target_preview.url if target_preview else None

        disc_items = []
        if self.emojis:
            disc_items.append(f"**{len(self.emojis)} Emoji(s)**")
        if self.stickers:
            disc_items.append(f"**{len(self.stickers)} Sticker(s)**")
        found_text = ", ".join(disc_items) if disc_items else "Expression"

        current_name = target_preview.name if target_preview else "Unknown"
        current_type = "Custom Sticker" if (target_preview and target_preview.is_sticker) else ("Animated GIF" if (target_preview and target_preview.is_animated) else "Static PNG")

        header_content = (
            f"### Steal Studio\n"
            f"> Discovered **{found_text}** ready to be added to **{self.guild.name}**.\n"
            f"> Preview is displayed in the card accessory."
        )

        # Section with Accessory Thumbnail showing the actual emoji/sticker image
        if preview_url:
            container.add_section(
                content=header_content,
                accessory={
                    "type": 11,
                    "media": {"url": preview_url},
                },
            )
        else:
            container.add_section(content=header_content)

        container.add_separator(divider=True)

        container.add_text(
            f"• **Active Selection:** `{current_name}` ({current_type})\n\n"
            f"**Server Capacity:**\n"
            f"{self._get_capacity_string()}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.author.display_name} • Click a button below to steal")

        return container

    async def _on_select_emoji(self, interaction: discord.Interaction) -> None:
        """Fired when user changes the active emoji in the dropdown."""
        self.current_emoji_idx = int(interaction.data["values"][0])
        self._build_components()
        await edit_container_response(interaction, self.build_initial_container(), view=self)

    async def _on_steal_emoji(self, interaction: discord.Interaction) -> None:
        """Handle individual emoji steal with live in-place edit."""
        await interaction.response.defer()
        target = self.emojis[self.current_emoji_idx]
        final_name = sanitize_name(target.custom_name or target.name, max_len=32)

        # Check server capacity limits
        static_count = len([e for e in self.guild.emojis if not e.animated])
        anim_count = len([e for e in self.guild.emojis if e.animated])
        limit = self.guild.emoji_limit

        if target.is_animated and anim_count >= limit:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Server Capacity Reached**\n> All `{limit}` animated emoji slots in **{self.guild.name}** are occupied.")
            await edit_container_response(interaction, container, view=None)
            return

        if not target.is_animated and static_count >= limit:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Server Capacity Reached**\n> All `{limit}` static emoji slots in **{self.guild.name}** are occupied.")
            await edit_container_response(interaction, container, view=None)
            return

        try:
            session = self.bot.session or aiohttp.ClientSession()
            img_bytes = await fetch_and_compress_image(session, target.url, is_sticker=False)
            new_emoji = await self.guild.create_custom_emoji(
                name=final_name,
                image=img_bytes,
                reason=f"Kyro Steal executed by {interaction.user} (ID: {interaction.user.id})",
            )
        except discord.Forbidden:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Permission Denied**\n> I do not have `Manage Expressions` permission or my role is positioned too low.")
            await edit_container_response(interaction, container, view=None)
            return
        except discord.HTTPException as e:
            logger.error(f"Failed to create emoji {final_name}: {e}")
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Upload Failed**\n> Discord rejected the emoji: `{e.text or e}`")
            await edit_container_response(interaction, container, view=None)
            return
        except Exception as e:
            logger.error(f"Error processing emoji {final_name}: {e}", exc_info=e)
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Processing Error**\n> Failed to download or convert emoji image: `{e}`")
            await edit_container_response(interaction, container, view=None)
            return

        # Build Success Container with Live Preview
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Emoji Added Successfully\n"
                f"> **{new_emoji}** is now available for all members in **{self.guild.name}**!"
            ),
            accessory={
                "type": 11,
                "media": {"url": new_emoji.url},
            },
        )
        container.add_separator(divider=True)
        container.add_text(
            f"• **Live Emoji:** {new_emoji}\n"
            f"• **Name:** `{new_emoji.name}`\n"
            f"• **Type:** `{'Animated GIF' if new_emoji.animated else 'Static PNG'}`\n\n"
            f"**Updated Server Capacity:**\n"
            f"{self._get_capacity_string()}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Successfully added by {interaction.user.display_name}")

        # Disable the clicked button to indicate completion
        self.clear_items()
        done_btn = discord.ui.Button(
            label="Added to Server",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            emoji="✅",
        )
        self.add_item(done_btn)

        # Allow viewing full CDN asset
        cdn_btn = discord.ui.Button(
            label="View Asset CDN",
            style=discord.ButtonStyle.link,
            url=new_emoji.url,
        )
        self.add_item(cdn_btn)

        await edit_container_response(interaction, container, view=self)

    async def _on_steal_sticker(self, interaction: discord.Interaction) -> None:
        """Handle individual sticker steal with live in-place edit."""
        await interaction.response.defer()
        target = self.stickers[self.current_sticker_idx]
        final_name = sanitize_name(target.custom_name or target.name, max_len=30)

        sticker_count = len(self.guild.stickers)
        s_limit = getattr(self.guild, "sticker_limit", 5)

        if sticker_count >= s_limit:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Sticker Limit Reached**\n> All `{s_limit}` custom sticker slots in **{self.guild.name}** are occupied.")
            await edit_container_response(interaction, container, view=None)
            return

        try:
            session = self.bot.session or aiohttp.ClientSession()
            sticker_bytes = await fetch_and_compress_image(session, target.url, is_sticker=True)
            sticker_file = discord.File(io.BytesIO(sticker_bytes), filename=f"{final_name}.png")

            new_sticker = await self.guild.create_sticker(
                name=final_name,
                description=f"Stolen with Kyro by {interaction.user.name}",
                emoji="⭐",
                file=sticker_file,
                reason=f"Kyro Steal executed by {interaction.user} (ID: {interaction.user.id})",
            )
        except discord.Forbidden:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Permission Denied**\n> I do not have `Manage Expressions` permission or my role is positioned too low.")
            await edit_container_response(interaction, container, view=None)
            return
        except discord.HTTPException as e:
            logger.error(f"Failed to create sticker {final_name}: {e}")
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Upload Failed**\n> Discord rejected the sticker: `{e.text or e}`")
            await edit_container_response(interaction, container, view=None)
            return
        except Exception as e:
            logger.error(f"Error processing sticker {final_name}: {e}", exc_info=e)
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Processing Error**\n> Failed to download or convert sticker image: `{e}`")
            await edit_container_response(interaction, container, view=None)
            return

        # Build Success Container
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Sticker Added Successfully\n"
                f"> Sticker **{new_sticker.name}** is now available in **{self.guild.name}**!"
            ),
            accessory={
                "type": 11,
                "media": {"url": new_sticker.url},
            },
        )
        container.add_separator(divider=True)
        container.add_text(
            f"• **Sticker Name:** `{new_sticker.name}`\n"
            f"• **Format:** `Custom PNG (320x320)`\n\n"
            f"**Updated Server Capacity:**\n"
            f"{self._get_capacity_string()}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Successfully added by {interaction.user.display_name}")

        self.clear_items()
        done_btn = discord.ui.Button(
            label="Sticker Added",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            emoji="✅",
        )
        self.add_item(done_btn)

        cdn_btn = discord.ui.Button(
            label="View Asset CDN",
            style=discord.ButtonStyle.link,
            url=new_sticker.url,
        )
        self.add_item(cdn_btn)

        await edit_container_response(interaction, container, view=self)

    async def _on_steal_all(self, interaction: discord.Interaction) -> None:
        """Batch steal all discovered emojis with rate-limit pacing."""
        await interaction.response.defer()

        session = self.bot.session or aiohttp.ClientSession()
        uploaded_emojis: list[discord.Emoji] = []
        limit = self.guild.emoji_limit

        for em in self.emojis:
            static_count = len([e for e in self.guild.emojis if not e.animated])
            anim_count = len([e for e in self.guild.emojis if e.animated])

            if em.is_animated and anim_count >= limit:
                break
            if not em.is_animated and static_count >= limit:
                break

            final_name = sanitize_name(em.name, max_len=32)
            try:
                img_bytes = await fetch_and_compress_image(session, em.url, is_sticker=False)
                new_emoji = await self.guild.create_custom_emoji(
                    name=final_name,
                    image=img_bytes,
                    reason=f"Kyro Steal All executed by {interaction.user}",
                )
                uploaded_emojis.append(new_emoji)
                # Respect Discord rate-limit pacing
                await asyncio.sleep(1.0)
            except Exception as e:
                logger.debug(f"Could not upload emoji {final_name} in Steal All: {e}")

        container = KyroContainer(accent_color=None)
        if uploaded_emojis:
            live_icons = " ".join(str(e) for e in uploaded_emojis)
            container.add_section(
                content=(
                    f"### Bulk Steal Complete\n"
                    f"> Successfully added **{len(uploaded_emojis)}** emoji(s) to **{self.guild.name}**!\n\n"
                    f"{live_icons}"
                ),
                accessory={
                    "type": 11,
                    "media": {"url": uploaded_emojis[0].url},
                },
            )
            container.add_separator(divider=True)
            container.add_text(
                f"• **Uploaded Items:** `{len(uploaded_emojis)}/{len(self.emojis)}`\n\n"
                f"**Updated Server Capacity:**\n"
                f"{self._get_capacity_string()}"
            )
        else:
            container.add_section(
                content="**Bulk Steal Incomplete**\n> No emojis could be uploaded. Please verify remaining server slots or permissions."
            )

        container.add_separator(divider=True)
        container.add_text(f"-# Executed by {interaction.user.display_name}")

        self.clear_items()
        done_btn = discord.ui.Button(
            label=f"{len(uploaded_emojis)} Emojis Added",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            emoji="✅",
        )
        self.add_item(done_btn)

        await edit_container_response(interaction, container, view=self)

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        """Cancel steal studio and dismiss interactive controls."""
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Steal Studio Dismissed**\n> Operation was cancelled. No emojis or stickers were added.")
        self.clear_items()
        await edit_container_response(interaction, container, view=None)

    async def on_timeout(self) -> None:
        """Disable buttons upon inactivity timeout."""
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True
        if self.message:
            try:
                container = self.build_initial_container()
                container.add_separator(divider=True)
                container.add_text("-# *This Steal Studio has expired due to inactivity.*")
                await edit_container_response(self.message, container, view=self)
            except Exception:
                pass


class Steal(commands.Cog):
    """Interactive expression stealing suite powered by Discord Components V2 Studio."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(
        name="steal",
        aliases=["stealemoji", "stealsticker", "addemoji"],
        description="Open interactive Steal Studio to add emojis or stickers from messages, replies, or chat.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild_expressions=True)
    @commands.bot_has_permissions(manage_guild_expressions=True)
    async def steal_command(
        self,
        ctx: CustomContext,
        target_input: Optional[str] = None,
        custom_name: Optional[str] = None,
    ) -> None:
        """
        Open the interactive Steal Studio Dashboard.
        
        Usage:
          ?steal <:pepe:123456789>          -> Opens Steal Studio with image preview
          ?steal <:pepe:123456789> my_pepe  -> Steals with custom name
          ?steal (reply to any message)    -> Automatically extracts emojis & stickers from replied message
          ?steal                           -> Scans recent channel messages for custom emojis/stickers
        """
        assert ctx.guild is not None

        raw_emojis: list[StealTarget] = []
        raw_stickers: list[StealTarget] = []

        # 1. Check if user replied to another message
        ref = ctx.message.reference
        if ref and ref.resolved and isinstance(ref.resolved, discord.Message):
            ref_msg: discord.Message = ref.resolved

            # Extract custom emojis from replied content
            for match in EMOJI_REGEX.finditer(ref_msg.content):
                is_anim = bool(match.group(1))
                e_name = match.group(2)
                e_id = int(match.group(3))
                ext = "gif" if is_anim else "png"
                e_url = f"https://cdn.discordapp.com/emojis/{e_id}.{ext}?size=256&quality=lossless"
                raw_emojis.append(StealTarget(name=e_name, url=e_url, is_animated=is_anim, custom_name=target_input if not custom_name else custom_name))

            # Extract stickers from replied message (exclude Lottie JSON vectors as Discord API only permits PNG/APNG)
            if ref_msg.stickers:
                for st in ref_msg.stickers:
                    if getattr(st, "format", None) == discord.StickerFormatType.lottie:
                        continue
                    st_url = f"https://cdn.discordapp.com/stickers/{st.id}.png?size=320"
                    raw_stickers.append(
                        StealTarget(
                            name=st.name,
                            url=st_url,
                            is_animated=(st.format == discord.StickerFormatType.apng),
                            is_sticker=True,
                            sticker_id=st.id,
                            custom_name=target_input if not custom_name else custom_name,
                        )
                    )

            # Extract image attachments if present
            for att in ref_msg.attachments:
                if att.content_type and any(att.content_type.startswith(x) for x in ("image/png", "image/jpeg", "image/gif", "image/webp")):
                    is_gif = "gif" in att.content_type
                    att_name = att.filename.rsplit(".", 1)[0]
                    raw_emojis.append(
                        StealTarget(
                            name=att_name,
                            url=att.url,
                            is_animated=is_gif,
                            custom_name=target_input if not custom_name else custom_name,
                        )
                    )

        # 2. Check direct command inputs if no items extracted from reply
        if not raw_emojis and not raw_stickers and target_input:
            # Check for custom emojis in arguments
            for match in EMOJI_REGEX.finditer(ctx.message.content):
                is_anim = bool(match.group(1))
                e_name = match.group(2)
                e_id = int(match.group(3))
                ext = "gif" if is_anim else "png"
                e_url = f"https://cdn.discordapp.com/emojis/{e_id}.{ext}?size=256&quality=lossless"
                raw_emojis.append(StealTarget(name=e_name, url=e_url, is_animated=is_anim, custom_name=custom_name))

            # Check for direct image/gif URLs
            if not raw_emojis:
                for match in URL_REGEX.finditer(ctx.message.content):
                    url_found = match.group(0)
                    is_gif = ".gif" in url_found.lower()
                    guessed_name = custom_name or url_found.split("/")[-1].split(".")[0]
                    raw_emojis.append(StealTarget(name=guessed_name, url=url_found, is_animated=is_gif, custom_name=custom_name))

        # 3. If still no targets found, scan recent channel message history
        if not raw_emojis and not raw_stickers:
            async for old_msg in ctx.channel.history(limit=15):
                if old_msg.id == ctx.message.id:
                    continue
                # Emojis in past message
                for match in EMOJI_REGEX.finditer(old_msg.content):
                    is_anim = bool(match.group(1))
                    e_name = match.group(2)
                    e_id = int(match.group(3))
                    ext = "gif" if is_anim else "png"
                    e_url = f"https://cdn.discordapp.com/emojis/{e_id}.{ext}?size=256&quality=lossless"
                    raw_emojis.append(StealTarget(name=e_name, url=e_url, is_animated=is_anim))
                    break

                # Stickers in past message
                if old_msg.stickers:
                    st = old_msg.stickers[0]
                    if getattr(st, "format", None) != discord.StickerFormatType.lottie:
                        st_url = f"https://cdn.discordapp.com/stickers/{st.id}.png?size=320"
                        raw_stickers.append(
                            StealTarget(
                                name=st.name,
                                url=st_url,
                                is_animated=(st.format == discord.StickerFormatType.apng),
                                is_sticker=True,
                                sticker_id=st.id,
                            )
                        )
                        break

                if raw_emojis or raw_stickers:
                    break

        # 4. Deduplicate items by URL
        seen_urls: set[str] = set()
        emojis: list[StealTarget] = []
        for em in raw_emojis:
            if em.url not in seen_urls:
                seen_urls.add(em.url)
                emojis.append(em)

        stickers: list[StealTarget] = []
        for st in raw_stickers:
            if st.url not in seen_urls:
                seen_urls.add(st.url)
                stickers.append(st)

        # 5. Check if user provided only standard Unicode emoji
        if not emojis and not stickers and target_input:
            import unicodedata
            has_unicode = any(unicodedata.category(c).startswith("S") for c in target_input)
            if has_unicode and not target_input.startswith("<"):
                container = KyroContainer(accent_color=None)
                container.add_section(
                    content=(
                        "**Standard Unicode Emoji Detected**\n"
                        f"> The emoji `{target_input}` is a built-in default Unicode emoji.\n"
                        "> Discord only allows uploading **custom server emojis** (e.g. `<:name:id>`), custom stickers, or image links."
                    )
                )
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container)
                return

        # 6. If absolutely nothing found, show guidance card
        if not emojis and not stickers:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Steal Studio — No Target Found**\n"
                    "> Could not detect any custom emojis, stickers, or image URLs.\n\n"
                    "**How to use:**\n"
                    f"• Reply to any message containing an emoji/sticker with `{ctx.prefix}steal`\n"
                    f"• Provide an emoji directly: `{ctx.prefix}steal <:pepe:123456789>`\n"
                    f"• Provide an image/GIF link: `{ctx.prefix}steal https://example.com/icon.gif [name]`"
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        # 7. Launch interactive Steal Studio Dashboard
        view = StealDashboardView(
            bot=self.bot,
            author=ctx.author,
            guild=ctx.guild,
            emojis=emojis,
            stickers=stickers,
        )
        initial_container = view.build_initial_container()
        msg = await send_container_response(ctx, initial_container, view=view)
        view.message = msg


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Steal(bot))
