"""
Cicada 3301 Discord Bot - Advanced Mimu-Style Components V2 Embed Builder
Full-featured interactive embed builder with zero required fields, placeholder support,
field management, live previewing, template storage, and message editing.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    CicadaContainer,
    send_container_response,
    edit_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("Cicada.EmbedBuilder")


def apply_placeholders(text: str | None, user: discord.Member | discord.User, guild: discord.Guild | None) -> str:
    """Replace dynamic template variables in text."""
    if not text:
        return ""

    replacements = {
        "{user}": user.mention,
        "{user.mention}": user.mention,
        "{user.name}": user.name,
        "{user.id}": str(user.id),
        "{user.avatar}": str(user.display_avatar.url),
    }

    if guild:
        replacements.update({
            "{server}": guild.name,
            "{server.name}": guild.name,
            "{server.id}": str(guild.id),
            "{server.members}": str(guild.member_count or 0),
            "{server.icon}": str(guild.icon.url) if guild.icon else "",
        })

    result = text
    for key, val in replacements.items():
        result = result.replace(key, val)
    return result


class ContainerDraft:
    """Modular data model for custom Components V2 container cards."""

    def __init__(self) -> None:
        self.author_name: str | None = None
        self.author_icon_url: str | None = None
        self.author_url: str | None = None

        self.title: str | None = "Cicada 3301 Custom Card"
        self.title_url: str | None = None

        self.description: str | None = "This is a clean Components V2 container card. You can edit or remove any element."
        
        self.fields: list[dict[str, str]] = []  # [{"name": "...", "value": "..."}]

        self.thumbnail_url: str | None = None
        self.image_url: str | None = None

        self.footer_text: str | None = None
        self.footer_icon_url: str | None = None
        self.timestamp: bool = False

        self.accent_hex: str | None = "#00FF66"
        self.buttons: list[dict[str, str]] = []  # [{"label": "...", "url": "..."}]

    def get_accent_int(self) -> int | None:
        if not self.accent_hex:
            return None
        clean = self.accent_hex.strip().lstrip("#")
        try:
            return int(clean, 16)
        except ValueError:
            return None

    def to_container(
        self,
        user: discord.Member | discord.User | None = None,
        guild: discord.Guild | None = None,
        default_avatar: str | None = None,
    ) -> CicadaContainer:
        """Convert draft into a Discord Components V2 CicadaContainer."""
        container = CicadaContainer(accent_color=self.get_accent_int())

        # Resolve placeholders if user/guild provided
        def parse(t: str | None) -> str:
            if not t:
                return ""
            if user:
                return apply_placeholders(t, user, guild)
            return t

        # 1. Author Section
        author_text = parse(self.author_name)
        author_icon = self.author_icon_url

        # 2. Title and Description Section
        title_text = parse(self.title)
        desc_text = parse(self.description)

        # Thumbnail Accessory (Type 11) on Header Section
        thumb_url = self.thumbnail_url
        accessory_dict = None
        if thumb_url and thumb_url.startswith("http"):
            accessory_dict = {
                "type": 11,
                "media": {
                    "url": thumb_url,
                },
            }

        # Compose Header
        header_blocks = []
        if author_text:
            if self.author_url and self.author_url.startswith("http"):
                header_blocks.append(f"**[{author_text}]({self.author_url})**")
            else:
                header_blocks.append(f"**{author_text}**")

        if title_text:
            if self.title_url and self.title_url.startswith("http"):
                header_blocks.append(f"## [{title_text}]({self.title_url})")
            else:
                header_blocks.append(f"## {title_text}")

        if desc_text:
            header_blocks.append(desc_text)

        if header_blocks or accessory_dict:
            full_header_content = "\n".join(header_blocks) if header_blocks else "​"
            container.add_section(content=full_header_content, accessory=accessory_dict)
            container.add_separator(divider=True)

        # 3. Custom Fields (Type 10 Text Displays)
        if self.fields:
            field_lines = []
            for f in self.fields:
                f_name = parse(f.get("name", ""))
                f_val = parse(f.get("value", ""))
                if f_name and f_val:
                    field_lines.append(f"**{f_name}**\n{f_val}")
                elif f_name:
                    field_lines.append(f"**{f_name}**")
                elif f_val:
                    field_lines.append(f_val)

            if field_lines:
                container.add_text("\n\n".join(field_lines))
                container.add_separator(divider=True)

        # 4. Large Banner Image (Media Gallery Type 12)
        if self.image_url and self.image_url.startswith("http"):
            container.components.append({
                "type": 12,
                "items": [
                    {
                        "media": {
                            "url": self.image_url,
                        }
                    }
                ],
            })
            container.add_separator(divider=True)

        # 5. Buttons Row (Type 1 Action Row)
        if self.buttons:
            btn_comps = []
            for b in self.buttons[:5]:
                btn_comps.append({
                    "type": 2,
                    "style": 5,  # Link URL Button
                    "label": b.get("label", "Link"),
                    "url": b.get("url", "https://discord.com"),
                })
            container.add_action_row(btn_comps)

        # 6. Footer Subtext
        footer_raw = parse(self.footer_text)
        footer_parts = []
        if footer_raw:
            footer_parts.append(footer_raw)
        if self.timestamp:
            import datetime
            now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            footer_parts.append(now_str)

        if footer_parts:
            container.add_text(f"-# {' • '.join(footer_parts)}")

        # Fallback if completely empty
        if not container.components:
            container.add_text("Empty card container.")

        return container

    def to_dict(self) -> dict[str, Any]:
        return {
            "author_name": self.author_name,
            "author_icon_url": self.author_icon_url,
            "author_url": self.author_url,
            "title": self.title,
            "title_url": self.title_url,
            "description": self.description,
            "fields": self.fields,
            "thumbnail_url": self.thumbnail_url,
            "image_url": self.image_url,
            "footer_text": self.footer_text,
            "footer_icon_url": self.footer_icon_url,
            "timestamp": self.timestamp,
            "accent_hex": self.accent_hex,
            "buttons": self.buttons,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContainerDraft:
        draft = cls()
        draft.author_name = data.get("author_name")
        draft.author_icon_url = data.get("author_icon_url")
        draft.author_url = data.get("author_url")
        draft.title = data.get("title")
        draft.title_url = data.get("title_url")
        draft.description = data.get("description")
        draft.fields = data.get("fields", [])
        draft.thumbnail_url = data.get("thumbnail_url")
        draft.image_url = data.get("image_url")
        draft.footer_text = data.get("footer_text")
        draft.footer_icon_url = data.get("footer_icon_url")
        draft.timestamp = bool(data.get("timestamp", False))
        draft.accent_hex = data.get("accent_hex")
        draft.buttons = data.get("buttons", [])
        return draft


# ─── Modals (All Fields Optional) ─────────────────────────────────────────────

class AuthorModal(discord.ui.Modal, title="Edit Author"):
    name_input = discord.ui.TextInput(
        label="Author Name",
        placeholder="Enter author text or leave empty to remove",
        max_length=256,
        required=False,
    )
    icon_input = discord.ui.TextInput(
        label="Author Icon URL",
        placeholder="https://example.com/icon.png",
        required=False,
    )
    url_input = discord.ui.TextInput(
        label="Author Clickable URL",
        placeholder="https://example.com",
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.name_input.default = self.view_ref.draft.author_name or ""
        self.icon_input.default = self.view_ref.draft.author_icon_url or ""
        self.url_input.default = self.view_ref.draft.author_url or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = str(self.name_input.value).strip()
        icon = str(self.icon_input.value).strip()
        url = str(self.url_input.value).strip()

        self.view_ref.draft.author_name = name if name else None
        self.view_ref.draft.author_icon_url = icon if icon.startswith("http") else None
        self.view_ref.draft.author_url = url if url.startswith("http") else None

        await self.view_ref.update_preview(interaction)


class TitleModal(discord.ui.Modal, title="Edit Title"):
    title_input = discord.ui.TextInput(
        label="Title Text",
        placeholder="Enter title text or leave empty to remove",
        max_length=256,
        required=False,
    )
    url_input = discord.ui.TextInput(
        label="Title URL (Clickable)",
        placeholder="https://example.com",
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.title_input.default = self.view_ref.draft.title or ""
        self.url_input.default = self.view_ref.draft.title_url or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        t = str(self.title_input.value).strip()
        u = str(self.url_input.value).strip()
        self.view_ref.draft.title = t if t else None
        self.view_ref.draft.title_url = u if u.startswith("http") else None
        await self.view_ref.update_preview(interaction)


class DescriptionModal(discord.ui.Modal, title="Edit Description"):
    desc_input = discord.ui.TextInput(
        label="Description Body",
        style=discord.TextStyle.paragraph,
        placeholder="Enter markdown text, quotes, variables {user}, {server}...",
        max_length=4000,
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.desc_input.default = self.view_ref.draft.description or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        d = str(self.desc_input.value).strip()
        self.view_ref.draft.description = d if d else None
        await self.view_ref.update_preview(interaction)


class AddFieldModal(discord.ui.Modal, title="Add Field"):
    name_input = discord.ui.TextInput(
        label="Field Name",
        placeholder="Field header or name...",
        max_length=256,
        required=False,
    )
    value_input = discord.ui.TextInput(
        label="Field Value",
        style=discord.TextStyle.paragraph,
        placeholder="Field text or details...",
        max_length=1024,
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        n = str(self.name_input.value).strip()
        v = str(self.value_input.value).strip()
        if n or v:
            self.view_ref.draft.fields.append({"name": n, "value": v})
        await self.view_ref.update_preview(interaction)


class ThumbnailModal(discord.ui.Modal, title="Edit Thumbnail"):
    thumb_input = discord.ui.TextInput(
        label="Thumbnail Image URL",
        placeholder="https://example.com/thumb.png or empty to remove",
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.thumb_input.default = self.view_ref.draft.thumbnail_url or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        t = str(self.thumb_input.value).strip()
        self.view_ref.draft.thumbnail_url = t if t.startswith("http") else None
        await self.view_ref.update_preview(interaction)


class ImageModal(discord.ui.Modal, title="Edit Banner Image"):
    img_input = discord.ui.TextInput(
        label="Banner Image URL",
        placeholder="https://example.com/banner.png or empty to remove",
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.img_input.default = self.view_ref.draft.image_url or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        img = str(self.img_input.value).strip()
        self.view_ref.draft.image_url = img if img.startswith("http") else None
        await self.view_ref.update_preview(interaction)


class FooterModal(discord.ui.Modal, title="Edit Footer"):
    text_input = discord.ui.TextInput(
        label="Footer Text",
        placeholder="Enter footer subtext or empty to remove",
        max_length=2048,
        required=False,
    )
    timestamp_input = discord.ui.TextInput(
        label="Include Timestamp? (yes/no)",
        placeholder="Type 'yes' to show current timestamp",
        max_length=10,
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.text_input.default = self.view_ref.draft.footer_text or ""
        self.timestamp_input.default = "yes" if self.view_ref.draft.timestamp else "no"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        f = str(self.text_input.value).strip()
        ts = str(self.timestamp_input.value).strip().lower()

        self.view_ref.draft.footer_text = f if f else None
        self.view_ref.draft.timestamp = ts in ["yes", "true", "1", "y"]
        await self.view_ref.update_preview(interaction)


class ColorModal(discord.ui.Modal, title="Edit Accent Color"):
    color_input = discord.ui.TextInput(
        label="Hex Color",
        placeholder="#00FF66, #5865F2, #E74C3C, or 'none' for Dark Mode",
        max_length=20,
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.color_input.default = self.view_ref.draft.accent_hex or "none"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val = str(self.color_input.value).strip().lower()
        if val in ["none", "dark", "transparent", ""]:
            self.view_ref.draft.accent_hex = None
        else:
            if not val.startswith("#"):
                val = f"#{val}"
            self.view_ref.draft.accent_hex = val
        await self.view_ref.update_preview(interaction)


class ButtonModal(discord.ui.Modal, title="Add Link Button"):
    label_input = discord.ui.TextInput(
        label="Button Text",
        placeholder="Website, Rules, Support...",
        max_length=80,
        required=False,
    )
    url_input = discord.ui.TextInput(
        label="Button Link URL",
        placeholder="https://discord.gg/...",
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        label = str(self.label_input.value).strip() or "Link"
        url = str(self.url_input.value).strip()
        if url.startswith("http"):
            self.view_ref.draft.buttons.append({"label": label, "url": url})
        await self.view_ref.update_preview(interaction)


class SaveModal(discord.ui.Modal, title="Save Template"):
    name_input = discord.ui.TextInput(
        label="Template Name",
        placeholder="welcome, rules, announcement...",
        max_length=32,
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = str(self.name_input.value).strip().lower()
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", name)
        if not clean_name:
            await interaction.response.send_message("Invalid template name. Use letters and numbers only.", ephemeral=True)
            return

        bot: CicadaBot = interaction.client  # type: ignore
        success = await bot.embed_mgr.save_template(
            guild_id=interaction.guild_id or 0,
            name=clean_name,
            payload=self.view_ref.draft.to_dict(),
            created_by=interaction.user.id,
        )
        if success:
            await interaction.response.send_message(
                f"Saved template as '{clean_name}'. Use '?embed send #channel {clean_name}' to post.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("Failed to save template.", ephemeral=True)


class JSONModal(discord.ui.Modal, title="JSON Payload"):
    json_input = discord.ui.TextInput(
        label="Container JSON Data",
        style=discord.TextStyle.paragraph,
        placeholder="Paste JSON payload or copy existing...",
        max_length=4000,
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.json_input.default = json.dumps(self.view_ref.draft.to_dict(), indent=2)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = str(self.json_input.value).strip()
        if not raw:
            return
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                self.view_ref.draft = ContainerDraft.from_dict(data)
                await self.view_ref.update_preview(interaction)
        except Exception as e:
            await interaction.response.send_message(f"Invalid JSON: {e}", ephemeral=True)


# ─── Interactive Controller View ─────────────────────────────────────────────

class EmbedBuilderView(discord.ui.View):
    """Full-featured Mimu-style builder view for Components V2 containers."""

    def __init__(self, bot: CicadaBot, author: discord.Member | discord.User, draft: ContainerDraft | None = None) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.author = author
        self.draft: ContainerDraft = draft or ContainerDraft()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Only the command author can use this menu.", ephemeral=True)
            return False
        return True

    def build_preview_container(self, guild: discord.Guild | None = None) -> CicadaContainer:
        return self.draft.to_container(
            user=self.author,
            guild=guild,
            default_avatar=str(self.bot.user.display_avatar.url),
        )

    async def update_preview(self, interaction: discord.Interaction) -> None:
        """Update the live preview container."""
        container = self.build_preview_container(interaction.guild)
        await edit_container_response(interaction, container, view=self)

    # ─── Dropdown Options ─────────────────────────────────────────────────────

    @discord.ui.select(
        placeholder="Choose an element to edit or configure...",
        options=[
            discord.SelectOption(label="Author", value="opt_author", description="Set author name, icon, or link"),
            discord.SelectOption(label="Title", value="opt_title", description="Set title text and clickable URL"),
            discord.SelectOption(label="Description", value="opt_desc", description="Set main description body markdown"),
            discord.SelectOption(label="Add Field", value="opt_add_field", description="Add a new custom name/value field"),
            discord.SelectOption(label="Clear Fields", value="opt_clear_fields", description="Remove all custom fields"),
            discord.SelectOption(label="Thumbnail", value="opt_thumb", description="Set top-right thumbnail image"),
            discord.SelectOption(label="Banner Image", value="opt_image", description="Set large bottom banner image"),
            discord.SelectOption(label="Footer", value="opt_footer", description="Set footer subtext and timestamp"),
            discord.SelectOption(label="Accent Color", value="opt_color", description="Set card sidebar border color"),
            discord.SelectOption(label="Add Link Button", value="opt_add_btn", description="Add a clickable URL button"),
            discord.SelectOption(label="Clear Buttons", value="opt_clear_btns", description="Remove all URL buttons"),
            discord.SelectOption(label="JSON Import / Export", value="opt_json", description="View or paste raw JSON code"),
        ],
        row=0,
    )
    async def select_element(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        val = select.values[0]

        if val == "opt_author":
            await interaction.response.send_modal(AuthorModal(self))
        elif val == "opt_title":
            await interaction.response.send_modal(TitleModal(self))
        elif val == "opt_desc":
            await interaction.response.send_modal(DescriptionModal(self))
        elif val == "opt_add_field":
            await interaction.response.send_modal(AddFieldModal(self))
        elif val == "opt_clear_fields":
            self.draft.fields.clear()
            await self.update_preview(interaction)
        elif val == "opt_thumb":
            await interaction.response.send_modal(ThumbnailModal(self))
        elif val == "opt_image":
            await interaction.response.send_modal(ImageModal(self))
        elif val == "opt_footer":
            await interaction.response.send_modal(FooterModal(self))
        elif val == "opt_color":
            await interaction.response.send_modal(ColorModal(self))
        elif val == "opt_add_btn":
            if len(self.draft.buttons) >= 5:
                await interaction.response.send_message("Maximum 5 buttons allowed per card.", ephemeral=True)
                return
            await interaction.response.send_modal(ButtonModal(self))
        elif val == "opt_clear_btns":
            self.draft.buttons.clear()
            await self.update_preview(interaction)
        elif val == "opt_json":
            await interaction.response.send_modal(JSONModal(self))

    # ─── Action Buttons ───────────────────────────────────────────────────────

    @discord.ui.button(label="Send to Channel", style=discord.ButtonStyle.primary, row=1)
    async def btn_send(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Cannot send in direct messages.", ephemeral=True)
            return

        text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages][:25]
        if not text_channels:
            await interaction.response.send_message("No accessible text channels found.", ephemeral=True)
            return

        select_options = [
            discord.SelectOption(
                label=f"#{c.name}"[:100],
                value=str(c.id),
                description=f"Send card to #{c.name}"[:100],
            )
            for c in text_channels
        ]

        class ChannelPicker(discord.ui.View):
            def __init__(self, parent_view: EmbedBuilderView) -> None:
                super().__init__(timeout=60)
                self.parent_view = parent_view

            @discord.ui.select(placeholder="Select target channel...", options=select_options)
            async def select_channel(self, inter: discord.Interaction, sel: discord.ui.Select) -> None:
                ch_id = int(sel.values[0])
                target_ch = inter.guild.get_channel(ch_id) if inter.guild else None
                if not isinstance(target_ch, discord.TextChannel):
                    await inter.response.send_message("Invalid channel selected.", ephemeral=True)
                    return

                container = self.parent_view.build_preview_container(inter.guild)
                await send_container_response(target_ch, container)
                await inter.response.send_message(f"Card posted to {target_ch.mention}.", ephemeral=True)

        await interaction.response.send_message("Select the channel where you want to post this card:", view=ChannelPicker(self), ephemeral=True)

    @discord.ui.button(label="Save Template", style=discord.ButtonStyle.secondary, row=1)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(SaveModal(self))

    @discord.ui.button(label="Clear All", style=discord.ButtonStyle.secondary, row=1)
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.draft = ContainerDraft()
        self.draft.title = None
        self.draft.description = None
        self.draft.footer_text = None
        self.draft.accent_hex = None
        await self.update_preview(interaction)


# ─── Cog Implementation ──────────────────────────────────────────────────────

class EmbedBuilder(commands.Cog):
    """Full-featured Discord Components V2 Embed & Container Builder."""
    category: str = "Utility"

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot

    @commands.group(
        name="embed",
        aliases=["embedbuilder", "container", "card"],
        description="Design, customize, preview, save, edit, and post Components V2 container cards.",
        invoke_without_command=True,
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_group(self, ctx: CustomContext, template_name: str | None = None) -> None:
        """Launch the live interactive embed builder."""
        draft = ContainerDraft()
        if template_name:
            data = await self.bot.embed_mgr.get_template(ctx.guild.id, template_name)
            if data:
                draft = ContainerDraft.from_dict(data)

        view = EmbedBuilderView(self.bot, ctx.author, draft=draft)
        container = view.build_preview_container(ctx.guild)
        await send_container_response(ctx, container, view=view)

    @embed_group.command(
        name="create",
        aliases=["new", "builder"],
        description="Launch a fresh interactive embed builder.",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_create(self, ctx: CustomContext, template_name: str | None = None) -> None:
        """Launch the interactive builder."""
        await self.embed_group(ctx, template_name=template_name)

    @embed_group.command(
        name="send",
        aliases=["post"],
        description="Send a saved template to a channel. Usage: ?embed send #channel <template_name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_send(
        self, ctx: CustomContext, channel: discord.TextChannel, template_name: str
    ) -> None:
        """Send a saved template to a channel."""
        template_data = await self.bot.embed_mgr.get_template(ctx.guild.id, template_name)
        if not template_data:
            await ctx.send(f"Saved template '{template_name}' not found. Use '?embed list' to view saved templates.")
            return

        draft = ContainerDraft.from_dict(template_data)
        container = draft.to_container(
            user=ctx.author,
            guild=ctx.guild,
            default_avatar=str(self.bot.user.display_avatar.url),
        )
        await send_container_response(channel, container)
        await ctx.send(f"Card '{template_name}' posted to {channel.mention}.")

    @embed_group.command(
        name="edit",
        description="Edit an existing bot message in this channel. Usage: ?embed edit <message_id> <template_name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_edit_msg(
        self, ctx: CustomContext, message_id: int, template_name: str
    ) -> None:
        """Edit an existing bot container message."""
        template_data = await self.bot.embed_mgr.get_template(ctx.guild.id, template_name)
        if not template_data:
            await ctx.send(f"Saved template '{template_name}' not found.")
            return

        try:
            target_msg = await ctx.channel.fetch_message(message_id)
        except Exception:
            await ctx.send(f"Message ID '{message_id}' not found in this channel.")
            return

        if target_msg.author.id != self.bot.user.id:
            await ctx.send("Can only edit messages sent by this bot.")
            return

        draft = ContainerDraft.from_dict(template_data)
        container = draft.to_container(
            user=ctx.author,
            guild=ctx.guild,
            default_avatar=str(self.bot.user.display_avatar.url),
        )

        payload = container.to_payload()
        await self.bot.http.request(
            discord.http.Route("PATCH", f"/channels/{ctx.channel.id}/messages/{message_id}"),
            json=payload,
        )
        await ctx.send(f"Message {message_id} updated successfully.")

    @embed_group.command(
        name="list",
        aliases=["all", "templates"],
        description="List all saved templates for this server.",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_list(self, ctx: CustomContext) -> None:
        """List all saved templates."""
        templates = await self.bot.embed_mgr.list_templates(ctx.guild.id)
        if not templates:
            await ctx.send("No saved templates found in this server. Create one using '?embed create'.")
            return

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"## Saved Server Embed Templates\n"
                f"> Found {len(templates)} saved container template(s) in this server."
            ),
            accessory={
                "type": 11,
                "media": {
                    "url": str(self.bot.user.display_avatar.url),
                },
            },
        )
        container.add_separator(divider=True)

        lines = []
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        for t in templates:
            name = t.get("embed_name", "unknown")
            created_at = str(t.get("created_at", ""))[:10]
            lines.append(f"- {name} (Created on {created_at}) - Use '{prefix}embed send #channel {name}'")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @embed_group.command(
        name="delete",
        aliases=["remove"],
        description="Delete a saved template. Usage: ?embed delete <template_name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_delete(self, ctx: CustomContext, template_name: str) -> None:
        """Delete a saved template."""
        success = await self.bot.embed_mgr.delete_template(ctx.guild.id, template_name)
        if success:
            await ctx.send(f"Deleted template '{template_name}' from server.")
        else:
            await ctx.send(f"Could not find or delete template '{template_name}'.")

    @embed_group.command(
        name="raw",
        aliases=["json"],
        description="Send a raw Components V2 JSON container. Usage: ?embed raw <json>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_raw(self, ctx: CustomContext, *, json_payload: str) -> None:
        """Send raw JSON container."""
        try:
            data = json.loads(json_payload)
            if isinstance(data, dict):
                draft = ContainerDraft.from_dict(data)
                container = draft.to_container(
                    user=ctx.author,
                    guild=ctx.guild,
                    default_avatar=str(self.bot.user.display_avatar.url),
                )
                await send_container_response(ctx, container)
                return
        except Exception as e:
            await ctx.send(f"Invalid JSON: {e}")


async def setup(bot: CicadaBot) -> None:
    await bot.add_cog(EmbedBuilder(bot))
