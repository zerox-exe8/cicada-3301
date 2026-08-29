"""
Cicada 3301 Discord Bot - Advanced Ticket System & Interactive Slide Dashboard
Seamlessly integrates with Embed Builder for custom visual panels and manages private ticket channels,
roles, permission overrides, live claiming, and HTML transcript logging.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from typing import Any

import discord
from discord.ext import commands

from src.core.bot import CicadaBot
from src.core.context import CustomContext
from src.utils.containers import CicadaContainer, send_container_response, edit_container_response, build_container_payload
from src.utils.transcript import generate_html_transcript
from src.cogs.utility.embed_builder import ContainerDraft

logger = logging.getLogger("Cicada.Cogs.Ticket")


# ─── INSIDE-TICKET CONTROLS VIEW ──────────────────────────────────────────────

class TicketCloseConfirmModal(discord.ui.Modal, title="Close Ticket"):
    reason_input = discord.ui.TextInput(
        label="Closing Reason (Optional)",
        placeholder="e.g. Issue resolved, inactive, answered",
        required=False,
        max_length=250,
    )

    def __init__(self, cog: TicketSystem, ticket_data: dict[str, Any]) -> None:
        super().__init__()
        self.cog = cog
        self.ticket_data = ticket_data

    async def on_submit(self, interaction: discord.Interaction) -> None:
        reason = str(self.reason_input.value).strip() or "No reason provided."
        await self.cog.execute_ticket_close(interaction, self.ticket_data, reason=reason)


class TicketInsideControlsView(discord.ui.View):
    """Persistent controls attached inside the private ticket channel."""

    def __init__(self, cog: TicketSystem) -> None:
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        emoji="🔒",
        custom_id="ticket_ctrl_close",
        row=0,
    )
    async def btn_close(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await self.cog.bot.ticket_mgr.get_ticket(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("This channel is not registered as an active ticket.", ephemeral=True)
            return

        # Open close confirmation modal
        await interaction.response.send_modal(TicketCloseConfirmModal(self.cog, ticket))

    @discord.ui.button(
        label="Claim Ticket",
        style=discord.ButtonStyle.success,
        emoji="🙋",
        custom_id="ticket_ctrl_claim",
        row=0,
    )
    async def btn_claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ticket = await self.cog.bot.ticket_mgr.get_ticket(interaction.channel_id)
        if not ticket:
            await interaction.response.send_message("This channel is not registered as an active ticket.", ephemeral=True)
            return

        # Check if staff permissions or panel support role
        panel = await self.cog.bot.ticket_mgr.get_panel_by_id(ticket.get("panel_id", 0))
        is_staff = interaction.user.guild_permissions.manage_channels or interaction.user.guild_permissions.administrator
        if panel and panel.get("support_role_id"):
            s_role = interaction.guild.get_role(panel["support_role_id"]) if interaction.guild else None
            if s_role and s_role in getattr(interaction.user, "roles", []):
                is_staff = True

        if not is_staff:
            await interaction.response.send_message("Only staff members can claim tickets.", ephemeral=True)
            return

        claimed_by = ticket.get("claimed_by")
        if claimed_by and claimed_by == interaction.user.id:
            await interaction.response.send_message("You have already claimed this ticket.", ephemeral=True)
            return

        await self.cog.bot.ticket_mgr.claim_ticket(interaction.channel_id, interaction.user.id)
        await interaction.response.send_message(
            f"**Ticket Claimed** • This ticket has been claimed by {interaction.user.mention}.",
        )

    @discord.ui.button(
        label="Save Transcript",
        style=discord.ButtonStyle.secondary,
        emoji="📋",
        custom_id="ticket_ctrl_transcript",
        row=0,
    )
    async def btn_transcript(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message("Transcripts are only supported in text channels.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        ticket = await self.cog.bot.ticket_mgr.get_ticket(interaction.channel_id)
        file = await generate_html_transcript(interaction.channel, ticket, bot=self.cog.bot)
        await interaction.followup.send(
            content="Here is the live transcript for this ticket:",
            file=file,
            ephemeral=True,
        )


# ─── SLIDE-BASED TICKET DASHBOARD SETUP WIZARD ───────────────────────────────

class TicketSetupWizard(discord.ui.View):
    """
    Slide-Based Wizard for ?ticket setup:
    Slide 1: Embed Select Template + Continue >
    Slide 2: Support Role & Target Category + < Back + Continue >
    Slide 3: Log Channel & Naming Format + < Back + Continue >
    Slide 4: Target Channel & Deploy Panel Action
    """

    SLIDES = [
        ("embed", "Step 1: Select Embed Template", "Choose a saved embed from the Embed Builder to use as the visual card for your ticket panel."),
        ("roles", "Step 2: Support Role & Category", "Select the support role allowed to manage tickets and the category where private channels are created."),
        ("logs", "Step 3: Logs & Settings", "Configure where transcripts and audit logs are sent, and set your ticket naming convention."),
        ("deploy", "Step 4: Target Channel & Deploy", "Choose which text channel to post this ticket panel to and deploy it live."),
    ]

    def __init__(
        self,
        cog: TicketSystem,
        author: discord.User | discord.Member,
        initial_embed: str | None = None,
    ) -> None:
        super().__init__(timeout=600)
        self.cog = cog
        self.bot = cog.bot
        self.author = author
        self.current_slide_idx: int = 0

        # Wizard State
        self.selected_embed: str | None = initial_embed
        self.selected_role_id: int | None = None
        self.selected_category_id: int | None = None
        self.selected_log_channel_id: int | None = None
        self.selected_target_channel_id: int | None = None
        self.naming_format: str = "ticket-{count}"
        self.button_label: str = "Create Ticket"

        self._build_components_for_slide()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                f"Only {self.author.mention} can control this setup wizard session.",
                ephemeral=True,
            )
            return False
        return True

    def _build_components_for_slide(self) -> None:
        """Rebuild view items dynamically according to current slide index."""
        self.clear_items()
        slide_key, _, _ = self.SLIDES[self.current_slide_idx]
        guild = getattr(self.author, "guild", None)
        templates = []
        if guild:
            templates = self.cog.bot.embed_mgr._templates_cache.get(guild.id, [])

        if slide_key == "embed":
            # Slide 1: Embed Select Menu
            options = []
            if templates:
                for t in templates[:25]:
                    name = t.get("embed_name", "unknown")
                    options.append(discord.SelectOption(
                        label=name,
                        value=name,
                        description=f"Use '{name}' as the ticket panel embed"[:100],
                        default=(self.selected_embed == name),
                    ))
            if not options:
                options.append(discord.SelectOption(
                    label="Default Support Embed",
                    value="__default__",
                    description="Standard clean ticket support embed card",
                    default=True,
                ))
                self.selected_embed = "__default__"

            select = discord.ui.Select(
                placeholder="Select an embed template...",
                options=options,
                custom_id="wiz_select_embed",
                row=0,
            )
            select.callback = self._on_embed_selected
            self.add_item(select)

            # Continue button
            btn_continue = discord.ui.Button(
                label="Continue >",
                style=discord.ButtonStyle.primary,
                custom_id="wiz_btn_continue",
                disabled=(self.selected_embed is None),
                row=1,
            )
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "roles":
            # Slide 2: Role Select & Category Select
            role_select = discord.ui.RoleSelect(
                placeholder="Select a Support Staff Role...",
                custom_id="wiz_select_role",
                min_values=0,
                max_values=1,
                row=0,
            )
            role_select.callback = self._on_role_selected
            self.add_item(role_select)

            cat_select = discord.ui.ChannelSelect(
                placeholder="Select a Category for Ticket Channels...",
                channel_types=[discord.ChannelType.category],
                custom_id="wiz_select_cat",
                min_values=0,
                max_values=1,
                row=1,
            )
            cat_select.callback = self._on_category_selected
            self.add_item(cat_select)

            btn_back = discord.ui.Button(
                label="< Back",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_back",
                row=2,
            )
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_continue = discord.ui.Button(
                label="Continue >",
                style=discord.ButtonStyle.primary,
                custom_id="wiz_btn_continue",
                row=2,
            )
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "logs":
            # Slide 3: Log Channel Select
            log_select = discord.ui.ChannelSelect(
                placeholder="Select a Log Channel for Transcripts...",
                channel_types=[discord.ChannelType.text],
                custom_id="wiz_select_log",
                min_values=0,
                max_values=1,
                row=0,
            )
            log_select.callback = self._on_log_channel_selected
            self.add_item(log_select)

            # Naming style toggle
            btn_name = discord.ui.Button(
                label=f"Naming: {self.naming_format}",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_naming",
                row=1,
            )
            btn_name.callback = self._on_toggle_naming
            self.add_item(btn_name)

            btn_back = discord.ui.Button(
                label="< Back",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_back",
                row=2,
            )
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_continue = discord.ui.Button(
                label="Continue >",
                style=discord.ButtonStyle.primary,
                custom_id="wiz_btn_continue",
                row=2,
            )
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "deploy":
            # Slide 4: Target Channel & Deploy Action
            target_select = discord.ui.ChannelSelect(
                placeholder="Select Target Channel to post panel...",
                channel_types=[discord.ChannelType.text],
                custom_id="wiz_select_target",
                min_values=1,
                max_values=1,
                row=0,
            )
            target_select.callback = self._on_target_selected
            self.add_item(target_select)

            btn_back = discord.ui.Button(
                label="< Back",
                style=discord.ButtonStyle.secondary,
                custom_id="wiz_btn_back",
                row=1,
            )
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_deploy = discord.ui.Button(
                label="Deploy Panel",
                style=discord.ButtonStyle.success,
                custom_id="wiz_btn_deploy",
                disabled=(self.selected_target_channel_id is None),
                row=1,
            )
            btn_deploy.callback = self._on_deploy_clicked
            self.add_item(btn_deploy)

    def get_dashboard_container(self, guild: discord.Guild | None) -> CicadaContainer:
        """Render the single sleek Components V2 Ticket Dashboard Container."""
        container = CicadaContainer(accent_color=None)
        slide_key, slide_title, slide_desc = self.SLIDES[self.current_slide_idx]

        container.add_section(
            content=(
                f"**Ticket Dashboard** • {slide_title}\n"
                f"> {slide_desc}"
            )
        )
        container.add_separator(divider=True)

        e_disp = f"`{self.selected_embed}`" if self.selected_embed else "*None Selected*"
        r_disp = f"<@&{self.selected_role_id}>" if self.selected_role_id else "*Administrators (Default)*"
        c_disp = f"<#{self.selected_category_id}>" if self.selected_category_id else "*Auto-Create 'Tickets' Category*"
        l_disp = f"<#{self.selected_log_channel_id}>" if self.selected_log_channel_id else "*None (Direct DM)*"
        t_disp = f"<#{self.selected_target_channel_id}>" if self.selected_target_channel_id else "*Not Selected*"

        container.add_text(
            f"• **Selected Embed:** {e_disp}\n"
            f"• **Support Role:** {r_disp}\n"
            f"• **Target Category:** {c_disp}\n"
            f"• **Log Channel:** {l_disp}\n"
            f"• **Naming Format:** `{self.naming_format}`\n"
            f"• **Deploy Target:** {t_disp}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Step {self.current_slide_idx + 1}/4 • Setup Session for {self.author.display_name}")

        return container

    async def _on_embed_selected(self, interaction: discord.Interaction) -> None:
        select: discord.ui.Select = interaction.data.get("values", [])  # type: ignore
        if select:
            self.selected_embed = select[0]
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_role_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        if values:
            self.selected_role_id = int(values[0])
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_category_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        if values:
            self.selected_category_id = int(values[0])
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_log_channel_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        if values:
            self.selected_log_channel_id = int(values[0])
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_target_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        if values:
            self.selected_target_channel_id = int(values[0])
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_toggle_naming(self, interaction: discord.Interaction) -> None:
        if self.naming_format == "ticket-{count}":
            self.naming_format = "support-{user}"
        elif self.naming_format == "support-{user}":
            self.naming_format = "ticket-{user}"
        else:
            self.naming_format = "ticket-{count}"
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_continue_clicked(self, interaction: discord.Interaction) -> None:
        if self.current_slide_idx < len(self.SLIDES) - 1:
            self.current_slide_idx += 1
            self._build_components_for_slide()
            await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_back_clicked(self, interaction: discord.Interaction) -> None:
        if self.current_slide_idx > 0:
            self.current_slide_idx -= 1
            self._build_components_for_slide()
            await edit_container_response(interaction, self.get_dashboard_container(interaction.guild), view=self)

    async def _on_deploy_clicked(self, interaction: discord.Interaction) -> None:
        if not self.selected_target_channel_id or not interaction.guild:
            await interaction.response.send_message("Please select a target channel to deploy.", ephemeral=True)
            return

        target_channel = interaction.guild.get_channel(self.selected_target_channel_id)
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("Invalid target text channel.", ephemeral=True)
            return

        await interaction.response.defer()

        panel_name = self.selected_embed or "support"
        if panel_name == "__default__":
            panel_name = "support"

        # Generate panel container from template or clean default
        draft = ContainerDraft()
        if self.selected_embed and self.selected_embed != "__default__":
            tmpl = await self.bot.embed_mgr.get_template(interaction.guild.id, self.selected_embed)
            if tmpl:
                draft = ContainerDraft.from_dict(tmpl)
        else:
            draft.title = "Support & Inquiries"
            draft.description = "Click the button below to create a private support ticket with our staff team."
            draft.accent_hex = "5865F2"

        panel_container = draft.to_container(
            user=interaction.user,
            guild=interaction.guild,
            channel=target_channel,
            bot=self.bot,
        )

        # Create database panel entry to get panel_id
        temp_row = await self.bot.ticket_mgr.create_panel(
            guild_id=interaction.guild.id,
            panel_name=panel_name,
            embed_name=self.selected_embed or "support",
            channel_id=target_channel.id,
            message_id=0,
            category_id=self.selected_category_id,
            support_role_id=self.selected_role_id,
            log_channel_id=self.selected_log_channel_id,
            naming_format=self.naming_format,
            button_label=self.button_label,
            created_by=interaction.user.id,
        )
        panel_id = temp_row.get("id", 1)

        # Attach interactive persistent button inside panel container
        btn_action_row = {
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 1,  # Primary Blurple
                    "label": self.button_label,
                    "custom_id": f"ticket_open_{panel_id}",
                    "emoji": {"name": "📩"},
                }
            ],
        }
        panel_container.components.append(btn_action_row)

        msg_data = await send_container_response(target_channel, panel_container)
        msg_id = 0
        if isinstance(msg_data, dict) and "id" in msg_data:
            msg_id = int(msg_data["id"])
        elif hasattr(msg_data, "id"):
            msg_id = int(msg_data.id)

        # Update message_id in database
        if msg_id:
            await self.bot.ticket_mgr.create_panel(
                guild_id=interaction.guild.id,
                panel_name=panel_name,
                embed_name=self.selected_embed or "support",
                channel_id=target_channel.id,
                message_id=msg_id,
                category_id=self.selected_category_id,
                support_role_id=self.selected_role_id,
                log_channel_id=self.selected_log_channel_id,
                naming_format=self.naming_format,
                button_label=self.button_label,
                created_by=interaction.user.id,
            )

        # Success confirmation on dashboard
        conf_container = CicadaContainer(accent_color=5763719)  # Green
        conf_container.add_section(
            content=(
                "**Ticket Panel Deployed Successfully**\n"
                f"> Panel **{panel_name}** is now live in {target_channel.mention}.\n\n"
                f"• **Category:** {f'<#{self.selected_category_id}>' if self.selected_category_id else 'Auto-Create'}\n"
                f"• **Support Role:** {f'<@&{self.selected_role_id}>' if self.selected_role_id else 'Administrators'}\n"
                f"• **Logs Channel:** {f'<#{self.selected_log_channel_id}>' if self.selected_log_channel_id else 'None'}"
            )
        )
        conf_container.add_separator(divider=True)
        conf_container.add_text(f"-# Configured by {interaction.user.display_name}")

        self.clear_items()
        await edit_container_response(interaction, conf_container, view=self)


# ─── MAIN TICKET SYSTEM COG ───────────────────────────────────────────────────

class TicketSystem(commands.Cog):
    """Enterprise Ticket System with Components V2 container panels and slide setup wizard."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot
        # Register persistent inside-ticket view
        self.bot.add_view(TicketInsideControlsView(self))

    # ─── PERSISTENT BUTTON INTERACTION LISTENER ───────────────────────────────

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Handle ticket panel create button clicks globally across all guilds."""
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("ticket_open_"):
            return

        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        try:
            panel_id = int(custom_id.replace("ticket_open_", ""))
        except ValueError:
            return

        panel = await self.bot.ticket_mgr.get_panel_by_id(panel_id)
        if not panel:
            await interaction.response.send_message("This ticket panel configuration was not found.", ephemeral=True)
            return

        # Check existing active ticket for user (Max 1 active ticket per panel/guild)
        existing = await self.bot.ticket_mgr.get_active_ticket_for_user(interaction.guild.id, interaction.user.id, panel_id=panel_id)
        if existing:
            ch_id = existing.get("channel_id")
            await interaction.response.send_message(
                f"You already have an open ticket in <#{ch_id}>.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        # Increment sequential ticket number
        ticket_num = await self.bot.ticket_mgr.get_next_ticket_number(interaction.guild.id)
        ticket_str = f"{ticket_num:04d}"

        # Resolve channel name
        naming = panel.get("naming_format", "ticket-{count}")
        clean_user = re.sub(r"[^a-zA-Z0-9_-]", "", interaction.user.name.lower()) or "user"
        channel_name = naming.replace("{count}", ticket_str).replace("{user}", clean_user)

        # Resolve or auto-create target category
        cat_id = panel.get("category_id")
        category: discord.CategoryChannel | None = None
        if cat_id:
            cat_obj = interaction.guild.get_channel(cat_id)
            if isinstance(cat_obj, discord.CategoryChannel):
                category = cat_obj

        if not category:
            # Auto-find or create 'Tickets' category
            category = discord.utils.get(interaction.guild.categories, name="Tickets")
            if not category:
                try:
                    category = await interaction.guild.create_category(
                        name="Tickets",
                        reason="Cicada 3301 Ticket Engine Category",
                    )
                except Exception as cat_err:
                    logger.warning(f"Could not create Tickets category: {cat_err}")

        # Construct permission overrides
        overrides: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False, send_messages=False),
            interaction.user: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True,
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                read_messages=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True,
                read_message_history=True,
            ),
        }

        support_role_id = panel.get("support_role_id")
        if support_role_id:
            s_role = interaction.guild.get_role(support_role_id)
            if s_role:
                overrides[s_role] = discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True,
                    attach_files=True,
                    embed_links=True,
                    read_message_history=True,
                )

        # Create private ticket text channel
        try:
            ticket_channel = await interaction.guild.create_text_channel(
                name=channel_name,
                category=category,
                overrides=overrides,
                topic=f"Ticket #{ticket_str} | Creator: {interaction.user} (ID: {interaction.user.id})",
                reason=f"Ticket created by {interaction.user}",
            )
        except Exception as create_err:
            logger.error(f"Failed to create ticket channel: {create_err}", exc_info=create_err)
            await interaction.followup.send("Failed to create ticket channel. Please ensure the bot has 'Manage Channels' permission.", ephemeral=True)
            return

        # Record ticket in database
        await self.bot.ticket_mgr.create_ticket(
            guild_id=interaction.guild.id,
            panel_id=panel_id,
            channel_id=ticket_channel.id,
            user_id=interaction.user.id,
            ticket_number=ticket_num,
        )

        # Send welcome card in ticket channel
        welcome_container = CicadaContainer(accent_color=5793266)  # Blurple
        welcome_container.add_section(
            content=(
                f"**Ticket #{ticket_str} • {interaction.user.display_name}**\n"
                f"> Welcome to your private support ticket, {interaction.user.mention}.\n"
                f"> Please describe your inquiry in detail. Our staff team will assist you shortly."
            )
        )
        welcome_container.add_separator(divider=True)
        welcome_container.add_text(
            f"• **Ticket ID:** `#{ticket_str}`\n"
            f"• **Panel:** `{panel.get('panel_name', 'Support')}`\n"
            f"• **Status:** `Open` • **Claimed:** *Unclaimed*"
        )
        welcome_container.add_separator(divider=True)
        welcome_container.add_text("-# Use the buttons below to manage this ticket.")

        await send_container_response(
            ticket_channel,
            welcome_container,
            view=TicketInsideControlsView(self),
            content=f"{interaction.user.mention} {f'<@&{support_role_id}>' if support_role_id else ''}",
        )

        # Log ticket creation in log channel if configured
        log_channel_id = panel.get("log_channel_id")
        if log_channel_id:
            log_ch = interaction.guild.get_channel(log_channel_id)
            if isinstance(log_ch, discord.TextChannel):
                log_c = CicadaContainer(accent_color=5763719)  # Green
                log_c.add_section(
                    content=(
                        f"**Ticket Opened • #{ticket_str}**\n"
                        f"> User: {interaction.user.mention} (`{interaction.user.id}`)\n"
                        f"> Channel: {ticket_channel.mention}\n"
                        f"> Panel: `{panel.get('panel_name')}`"
                    )
                )
                await send_container_response(log_ch, log_c)

        # Ephemeral confirmation to user
        await interaction.followup.send(
            f"Your ticket has been created: {ticket_channel.mention}",
            ephemeral=True,
        )

    # ─── TICKET CLOSE EXECUTION ───────────────────────────────────────────────

    async def execute_ticket_close(
        self,
        interaction_or_ctx: discord.Interaction | CustomContext,
        ticket_data: dict[str, Any],
        reason: str = "Issue resolved",
    ) -> None:
        """Generate transcript, notify logs/user, and safely close the ticket channel."""
        guild = interaction_or_ctx.guild
        channel = interaction_or_ctx.channel
        closer = interaction_or_ctx.user if isinstance(interaction_or_ctx, discord.Interaction) else interaction_or_ctx.author

        if not guild or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        if isinstance(interaction_or_ctx, discord.Interaction):
            await interaction_or_ctx.response.send_message(
                f"**Closing Ticket** • Transcript generating, channel will be deleted in 5 seconds...",
            )
        else:
            await interaction_or_ctx.send(
                f"**Closing Ticket** • Transcript generating, channel will be deleted in 5 seconds...",
            )

        ticket_num = ticket_data.get("ticket_number", channel.id)
        panel = await self.bot.ticket_mgr.get_panel_by_id(ticket_data.get("panel_id", 0))

        # Generate HTML transcript
        transcript_file = await generate_html_transcript(channel, ticket_data, bot=self.bot)

        # Send transcript to ticket owner DM
        user_id = ticket_data.get("user_id")
        if user_id:
            user = guild.get_member(user_id) or await self.bot.fetch_user(user_id)
            if user:
                try:
                    dm_container = CicadaContainer(accent_color=15548997)  # Red
                    dm_container.add_section(
                        content=(
                            f"**Ticket #{ticket_num:04d} Closed**\n"
                            f"> Server: **{guild.name}**\n"
                            f"> Closed By: **{closer.display_name}**\n"
                            f"> Reason: `{reason}`"
                        )
                    )
                    await user.send(file=transcript_file)
                except Exception:
                    pass

        # Send transcript to log channel if configured
        log_channel_id = panel.get("log_channel_id") if panel else None
        if log_channel_id:
            log_ch = guild.get_channel(log_channel_id)
            if isinstance(log_ch, discord.TextChannel):
                try:
                    # Re-generate transcript stream for log channel
                    t_file_2 = await generate_html_transcript(channel, ticket_data, bot=self.bot)
                    log_c = CicadaContainer(accent_color=15548997)  # Red
                    log_c.add_section(
                        content=(
                            f"**Ticket Closed • #{ticket_num:04d}**\n"
                            f"> Channel: `#{channel.name}`\n"
                            f"> Creator: <@{user_id}> (`{user_id}`)\n"
                            f"> Closed By: {closer.mention} (`{closer.id}`)\n"
                            f"> Reason: `{reason}`"
                        )
                    )
                    await log_ch.send(file=t_file_2)
                    await send_container_response(log_ch, log_c)
                except Exception as log_err:
                    logger.warning(f"Could not send close log: {log_err}")

        # Update database record
        await self.bot.ticket_mgr.close_ticket(channel.id, closer.id)

        # Delete channel after short countdown
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket closed by {closer.name}: {reason}")
        except Exception as del_err:
            logger.error(f"Failed to delete closed ticket channel {channel.id}: {del_err}")

    # ─── TICKET COMMANDS ──────────────────────────────────────────────────────

    @commands.hybrid_group(
        name="ticket",
        aliases=["tickets", "ticketpanel"],
        description="Enterprise Ticket System management commands and interactive setup wizard.",
        fallback="hub",
    )
    async def ticket_group(self, ctx: CustomContext) -> None:
        """Ticket Hub Overview & Commands Guide."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        panels = await self.bot.ticket_mgr.list_panels(ctx.guild.id)

        hub_container = CicadaContainer(accent_color=None)
        hub_container.add_section(
            content=(
                "**Ticket System Hub**\n"
                f"> Manage, deploy, and configure custom ticket panels for **{ctx.guild.name}**.\n"
                f"> Integrated with the **Embed Builder** for custom visual cards."
            )
        )
        hub_container.add_separator(divider=True)

        if panels:
            p_names = [f"`{p.get('panel_name')}`" for p in panels[:25]]
            hub_container.add_text(
                f"**Configured Panels ({len(panels)}):** " + " , ".join(p_names)
            )
        else:
            hub_container.add_text(
                "**Configured Panels:** `None`"
            )

        hub_container.add_separator(divider=True)
        hub_container.add_text(
            f"`{prefix}ticket setup` , `{prefix}ticket list`\n"
            f"`{prefix}ticket close` , `{prefix}ticket claim`\n"
            f"`{prefix}ticket add <@user>` , `{prefix}ticket remove <@user>`\n"
            f"`{prefix}ticket transcript` , `{prefix}ticket delete <name>`"
        )
        hub_container.add_separator(divider=True)
        hub_container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, hub_container)

    @ticket_group.command(
        name="setup",
        description="Launch the interactive Slide Dashboard to configure and deploy a ticket panel.",
    )
    @commands.has_permissions(manage_guild=True)
    async def ticket_setup(self, ctx: CustomContext, embed_name: str | None = None) -> None:
        """Launch the 4-step Slide Wizard."""
        wizard = TicketSetupWizard(self, ctx.author, initial_embed=embed_name)
        dashboard_container = wizard.get_dashboard_container(ctx.guild)
        await send_container_response(ctx, dashboard_container, view=wizard)

    @ticket_group.command(
        name="close",
        description="Close the active ticket channel with optional reason.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ticket_close_cmd(self, ctx: CustomContext, *, reason: str = "Issue resolved") -> None:
        """Command to close active ticket channel."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket:
            await ctx.send("This channel is not an active ticket channel.")
            return
        await self.execute_ticket_close(ctx, ticket, reason=reason)

    @ticket_group.command(
        name="claim",
        description="Claim the current active ticket.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ticket_claim_cmd(self, ctx: CustomContext) -> None:
        """Command to claim active ticket."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket:
            await ctx.send("This channel is not an active ticket channel.")
            return

        claimed_by = ticket.get("claimed_by")
        if claimed_by and claimed_by == ctx.author.id:
            await ctx.send("You have already claimed this ticket.")
            return

        await self.bot.ticket_mgr.claim_ticket(ctx.channel.id, ctx.author.id)
        await ctx.send(f"**Ticket Claimed** • {ctx.author.mention} is now handling this ticket.")

    @ticket_group.command(
        name="add",
        description="Add a member to the current ticket channel.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ticket_add_user(self, ctx: CustomContext, member: discord.Member) -> None:
        """Add user to ticket channel."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket or not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("This channel is not an active ticket channel.")
            return

        await ctx.channel.set_permissions(
            member,
            read_messages=True,
            send_messages=True,
            attach_files=True,
            embed_links=True,
            read_message_history=True,
            reason=f"Added to ticket by {ctx.author}",
        )
        await ctx.send(f"Added {member.mention} to this ticket.")

    @ticket_group.command(
        name="remove",
        description="Remove a member from the current ticket channel.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ticket_remove_user(self, ctx: CustomContext, member: discord.Member) -> None:
        """Remove user from ticket channel."""
        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        if not ticket or not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("This channel is not an active ticket channel.")
            return

        if member.id == ticket.get("user_id"):
            await ctx.send("You cannot remove the ticket creator from their own ticket.")
            return

        await ctx.channel.set_permissions(member, overwrite=None, reason=f"Removed from ticket by {ctx.author}")
        await ctx.send(f"Removed {member.mention} from this ticket.")

    @ticket_group.command(
        name="transcript",
        description="Generate and download the HTML transcript of this ticket channel.",
    )
    @commands.has_permissions(manage_messages=True)
    async def ticket_transcript_cmd(self, ctx: CustomContext) -> None:
        """Generate and send transcript."""
        if not isinstance(ctx.channel, (discord.TextChannel, discord.Thread)):
            await ctx.send("Transcripts are only supported in text channels.")
            return

        ticket = await self.bot.ticket_mgr.get_ticket(ctx.channel.id)
        file = await generate_html_transcript(ctx.channel, ticket, bot=self.bot)
        await ctx.send(content="Here is the transcript for this ticket:", file=file)

    @ticket_group.command(
        name="list",
        description="List all active ticket panels configured in this server.",
    )
    @commands.has_permissions(manage_guild=True)
    async def ticket_list_panels(self, ctx: CustomContext) -> None:
        """List configured panels."""
        panels = await self.bot.ticket_mgr.list_panels(ctx.guild.id)
        if not panels:
            await ctx.send("No ticket panels configured yet. Use `?ticket setup` to create one.")
            return

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=f"**Configured Ticket Panels ({len(panels)})**\n> Server: **{ctx.guild.name}**"
        )
        container.add_separator(divider=True)

        lines = []
        for i, p in enumerate(panels[:15], 1):
            ch_m = f"<#{p.get('channel_id')}>"
            cat_m = f"<#{p.get('category_id')}>" if p.get("category_id") else "*Auto*"
            lines.append(f"**{i}. {p.get('panel_name')}** • Channel: {ch_m} • Category: {cat_m}")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, container)

    @ticket_group.command(
        name="delete",
        description="Delete a configured ticket panel. Usage: ?ticket delete <panel_name>",
    )
    @commands.has_permissions(manage_guild=True)
    async def ticket_delete_panel(self, ctx: CustomContext, panel_name: str) -> None:
        """Delete a ticket panel."""
        clean_name = panel_name.lower().strip()
        existing = await self.bot.ticket_mgr.get_panel(ctx.guild.id, clean_name)
        if not existing:
            await ctx.send(f"Panel `{clean_name}` not found. Use `?ticket list` to see configured panels.")
            return

        # Attempt to delete deployed message if possible
        ch_id = existing.get("channel_id")
        msg_id = existing.get("message_id")
        if ch_id and msg_id:
            try:
                ch = ctx.guild.get_channel(ch_id)
                if isinstance(ch, discord.TextChannel):
                    msg = await ch.fetch_message(msg_id)
                    await msg.delete()
            except Exception:
                pass

        await self.bot.ticket_mgr.delete_panel(ctx.guild.id, clean_name)
        await ctx.send(f"Ticket panel `{clean_name}` has been deleted.")


async def setup(bot: CicadaBot) -> None:
    await bot.add_cog(TicketSystem(bot))
