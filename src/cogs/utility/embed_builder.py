"""
Cicada 3301 Discord Bot - Interactive Components V2 Embed & Container Builder
Allows server administrators to create, customize, preview, save, export, and send
high-performance Discord Components V2 Containers to any channel.
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
from src.utils.containers import CicadaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("Cicada.EmbedBuilder")


class ContainerDraft:
    """Represents the in-memory state of a custom Components V2 container."""

    def __init__(self) -> None:
        self.title: str = "Cicada 3301 Custom Embed"
        self.description: str = "> A clean, modern Components V2 container card."
        self.accent_hex: str | None = "#00FF66"
        self.avatar_url: str | None = None
        self.banner_url: str | None = None
        self.footer_text: str | None = None
        self.buttons: list[dict[str, str]] = []

    def get_accent_int(self) -> int | None:
        if not self.accent_hex:
            return None
        hex_clean = self.accent_hex.strip().lstrip("#")
        try:
            return int(hex_clean, 16)
        except ValueError:
            return None

    def to_container(self, bot_avatar: str | None = None) -> CicadaContainer:
        """Render the draft into a Discord Components V2 CicadaContainer."""
        accent = self.get_accent_int()
        container = CicadaContainer(accent_color=accent)

        # Header Section with optional Avatar Accessory on the right
        avatar = self.avatar_url or bot_avatar
        accessory_dict = None
        if avatar:
            accessory_dict = {
                "type": 11,
                "media": {
                    "url": avatar,
                },
            }

        container.add_section(
            content=f"### **{self.title}**\n{self.description}",
            accessory=accessory_dict,
        )

        # Divider
        container.add_separator(divider=True)

        # Optional Banner Image
        if self.banner_url:
            container.add_media_gallery([self.banner_url])
            container.add_separator(divider=True)

        # Action Buttons (URL Link buttons)
        if self.buttons:
            btn_components = []
            for b in self.buttons[:5]:  # Max 5 buttons in an action row
                btn_components.append({
                    "type": 2,
                    "style": 5,  # URL Button
                    "label": b.get("label", "Link"),
                    "url": b.get("url", "https://discord.com"),
                })
            container.add_action_row(btn_components)

        # Optional Footer
        if self.footer_text:
            container.add_text(f"-# {self.footer_text}")

        return container

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
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
        draft.description = data.get("description", draft.description)
        draft.accent_hex = data.get("accent_hex", draft.accent_hex)
        draft.avatar_url = data.get("avatar_url")
        draft.banner_url = data.get("banner_url")
        draft.footer_text = data.get("footer_text")
        draft.buttons = data.get("buttons", [])
        return draft


# ─── Modals for User Input ───────────────────────────────────────────────────

class TextEditModal(discord.ui.Modal, title="Edit Title & Description"):
    title_input = discord.ui.TextInput(
        label="Title / Heading",
        placeholder="Enter embed title...",
        max_length=200,
        required=True,
    )
    desc_input = discord.ui.TextInput(
        label="Description / Markdown Content",
        style=discord.TextStyle.paragraph,
        placeholder="Enter markdown body, quotes, bullet points...",
        max_length=2000,
        required=True,
    )
    avatar_input = discord.ui.TextInput(
        label="Avatar / Thumbnail URL (Optional)",
        placeholder="https://example.com/image.png (or leave blank)",
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.title_input.default = self.view_ref.draft.title
        self.desc_input.default = self.view_ref.draft.description
        self.avatar_input.default = self.view_ref.draft.avatar_url or ""

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.view_ref.draft.title = str(self.title_input.value).strip()
        self.view_ref.draft.description = str(self.desc_input.value).strip()
        avatar = str(self.avatar_input.value).strip()
        self.view_ref.draft.avatar_url = avatar if avatar.startswith("http") else None

        await self.view_ref.update_preview(interaction)


class ColorEditModal(discord.ui.Modal, title="Set Accent Color"):
    color_input = discord.ui.TextInput(
        label="Hex Color Code",
        placeholder="#00FF66, #5865F2, #FF3366, or 'none' for Dark Glass",
        max_length=20,
        required=True,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.color_input.default = self.view_ref.draft.accent_hex or "none"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        val = str(self.color_input.value).strip().lower()
        if val in ["none", "dark", "transparent"]:
            self.view_ref.draft.accent_hex = None
        else:
            if not val.startswith("#"):
                val = f"#{val}"
            self.view_ref.draft.accent_hex = val

        await self.view_ref.update_preview(interaction)


class MediaModal(discord.ui.Modal, title="Set Banner Image"):
    banner_input = discord.ui.TextInput(
        label="Banner Image URL",
        placeholder="https://example.com/banner.png (or 'none' to remove)",
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
        placeholder="e.g. Website, Discord, Rules",
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


class FooterModal(discord.ui.Modal, title="Set Footer Text"):
    footer_input = discord.ui.TextInput(
        label="Footer Subtext",
        placeholder="e.g. Server System • Today at 12:00 PM",
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


class SaveTemplateModal(discord.ui.Modal, title="Save Embed Template"):
    name_input = discord.ui.TextInput(
        label="Template Name",
        placeholder="e.g. welcome, rules, announcement",
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
            await interaction.response.send_message("❌ Invalid template name. Use alphanumeric characters only.", ephemeral=True)
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
                f"✅ Saved custom template as **`{clean_name}`**! Use `?embed send #channel {clean_name}` to post anytime.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("❌ Failed to save template to database. Please try again.", ephemeral=True)


class JSONModal(discord.ui.Modal, title="JSON Import / Export"):
    json_input = discord.ui.TextInput(
        label="Container JSON Payload",
        style=discord.TextStyle.paragraph,
        placeholder="Paste JSON payload here or copy current payload...",
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
            await interaction.response.send_message(f"❌ Invalid JSON format: `{e}`", ephemeral=True)


# ─── Interactive Builder Controller View ─────────────────────────────────────

class EmbedBuilderView(discord.ui.View):
    """Control Panel UI attached to the Live Preview embed builder."""

    def __init__(self, bot: CicadaBot, author: discord.Member | discord.User, draft: ContainerDraft | None = None) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.author = author
        self.draft: ContainerDraft = draft or ContainerDraft()
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Only the command author can interact with this editor.", ephemeral=True)
            return False
        return True

    def build_preview_container(self) -> CicadaContainer:
        bot_avatar = str(self.bot.user.display_avatar.url)
        return self.draft.to_container(bot_avatar=bot_avatar)

    async def update_preview(self, interaction: discord.Interaction) -> None:
        """Refresh the live preview container in Discord."""
        from src.utils.containers import edit_container_response
        container = self.build_preview_container()
        await edit_container_response(interaction, container, view=self)

    # ─── Control Panel Buttons ────────────────────────────────────────────────


    @discord.ui.button(label="Edit Text", style=discord.ButtonStyle.primary, emoji="📝", row=0)
    async def btn_edit_text(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(TextEditModal(self))

    @discord.ui.button(label="Accent Color", style=discord.ButtonStyle.secondary, emoji="🎨", row=0)
    async def btn_edit_color(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(ColorEditModal(self))

    @discord.ui.button(label="Banner Image", style=discord.ButtonStyle.secondary, emoji="🖼️", row=0)
    async def btn_edit_banner(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(MediaModal(self))

    @discord.ui.button(label="Add Link Button", style=discord.ButtonStyle.secondary, emoji="🔘", row=0)
    async def btn_add_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if len(self.draft.buttons) >= 5:
            await interaction.response.send_message("❌ Maximum 5 buttons per container allowed.", ephemeral=True)
            return
        await interaction.response.send_modal(ButtonModal(self))

    @discord.ui.button(label="Footer", style=discord.ButtonStyle.secondary, emoji="👣", row=1)
    async def btn_edit_footer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(FooterModal(self))

    @discord.ui.button(label="Save Template", style=discord.ButtonStyle.success, emoji="💾", row=1)
    async def btn_save_template(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(SaveTemplateModal(self))

    @discord.ui.button(label="JSON / Import", style=discord.ButtonStyle.secondary, emoji="📋", row=1)
    async def btn_json(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(JSONModal(self))

    @discord.ui.button(label="Send to Channel", style=discord.ButtonStyle.danger, emoji="📤", row=1)
    async def btn_send(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Prompt user to select target channel
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("❌ Cannot send in DMs.", ephemeral=True)
            return

        text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages][:25]
        if not text_channels:
            await interaction.response.send_message("❌ No accessible text channels found.", ephemeral=True)
            return

        select_options = [
            discord.SelectOption(
                label=f"#{c.name}"[:100],
                value=str(c.id),
                description=f"Send custom container to #{c.name}"[:100],
            )
            for c in text_channels
        ]

        class ChannelPicker(discord.ui.View):
            def __init__(self, parent_view: EmbedBuilderView) -> None:
                super().__init__(timeout=60)
                self.parent_view = parent_view

            @discord.ui.select(placeholder="Select target channel to post container...", options=select_options)
            async def select_channel(self, inter: discord.Interaction, select: discord.ui.Select) -> None:
                ch_id = int(select.values[0])
                target_ch = inter.guild.get_channel(ch_id) if inter.guild else None
                if not isinstance(target_ch, discord.TextChannel):
                    await inter.response.send_message("❌ Invalid channel selected.", ephemeral=True)
                    return

                container = self.parent_view.build_preview_container()
                await send_container_response(target_ch, container)
                await inter.response.send_message(f"✅ Container successfully posted to {target_ch.mention}!", ephemeral=True)

        await interaction.response.send_message("Select the target channel where you want to send this embed:", view=ChannelPicker(self), ephemeral=True)


# ─── Cog Implementation ──────────────────────────────────────────────────────

class EmbedBuilder(commands.Cog):
    """Interactive Discord Components V2 Embed & Container Builder."""
    category: str = "Utility"

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot

    @commands.group(
        name="embed",
        aliases=["embedbuilder", "container", "card"],
        description="Design, customize, save, and send sleek Components V2 container cards.",
        invoke_without_command=True,
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_group(self, ctx: CustomContext) -> None:
        """Launch the live interactive embed builder."""
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
        description="Send a saved container template to a specific channel. Usage: ?embed send #channel <template_name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_send(
        self, ctx: CustomContext, channel: discord.TextChannel, template_name: str
    ) -> None:
        """Post a saved template to a channel."""
        template_data = await self.bot.embed_mgr.get_template(ctx.guild.id, template_name)
        if not template_data:
            await ctx.send(f"❌ Saved template **`{template_name}`** not found in this server. Use `?embed list` to view saved templates.")
            return

        draft = ContainerDraft.from_dict(template_data)
        container = draft.to_container(bot_avatar=str(self.bot.user.display_avatar.url))
        await send_container_response(channel, container)
        await ctx.send(f"✅ Container **`{template_name}`** sent to {channel.mention}!")

    @embed_group.command(
        name="list",
        aliases=["all", "templates"],
        description="List all saved embed templates for this server.",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_list(self, ctx: CustomContext) -> None:
        """List all saved templates."""
        templates = await self.bot.embed_mgr.list_templates(ctx.guild.id)
        if not templates:
            await ctx.send("ℹ️ No saved templates found in this server. Create one using `?embed create`.")
            return

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"### **Saved Server Embed Templates**\n"
                f"> Found `{len(templates)}` saved container template(s) in this server."
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
            lines.append(f"• **`{name}`** — Created on `{created_at}` • Use `{prefix}embed send #channel {name}`")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @embed_group.command(
        name="delete",
        aliases=["remove"],
        description="Delete a saved embed template. Usage: ?embed delete <template_name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_delete(self, ctx: CustomContext, template_name: str) -> None:
        """Delete a saved template."""
        success = await self.bot.embed_mgr.delete_template(ctx.guild.id, template_name)
        if success:
            await ctx.send(f"✅ Deleted template **`{template_name}`** from server.")
        else:
            await ctx.send(f"❌ Could not find or delete template **`{template_name}`**.")

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
                container = draft.to_container(bot_avatar=str(self.bot.user.display_avatar.url))
                await send_container_response(ctx, container)
                return
        except Exception as e:
            await ctx.send(f"❌ Invalid JSON: `{e}`")


async def setup(bot: CicadaBot) -> None:
    await bot.add_cog(EmbedBuilder(bot))
