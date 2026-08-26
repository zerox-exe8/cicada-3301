"""
Cicada 3301 Discord Bot - Advanced Components V2 Container Embed Builder
Provides a clean, dropdown-driven interface for designing, customizing,
previewing, saving, and posting Discord Components V2 Containers.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import (
    CicadaContainer,
    send_container_response,
    edit_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("Cicada.EmbedBuilder")


class ContainerDraft:
    """Represents a clean Discord Components V2 Container draft."""

    def __init__(self) -> None:
        self.title: str = "Announcement Title"
        self.subtitle: str = "Official server updates and notices."
        self.body: str = (
            "Write your announcement or information here.\n"
            "- First point or update item\n"
            "- Second point or feature notice\n"
            "- Third point or contact detail"
        )
        self.accent_hex: str | None = "#00FF66"
        self.avatar_url: str | None = None
        self.banner_url: str | None = None
        self.footer_text: str | None = "Cicada 3301 System"
        self.buttons: list[dict[str, str]] = []

    def get_accent_int(self) -> int | None:
        if not self.accent_hex:
            return None
        hex_clean = self.accent_hex.strip().lstrip("#")
        try:
            return int(hex_clean, 16)
        except ValueError:
            return None

    def to_container(self, default_avatar: str | None = None) -> CicadaContainer:
        """Convert draft into a valid Discord Components V2 container."""
        container = CicadaContainer(accent_color=self.get_accent_int())

        # 1. Section Header with optional Thumbnail Accessory (Type 11)
        avatar = self.avatar_url or default_avatar
        accessory_dict = None
        if avatar:
            accessory_dict = {
                "type": 11,
                "media": {
                    "url": avatar,
                },
            }

        header_text = f"## {self.title}"
        if self.subtitle:
            header_text += f"\n> {self.subtitle}"

        container.add_section(content=header_text, accessory=accessory_dict)
        container.add_separator(divider=True)

        # 2. Main Body Content (Type 10 TextDisplay)
        if self.body:
            container.add_text(self.body)
            container.add_separator(divider=True)

        # 3. Media Gallery Banner (Type 12)
        if self.banner_url:
            container.components.append({
                "type": 12,
                "items": [
                    {
                        "media": {
                            "url": self.banner_url,
                        }
                    }
                ],
            })
            container.add_separator(divider=True)

        # 4. Action Row Buttons (Type 1)
        if self.buttons:
            btn_items = []
            for b in self.buttons[:5]:
                btn_items.append({
                    "type": 2,
                    "style": 5,  # URL Button
                    "label": b.get("label", "Link"),
                    "url": b.get("url", "https://discord.com"),
                })
            container.add_action_row(btn_items)

        # 5. Footer Subtext
        if self.footer_text:
            container.add_text(f"-# {self.footer_text}")

        return container

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "body": self.body,
            "accent_hex": self.accent_hex,
            "avatar_url": self.avatar_url,
            "banner_url": self.banner_url,
            "footer_text": self.footer_text,
            "buttons": self.buttons,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContainerDraft:
        draft = cls()
        draft.title = data.get("title", draft.title)
        draft.subtitle = data.get("subtitle", draft.subtitle)
        draft.body = data.get("body", draft.body)
        draft.accent_hex = data.get("accent_hex", draft.accent_hex)
        draft.avatar_url = data.get("avatar_url")
        draft.banner_url = data.get("banner_url")
        draft.footer_text = data.get("footer_text")
        draft.buttons = data.get("buttons", [])
        return draft


# ─── Input Modals ────────────────────────────────────────────────────────────

class HeaderModal(discord.ui.Modal, title="Edit Header and Thumbnail"):
    title_input = discord.ui.TextInput(
        label="Title",
        placeholder="Enter heading text...",
        max_length=200,
        required=True,
    )
    subtitle_input = discord.ui.TextInput(
        label="Subtitle / Quote",
        placeholder="Short description or quote...",
        max_length=500,
        required=False,
    )
    avatar_input = discord.ui.TextInput(
        label="Thumbnail URL (Optional)",
        placeholder="https://example.com/image.png or leave empty for bot avatar",
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.title_input.default = self.view_ref.draft.title
        self.subtitle_input.default = self.view_ref.draft.subtitle
        self.avatar_input.default = self.view_ref.draft.avatar_url or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.view_ref.draft.title = str(self.title_input.value).strip()
        self.view_ref.draft.subtitle = str(self.subtitle_input.value).strip()
        avatar = str(self.avatar_input.value).strip()
        self.view_ref.draft.avatar_url = avatar if avatar.startswith("http") else None
        await self.view_ref.update_preview(interaction)


class BodyModal(discord.ui.Modal, title="Edit Body Content"):
    body_input = discord.ui.TextInput(
        label="Body Markdown Text",
        style=discord.TextStyle.paragraph,
        placeholder="Write paragraphs, lists (- item), bold text, quotes...",
        max_length=3000,
        required=True,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.body_input.default = self.view_ref.draft.body

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.view_ref.draft.body = str(self.body_input.value).strip()
        await self.view_ref.update_preview(interaction)


class ColorModal(discord.ui.Modal, title="Edit Accent Color"):
    color_input = discord.ui.TextInput(
        label="Hex Color Code",
        placeholder="#00FF66, #5865F2, #E67E22, or 'none' for Dark Mode",
        max_length=20,
        required=True,
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


class BannerModal(discord.ui.Modal, title="Edit Banner Image"):
    banner_input = discord.ui.TextInput(
        label="Banner Image URL",
        placeholder="https://example.com/banner.png or 'none' to remove",
        required=True,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.banner_input.default = self.view_ref.draft.banner_url or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val = str(self.banner_input.value).strip()
        if val.lower() in ["none", "remove", ""]:
            self.view_ref.draft.banner_url = None
        elif val.startswith("http"):
            self.view_ref.draft.banner_url = val
        await self.view_ref.update_preview(interaction)


class ButtonModal(discord.ui.Modal, title="Add URL Button"):
    label_input = discord.ui.TextInput(
        label="Button Label",
        placeholder="Website, Rules, Support...",
        max_length=80,
        required=True,
    )
    url_input = discord.ui.TextInput(
        label="Target Link (URL)",
        placeholder="https://discord.gg/...",
        required=True,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        label = str(self.label_input.value).strip()
        url = str(self.url_input.value).strip()
        if url.startswith("http"):
            self.view_ref.draft.buttons.append({"label": label, "url": url})
        await self.view_ref.update_preview(interaction)


class FooterModal(discord.ui.Modal, title="Edit Footer Text"):
    footer_input = discord.ui.TextInput(
        label="Footer Subtext",
        placeholder="Server name or timestamp note...",
        max_length=200,
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.footer_input.default = self.view_ref.draft.footer_text or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val = str(self.footer_input.value).strip()
        self.view_ref.draft.footer_text = val if val else None
        await self.view_ref.update_preview(interaction)


class SaveModal(discord.ui.Modal, title="Save Template"):
    name_input = discord.ui.TextInput(
        label="Template Name",
        placeholder="announcement, rules, welcome...",
        max_length=32,
        required=True,
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
            await interaction.response.send_message("Failed to save template to database.", ephemeral=True)


class JSONModal(discord.ui.Modal, title="JSON Import / Export"):
    json_input = discord.ui.TextInput(
        label="Container JSON Payload",
        style=discord.TextStyle.paragraph,
        placeholder="Paste valid JSON code here...",
        max_length=4000,
        required=True,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.json_input.default = json.dumps(self.view_ref.draft.to_dict(), indent=2)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = str(self.json_input.value).strip()
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                self.view_ref.draft = ContainerDraft.from_dict(data)
                await self.view_ref.update_preview(interaction)
                return
        except Exception as e:
            await interaction.response.send_message(f"Invalid JSON format: {e}", ephemeral=True)


# ─── Interactive Controller View ─────────────────────────────────────────────

class EmbedBuilderView(discord.ui.View):
    """Clean dropdown-driven controller for Discord Components V2 Embeds."""

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

    def build_preview_container(self) -> CicadaContainer:
        bot_avatar = str(self.bot.user.display_avatar.url)
        return self.draft.to_container(default_avatar=bot_avatar)

    async def update_preview(self, interaction: discord.Interaction) -> None:
        """Update live preview container."""
        container = self.build_preview_container()
        await edit_container_response(interaction, container, view=self)

    # ─── Dropdown Component Selector ──────────────────────────────────────────

    @discord.ui.select(
        placeholder="Select an option to edit or load...",
        options=[
            discord.SelectOption(label="Edit Header and Thumbnail", value="edit_header", description="Change title, subtitle, or avatar"),
            discord.SelectOption(label="Edit Body Content", value="edit_body", description="Change description text and markdown"),
            discord.SelectOption(label="Edit Accent Color", value="edit_color", description="Set custom hex border color"),
            discord.SelectOption(label="Edit Banner Image", value="edit_banner", description="Set or remove bottom banner image"),
            discord.SelectOption(label="Add Link Button", value="add_button", description="Add a clickable URL button to card"),
            discord.SelectOption(label="Edit Footer Text", value="edit_footer", description="Change footer subtext"),
            discord.SelectOption(label="Load Preset: Announcement", value="preset_announcement", description="Load announcement layout"),
            discord.SelectOption(label="Load Preset: Server Rules", value="preset_rules", description="Load server rules layout"),
            discord.SelectOption(label="Load Preset: Welcome Guide", value="preset_welcome", description="Load welcome card layout"),
            discord.SelectOption(label="JSON Import / Export", value="json_io", description="View or paste raw JSON code"),
        ],
        row=0,
    )
    async def select_action(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        choice = select.values[0]

        if choice == "edit_header":
            await interaction.response.send_modal(HeaderModal(self))
        elif choice == "edit_body":
            await interaction.response.send_modal(BodyModal(self))
        elif choice == "edit_color":
            await interaction.response.send_modal(ColorModal(self))
        elif choice == "edit_banner":
            await interaction.response.send_modal(BannerModal(self))
        elif choice == "add_button":
            if len(self.draft.buttons) >= 5:
                await interaction.response.send_message("Maximum 5 buttons allowed per card.", ephemeral=True)
                return
            await interaction.response.send_modal(ButtonModal(self))
        elif choice == "edit_footer":
            await interaction.response.send_modal(FooterModal(self))
        elif choice == "preset_announcement":
            self.draft.title = "Important Server Announcement"
            self.draft.subtitle = "Please read the following information carefully."
            self.draft.body = (
                "### Maintenance and Updates\n"
                "- Scheduled maintenance window: Tonight at 12:00 AM UTC\n"
                "- Expected downtime: Less than 5 minutes\n"
                "- Services affected: Database indexing and sync"
            )
            self.draft.accent_hex = "#00FF66"
            self.draft.footer_text = "Cicada 3301 Core Infrastructure"
            await self.update_preview(interaction)
        elif choice == "preset_rules":
            self.draft.title = "Server Rules and Guidelines"
            self.draft.subtitle = "Follow these rules to maintain a friendly community."
            self.draft.body = (
                "1. Treat all members with respect and courtesy.\n"
                "2. No hate speech, harassment, or offensive language.\n"
                "3. Keep discussions in the relevant designated channels.\n"
                "4. No unauthorized advertising or self-promotion.\n"
                "5. Follow all official Discord Terms of Service."
            )
            self.draft.accent_hex = "#5865F2"
            self.draft.footer_text = "Server Moderation Team"
            await self.update_preview(interaction)
        elif choice == "preset_welcome":
            self.draft.title = "Welcome to Our Server"
            self.draft.subtitle = "We are glad to have you here."
            self.draft.body = (
                "### Getting Started\n"
                "- Read our server rules in the rules channel\n"
                "- Pick your notification roles in role-select\n"
                "- Introduce yourself in the general chat"
            )
            self.draft.accent_hex = "#F59E0B"
            self.draft.footer_text = "Community Management"
            await self.update_preview(interaction)
        elif choice == "json_io":
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
                description=f"Send container to #{c.name}"[:100],
            )
            for c in text_channels
        ]

        class ChannelPicker(discord.ui.View):
            def __init__(self, parent_view: EmbedBuilderView) -> None:
                super().__init__(timeout=60)
                self.parent_view = parent_view

            @discord.ui.select(placeholder="Select target channel...", options=select_options)
            async def select_channel(self, inter: discord.Interaction, select: discord.ui.Select) -> None:
                ch_id = int(select.values[0])
                target_ch = inter.guild.get_channel(ch_id) if inter.guild else None
                if not isinstance(target_ch, discord.TextChannel):
                    await inter.response.send_message("Invalid channel selected.", ephemeral=True)
                    return

                container = self.parent_view.build_preview_container()
                await send_container_response(target_ch, container)
                await inter.response.send_message(f"Container posted to {target_ch.mention}.", ephemeral=True)

        await interaction.response.send_message("Select the channel where you want to post this container:", view=ChannelPicker(self), ephemeral=True)

    @discord.ui.button(label="Save Template", style=discord.ButtonStyle.secondary, row=1)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(SaveModal(self))

    @discord.ui.button(label="Reset", style=discord.ButtonStyle.secondary, row=1)
    async def btn_reset(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.draft = ContainerDraft()
        await self.update_preview(interaction)


# ─── Cog Implementation ──────────────────────────────────────────────────────

class EmbedBuilder(commands.Cog):
    """Clean Discord Components V2 Container Embed Builder."""
    category: str = "Utility"

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot

    @commands.group(
        name="embed",
        aliases=["embedbuilder", "container", "card"],
        description="Create, customize, preview, save, and post Components V2 container cards.",
        invoke_without_command=True,
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_group(self, ctx: CustomContext) -> None:
        """Launch the live embed builder."""
        view = EmbedBuilderView(self.bot, ctx.author)
        container = view.build_preview_container()
        await send_container_response(ctx, container, view=view)

    @embed_group.command(
        name="create",
        aliases=["builder", "new"],
        description="Launch live interactive Components V2 embed builder.",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_create(self, ctx: CustomContext) -> None:
        """Launch the live interactive editor."""
        await self.embed_group(ctx)

    @embed_group.command(
        name="send",
        aliases=["post"],
        description="Send a saved template to a channel. Usage: ?embed send #channel <template_name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_send(
        self, ctx: CustomContext, channel: discord.TextChannel, template_name: str
    ) -> None:
        """Post a saved template to a channel."""
        template_data = await self.bot.embed_mgr.get_template(ctx.guild.id, template_name)
        if not template_data:
            await ctx.send(f"Saved template '{template_name}' not found. Use '?embed list' to view saved templates.")
            return

        draft = ContainerDraft.from_dict(template_data)
        container = draft.to_container(default_avatar=str(self.bot.user.display_avatar.url))
        await send_container_response(channel, container)
        await ctx.send(f"Container '{template_name}' posted to {channel.mention}.")

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
                container = draft.to_container(default_avatar=str(self.bot.user.display_avatar.url))
                await send_container_response(ctx, container)
                return
        except Exception as e:
            await ctx.send(f"Invalid JSON: {e}")


async def setup(bot: CicadaBot) -> None:
    await bot.add_cog(EmbedBuilder(bot))
