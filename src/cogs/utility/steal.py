"""
Kyro Discord Bot - Interactive Steal Studio
Smart expression stealer with:
- Duplicate detection (already exists in server check)
- Name collision auto-renaming (pepe -> pepe_1)
- Dynamic slot capacity calculations (Static/Animated/Stickers)
- Clean, compact Components V2 card with two always-active buttons: [Emoji] and [Sticker]
- Custom heart_dot emoji styling and in-place live edits
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from typing import TYPE_CHECKING, Optional
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
    source_id: Optional[int] = None
    custom_name: Optional[str] = None


def sanitize_name(name: str, max_len: int = 32) -> str:
    """Clean a string so it adheres to Discord's alphanumeric naming rules."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_")
    if len(cleaned) < 2:
        cleaned = f"item_{cleaned}" if cleaned else "stolen_item"
    return cleaned[:max_len]


def resolve_unique_name(base_name: str, existing_names: set[str], max_len: int = 32) -> str:
    """If a name already exists in the server, append _1, _2 to prevent autocomplete confusion."""
    cleaned = sanitize_name(base_name, max_len=max_len)
    if cleaned.lower() not in existing_names:
        return cleaned

    counter = 1
    while True:
        suffix = f"_{counter}"
        available_len = max_len - len(suffix)
        candidate = f"{cleaned[:available_len]}{suffix}"
        if candidate.lower() not in existing_names:
            return candidate
        counter += 1


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

        # Handle static image
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
    """Clean view with [Emoji] and [Sticker] buttons and duplicate detection."""

    def __init__(
        self,
        bot: KyroBot,
        author: discord.Member | discord.User,
        guild: discord.Guild,
        target: StealTarget,
        timeout: float = 90.0,
    ) -> None:
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author = author
        self.guild = guild
        self.target = target
        self.message: Optional[discord.Message] = None

        self._build_buttons()

    def _build_buttons(self) -> None:
        """Both buttons (Emoji and Sticker) are always present."""
        self.clear_items()

        btn_emoji = discord.ui.Button(
            label="Emoji",
            style=discord.ButtonStyle.secondary,
            custom_id="btn_steal_emoji",
            row=0,
        )
        btn_emoji.callback = self._on_steal_emoji
        self.add_item(btn_emoji)

        btn_sticker = discord.ui.Button(
            label="Sticker",
            style=discord.ButtonStyle.secondary,
            custom_id="btn_steal_sticker",
            row=0,
        )
        btn_sticker.callback = self._on_steal_sticker
        self.add_item(btn_sticker)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Enforce author-lock: only the command author can click."""
        if interaction.user.id != self.author.id:
            e_reg = getattr(self.bot, "custom_emojis", None)
            err_icon = e_reg.get("icons_wrong", "") if e_reg else ""
            await interaction.response.send_message(
                f"{err_icon} Only {self.author.mention} can interact with this dashboard.",
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
                "You need `Manage Expressions` permission to use this command.",
                ephemeral=True,
            )
            return False

        return True

    def _is_already_in_server(self) -> bool:
        """Check if this exact emoji or sticker is already present in this server."""
        if not self.target.source_id:
            return False
        if self.target.is_sticker:
            return any(s.id == self.target.source_id for s in self.guild.stickers)
        return any(e.id == self.target.source_id for e in self.guild.emojis)

    def build_initial_container(self) -> KyroContainer:
        """Build clean Components V2 card with thumbnail and duplicate warnings."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        dot = e_reg.get("heart_dot", "-") if e_reg else "-"
        warn_icon = e_reg.get("icons_warning", "⚠️ ") if e_reg else "⚠️ "

        preview_url = self.target.url
        target_name = self.target.name
        target_type = "Animated GIF" if self.target.is_animated else "Static Image"

        static_count = len([e for e in self.guild.emojis if not e.animated])
        anim_count = len([e for e in self.guild.emojis if e.animated])
        limit = self.guild.emoji_limit
        sticker_count = len(self.guild.stickers)
        s_limit = getattr(self.guild, "sticker_limit", 5)

        container = KyroContainer(accent_color=None)
        
        # Header text
        header_text = (
            f"**Steal Studio**\n"
            f"> Choose whether to add as **Emoji** or **Sticker**."
        )
        if self._is_already_in_server():
            header_text += f"\n> {warn_icon}*Notice: This item already exists in this server.*"

        section_kwargs = {"content": header_text}
        if preview_url:
            section_kwargs["accessory"] = {
                "type": 11,
                "media": {"url": preview_url},
            }

        container.add_section(**section_kwargs)
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Name:** `{target_name}`\n"
            f"{dot} **Type:** `{target_type}`\n"
            f"{dot} **Emoji Slots:** `{static_count}/{limit} Static` {dot} `{anim_count}/{limit} Animated`\n"
            f"{dot} **Sticker Slots:** `{sticker_count}/{s_limit}`"
        )

        return container

    async def _on_steal_emoji(self, interaction: discord.Interaction) -> None:
        """Add target as a server custom emoji with collision & capacity resolution."""
        await interaction.response.defer()

        # 1. Capacity check
        static_count = len([e for e in self.guild.emojis if not e.animated])
        anim_count = len([e for e in self.guild.emojis if e.animated])
        limit = self.guild.emoji_limit

        if self.target.is_animated and anim_count >= limit:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Slots Full**\n> All `{limit}` animated emoji slots in **{self.guild.name}** are full.")
            await edit_container_response(interaction, container, view=None)
            return

        if not self.target.is_animated and static_count >= limit:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Slots Full**\n> All `{limit}` static emoji slots in **{self.guild.name}** are occupied.")
            await edit_container_response(interaction, container, view=None)
            return

        # 2. Name collision check & auto-rename
        existing_emoji_names = {e.name.lower() for e in self.guild.emojis}
        base_name = self.target.custom_name or self.target.name
        final_name = resolve_unique_name(base_name, existing_emoji_names, max_len=32)

        try:
            session = self.bot.session or aiohttp.ClientSession()
            img_bytes = await fetch_and_compress_image(session, self.target.url, is_sticker=False)
            new_emoji = await self.guild.create_custom_emoji(
                name=final_name,
                image=img_bytes,
                reason=f"Steal executed by {interaction.user} (ID: {interaction.user.id})",
            )
        except discord.Forbidden:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Permission Denied**\n> I do not have permission to add emojis or my role is positioned too low.")
            await edit_container_response(interaction, container, view=None)
            return
        except Exception as e:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Upload Error**\n> `{e}`")
            await edit_container_response(interaction, container, view=None)
            return

        e_reg = getattr(self.bot, "custom_emojis", None)
        dot = e_reg.get("heart_dot", "-") if e_reg else "-"
        s_count = len([e for e in self.guild.emojis if not e.animated])
        a_count = len([e for e in self.guild.emojis if e.animated])

        rename_note = f" *(Auto-renamed from `{base_name}` to prevent name conflict)*" if final_name.lower() != base_name.lower() else ""

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Emoji Added Successfully**\n"
                f"> {new_emoji} is now ready to use in **{self.guild.name}**!{rename_note}"
            ),
            accessory={
                "type": 11,
                "media": {"url": new_emoji.url},
            },
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Emoji:** {new_emoji}\n"
            f"{dot} **Name:** `{new_emoji.name}`\n"
            f"{dot} **Slots:** `{s_count}/{limit} Static` {dot} `{a_count}/{limit} Animated`"
        )

        self.clear_items()
        done_btn = discord.ui.Button(
            label="Emoji Added",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            emoji="✅",
        )
        self.add_item(done_btn)

        await edit_container_response(interaction, container, view=self)

    async def _on_steal_sticker(self, interaction: discord.Interaction) -> None:
        """Add target as a server custom sticker with collision & capacity resolution."""
        await interaction.response.defer()

        # 1. Capacity check
        sticker_count = len(self.guild.stickers)
        s_limit = getattr(self.guild, "sticker_limit", 5)

        if sticker_count >= s_limit:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Sticker Slots Full**\n> All `{s_limit}` sticker slots in **{self.guild.name}** are occupied.")
            await edit_container_response(interaction, container, view=None)
            return

        # 2. Name collision check & auto-rename (max 30 chars for stickers)
        existing_sticker_names = {s.name.lower() for s in self.guild.stickers}
        base_name = self.target.custom_name or self.target.name
        final_name = resolve_unique_name(base_name, existing_sticker_names, max_len=30)

        try:
            session = self.bot.session or aiohttp.ClientSession()
            sticker_bytes = await fetch_and_compress_image(session, self.target.url, is_sticker=True)
            sticker_file = discord.File(io.BytesIO(sticker_bytes), filename=f"{final_name}.png")

            new_sticker = await self.guild.create_sticker(
                name=final_name,
                description=f"Stolen with Kyro by {interaction.user.name}",
                emoji="⭐",
                file=sticker_file,
                reason=f"Steal executed by {interaction.user} (ID: {interaction.user.id})",
            )
        except discord.Forbidden:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Permission Denied**\n> I do not have permission to add stickers or my role is positioned too low.")
            await edit_container_response(interaction, container, view=None)
            return
        except Exception as e:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Upload Error**\n> `{e}`")
            await edit_container_response(interaction, container, view=None)
            return

        e_reg = getattr(self.bot, "custom_emojis", None)
        dot = e_reg.get("heart_dot", "-") if e_reg else "-"
        s_count = len(self.guild.stickers)

        rename_note = f" *(Auto-renamed from `{base_name}` to prevent name conflict)*" if final_name.lower() != base_name.lower() else ""

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Sticker Added Successfully**\n"
                f"> Sticker **{new_sticker.name}** is now available in **{self.guild.name}**!{rename_note}"
            ),
            accessory={
                "type": 11,
                "media": {"url": new_sticker.url},
            },
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Name:** `{new_sticker.name}`\n"
            f"{dot} **Type:** `Custom PNG (320x320)`\n"
            f"{dot} **Sticker Slots:** `{s_count}/{s_limit}`"
        )

        self.clear_items()
        done_btn = discord.ui.Button(
            label="Sticker Added",
            style=discord.ButtonStyle.secondary,
            disabled=True,
            emoji="✅",
        )
        self.add_item(done_btn)

        await edit_container_response(interaction, container, view=self)

    async def on_timeout(self) -> None:
        """Disable buttons upon inactivity timeout."""
        for item in self.children:
            if hasattr(item, "disabled"):
                item.disabled = True
        if self.message:
            try:
                await edit_container_response(self.message, self.build_initial_container(), view=self)
            except Exception:
                pass


class Steal(commands.Cog):
    """Interactive expression stealer with duplicate detection and name collision handling."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(
        name="steal",
        aliases=["stealemoji", "stealsticker", "addemoji"],
        description="Steal emojis or stickers with an interactive dashboard.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_expressions=True)
    @commands.bot_has_permissions(manage_expressions=True)
    async def steal_command(
        self,
        ctx: CustomContext,
        target_input: Optional[str] = None,
        custom_name: Optional[str] = None,
    ) -> None:
        """
        Interactive Steal Studio with exactly 2 buttons: [Emoji] and [Sticker].
        
        Usage:
          ?steal <:pepe:123456789>
          ?steal <:pepe:123456789> my_name
          ?steal (reply to any message with emoji/sticker)
        """
        assert ctx.guild is not None

        target: Optional[StealTarget] = None

        # 1. Check replied message
        ref = ctx.message.reference
        if ref and ref.resolved and isinstance(ref.resolved, discord.Message):
            ref_msg: discord.Message = ref.resolved

            # Check emojis in replied message
            for match in EMOJI_REGEX.finditer(ref_msg.content):
                is_anim = bool(match.group(1))
                e_name = match.group(2)
                e_id = int(match.group(3))
                ext = "gif" if is_anim else "png"
                e_url = f"https://cdn.discordapp.com/emojis/{e_id}.{ext}?size=256&quality=lossless"
                target = StealTarget(
                    name=e_name,
                    url=e_url,
                    is_animated=is_anim,
                    source_id=e_id,
                    custom_name=target_input if not custom_name else custom_name,
                )
                break

            # Check stickers in replied message if no emoji
            if not target and ref_msg.stickers:
                for st in ref_msg.stickers:
                    if getattr(st, "format", None) == discord.StickerFormatType.lottie:
                        continue
                    st_url = f"https://cdn.discordapp.com/stickers/{st.id}.png?size=320"
                    target = StealTarget(
                        name=st.name,
                        url=st_url,
                        is_animated=(st.format == discord.StickerFormatType.apng),
                        is_sticker=True,
                        source_id=st.id,
                        custom_name=target_input if not custom_name else custom_name,
                    )
                    break

            # Check image attachments in replied message
            if not target:
                for att in ref_msg.attachments:
                    if att.content_type and any(att.content_type.startswith(x) for x in ("image/png", "image/jpeg", "image/gif", "image/webp")):
                        is_gif = "gif" in att.content_type
                        att_name = att.filename.rsplit(".", 1)[0]
                        target = StealTarget(
                            name=att_name,
                            url=att.url,
                            is_animated=is_gif,
                            source_id=att.id,
                            custom_name=target_input if not custom_name else custom_name,
                        )
                        break

        # 2. Check direct command arguments
        if not target and target_input:
            for match in EMOJI_REGEX.finditer(ctx.message.content):
                is_anim = bool(match.group(1))
                e_name = match.group(2)
                e_id = int(match.group(3))
                ext = "gif" if is_anim else "png"
                e_url = f"https://cdn.discordapp.com/emojis/{e_id}.{ext}?size=256&quality=lossless"
                target = StealTarget(
                    name=e_name,
                    url=e_url,
                    is_animated=is_anim,
                    source_id=e_id,
                    custom_name=custom_name,
                )
                break

            if not target:
                for match in URL_REGEX.finditer(ctx.message.content):
                    url_found = match.group(0)
                    is_gif = ".gif" in url_found.lower()
                    guessed_name = custom_name or url_found.split("/")[-1].split(".")[0]
                    target = StealTarget(name=guessed_name, url=url_found, is_animated=is_gif, custom_name=custom_name)
                    break

        # 3. Scan recent channel history if still not found
        if not target:
            async for old_msg in ctx.channel.history(limit=15):
                if old_msg.id == ctx.message.id:
                    continue
                for match in EMOJI_REGEX.finditer(old_msg.content):
                    is_anim = bool(match.group(1))
                    e_name = match.group(2)
                    e_id = int(match.group(3))
                    ext = "gif" if is_anim else "png"
                    e_url = f"https://cdn.discordapp.com/emojis/{e_id}.{ext}?size=256&quality=lossless"
                    target = StealTarget(name=e_name, url=e_url, is_animated=is_anim, source_id=e_id)
                    break

                if not target and old_msg.stickers:
                    st = old_msg.stickers[0]
                    if getattr(st, "format", None) != discord.StickerFormatType.lottie:
                        st_url = f"https://cdn.discordapp.com/stickers/{st.id}.png?size=320"
                        target = StealTarget(
                            name=st.name,
                            url=st_url,
                            is_animated=(st.format == discord.StickerFormatType.apng),
                            is_sticker=True,
                            source_id=st.id,
                        )
                        break

                if target:
                    break

        # If nothing found
        if not target:
            e_reg = getattr(self.bot, "custom_emojis", None)
            dot = e_reg.get("heart_dot", "-") if e_reg else "-"
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**No Target Found**\n"
                    "> Reply to a message with an emoji/sticker or provide one directly.\n\n"
                    f"{dot} `?steal <:pepe:123456789>`\n"
                    f"{dot} Reply to any message with `?steal`"
                )
            )
            await send_container_response(ctx, container)
            return

        # Launch clean dashboard with duplicate & collision checks
        view = StealDashboardView(
            bot=self.bot,
            author=ctx.author,
            guild=ctx.guild,
            target=target,
        )
        msg = await send_container_response(ctx, view.build_initial_container(), view=view)
        view.message = msg


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Steal(bot))
