from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
import discord
from discord import ui

from src.utils.containers import KyroContainer, edit_container_response, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Meeting.Setup")

MEETING_MODULES = [
    ("all", "All Intelligence Modules"),
    ("summary", "Executive Summary"),
    ("decisions", "Key Decisions Extraction"),
    ("action_items", "Action Items & Tasks"),
    ("topics", "Discussion Topics"),
    ("auto_leave", "Auto-End on Empty VC"),
]

ALL_MEETING_KEYS = [k for k, _ in MEETING_MODULES if k != "all"]


async def ensure_meeting_channel(
    bot: KyroBot,
    guild: discord.Guild,
    invoker: discord.Member | discord.User,
    channel_id: int | None = None,
    privacy_mode: str = "locked",
) -> tuple[discord.TextChannel | None, bool]:
    """
    Ensure the designated meeting intelligence channel exists and apply requested privacy permissions.
    Modes:
      - 'locked': @everyone can view, but cannot send messages (clean read-only feed).
      - 'hidden': Hidden from @everyone; only Administrators & Server Managers can view.
      - 'public': Normal channel; @everyone can view and send messages freely.
    """
    target_channel: discord.TextChannel | None = None
    is_new = False

    if channel_id:
        target_channel = guild.get_channel(channel_id)

    if not target_channel:
        # Check if existing kyro-meetings channel exists
        existing = discord.utils.find(
            lambda c: isinstance(c, discord.TextChannel) and c.name.lower() in ("kyro-meetings", "meeting-logs", "meetings"),
            guild.text_channels,
        )
        if existing:
            target_channel = existing

    # Create new channel if none exists
    if not target_channel:
        try:
            overwrites: dict[Any, discord.PermissionOverwrite] = {}

            # Bot permissions
            bot_member = guild.me
            overwrites[bot_member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                manage_messages=True,
            )

            if privacy_mode == "hidden":
                overwrites[guild.default_role] = discord.PermissionOverwrite(
                    view_channel=False,
                    send_messages=False,
                )
                if isinstance(invoker, discord.Member):
                    overwrites[invoker] = discord.PermissionOverwrite(
                        view_channel=True,
                        read_messages=True,
                        read_message_history=True,
                    )
            elif privacy_mode == "locked":
                overwrites[guild.default_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=False,
                    add_reactions=True,
                    read_message_history=True,
                )
            else:  # public
                overwrites[guild.default_role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

            target_channel = await guild.create_text_channel(
                "kyro-meetings",
                overwrites=overwrites,
                topic="Kyro Voice Meeting Intelligence — AI summaries, key decisions, and action items.",
                reason="Kyro Meeting: Auto-create designated meeting summaries channel",
            )
            is_new = True
        except Exception as e:
            logger.warning(f"Could not auto-create meeting channel in guild {guild.id}: {e}")
            return None, False
    else:
        # Update permissions on existing channel
        try:
            bot_member = guild.me
            await target_channel.set_permissions(
                bot_member,
                view_channel=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                reason="Kyro Meeting: Ensure bot permissions in meeting feed",
            )

            if privacy_mode == "hidden":
                await target_channel.set_permissions(
                    guild.default_role,
                    view_channel=False,
                    send_messages=False,
                    reason="Kyro Meeting: Set hidden private privacy mode",
                )
            elif privacy_mode == "locked":
                await target_channel.set_permissions(
                    guild.default_role,
                    view_channel=True,
                    send_messages=False,
                    reason="Kyro Meeting: Set locked read-only privacy mode",
                )
            else:  # public
                await target_channel.set_permissions(
                    guild.default_role,
                    view_channel=True,
                    send_messages=True,
                    reason="Kyro Meeting: Set normal public privacy mode",
                )
        except Exception as e:
            logger.warning(f"Could not update permissions on meeting channel {target_channel.id}: {e}")

    # Post initialization card if newly created
    if is_new and target_channel:
        try:
            dot = bot.custom_emojis.get("heart_dot", "•")
            mode_names = {"locked": "Locked (Read-Only)", "hidden": "Hidden (Private)", "public": "Normal (Public)"}
            mode_disp = mode_names.get(privacy_mode, "Locked")

            init_card = KyroContainer(accent_color=None)
            init_card.add_section(
                content="**Kyro Meeting Intelligence**\n> This channel is configured to receive all voice meeting reports and key decisions."
            )
            init_card.add_separator(divider=True)
            init_card.add_text(
                f"> {dot} **Channel Access:** `{mode_disp}`\n"
                f"> {dot} **Intelligence:** Summaries, Key Decisions, Action Items & Topics\n"
                f"> {dot} **Usage:** Start any meeting in VC using `,meeting start`."
            )
            init_card.add_separator(divider=True)
            init_card.add_text(f"-# Initialized by {invoker.display_name} • <t:{int(discord.utils.utcnow().timestamp())}:f>")
            await send_container_response(target_channel, init_card)
        except Exception as e:
            logger.debug(f"Notice sending init card to meeting channel: {e}")

    return target_channel, is_new


class MeetingSetupWizard(ui.View):
    """
    Slide-Based Setup Wizard for `,meeting setup`:
    Slide 1: Select Intelligence Modules (Multi-Select with 'All Modules' option) + Continue >
    Slide 2: Meeting Feed Channel (Optional Dropdown - defaults to Auto-create #kyro-meetings) + < Back + Continue >
    Slide 3: Channel Privacy Mode (Locked / Hidden / Normal) + < Back + Continue >
    Slide 4: Review Summary & Deploy Action
    """

    SLIDES = [
        ("modules", "Step 1: Select Modules", "Choose which meeting intelligence capabilities you want to enable."),
        ("channel", "Step 2: Meeting Channel", "Choose where meeting summaries should be posted (or auto-create #kyro-meetings)."),
        ("privacy", "Step 3: Channel Access & Privacy", "Choose how the meeting channel permissions should be configured."),
        ("deploy", "Step 4: Review & Finish", "Review your settings and activate Meeting Intelligence."),
    ]

    def __init__(
        self,
        bot: KyroBot,
        guild: discord.Guild,
        author: discord.User | discord.Member,
    ) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.author = author
        self.current_slide_idx: int = 0

        # Defaults
        self.selected_modules: set[str] = set(ALL_MEETING_KEYS)
        self.channel_mode: str = "auto"
        self.selected_channel_id: int | None = None
        self.privacy_mode: str = "locked"  # 'locked', 'hidden', 'public'

        self._build_components_for_slide()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the invoker can interact with this setup wizard."""
        if interaction.user.id != self.author.id:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=f"**Access Denied**\n> Only {self.author.mention} can control this setup session."
            )
            await send_container_response(interaction, container, ephemeral=True)
            return False
        return True

    def _build_components_for_slide(self) -> None:
        """Dynamically assemble Discord UI components according to current slide."""
        self.clear_items()
        slide_key, _, _ = self.SLIDES[self.current_slide_idx]

        if slide_key == "modules":
            # Slide 1: Module Multi-Select
            is_all_selected = len(self.selected_modules) == len(ALL_MEETING_KEYS)
            options: list[discord.SelectOption] = []

            for key, label in MEETING_MODULES:
                options.append(discord.SelectOption(label=label, value=key, default=False))

            sel_count = len(self.selected_modules)
            placeholder = (
                "All 5 modules selected"
                if is_all_selected
                else f"{sel_count}/5 modules selected"
            )

            select = ui.Select(
                placeholder=placeholder,
                min_values=1,
                max_values=len(options),
                options=options,
                custom_id="meeting_select_modules",
                row=0,
            )
            select.callback = self._on_modules_selected
            self.add_item(select)

            # Back button (disabled on Slide 1)
            btn_back_dis = ui.Button(label="Back", style=discord.ButtonStyle.secondary, disabled=True, row=1)
            self.add_item(btn_back_dis)

            btn_continue = ui.Button(label="Continue >", style=discord.ButtonStyle.secondary, row=1)
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "channel":
            # Slide 2: Channel Selection (Optional ChannelSelect)
            channel_select = ui.ChannelSelect(
                channel_types=[discord.ChannelType.text],
                placeholder="Select channel (Optional, defaults to auto-create)...",
                custom_id="meeting_select_channel",
                row=0,
            )
            channel_select.callback = self._on_channel_selected
            self.add_item(channel_select)

            btn_back = ui.Button(label="< Back", style=discord.ButtonStyle.secondary, row=1)
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_continue = ui.Button(label="Continue >", style=discord.ButtonStyle.secondary, row=1)
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "privacy":
            # Slide 3: Channel Privacy & Permissions
            select = ui.Select(
                placeholder="Choose channel access mode...",
                options=[
                    discord.SelectOption(
                        label="Locked (Read-Only)",
                        value="locked",
                        description="@everyone can view summaries, but cannot chat in channel",
                        default=(self.privacy_mode == "locked"),
                    ),
                    discord.SelectOption(
                        label="Hidden (Private)",
                        value="hidden",
                        description="Hidden from @everyone; only Admins & Managers can see",
                        default=(self.privacy_mode == "hidden"),
                    ),
                    discord.SelectOption(
                        label="Normal (Public Chat)",
                        value="public",
                        description="@everyone can view summaries and chat freely",
                        default=(self.privacy_mode == "public"),
                    ),
                ],
                custom_id="meeting_select_privacy",
                row=0,
            )
            select.callback = self._on_privacy_selected
            self.add_item(select)

            btn_back = ui.Button(label="< Back", style=discord.ButtonStyle.secondary, row=1)
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_continue = ui.Button(label="Continue >", style=discord.ButtonStyle.secondary, row=1)
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "deploy":
            # Slide 4: Review & Deploy
            btn_back = ui.Button(label="< Back", style=discord.ButtonStyle.secondary, row=0)
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_deploy = ui.Button(
                label="Enable Meeting Intelligence",
                style=discord.ButtonStyle.success,
                custom_id="meeting_btn_deploy",
                row=0,
            )
            btn_deploy.callback = self._on_deploy_clicked
            self.add_item(btn_deploy)

    def get_dashboard_container(self) -> KyroContainer:
        """Render the clean Components V2 Meeting Setup container."""
        container = KyroContainer(accent_color=None)
        slide_key, slide_title, slide_desc = self.SLIDES[self.current_slide_idx]
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")

        container.add_section(
            content=(
                "**Kyro Meeting Setup**\n"
                f"> **{slide_title}**\n"
                f"> *{slide_desc}*"
            )
        )
        container.add_separator(divider=True)

        total_mods = len(ALL_MEETING_KEYS)
        sel_count = len(self.selected_modules)
        mod_disp = (
            f"`All Modules ({total_mods}/{total_mods})`"
            if sel_count == total_mods
            else f"`{sel_count}/{total_mods} selected`"
        )

        if self.channel_mode == "auto":
            ch_disp = "`Auto-create #kyro-meetings`"
        elif self.selected_channel_id:
            ch_disp = f"<#{self.selected_channel_id}>"
        else:
            ch_disp = "`Auto-create #kyro-meetings`"

        privacy_names = {
            "locked": "Locked (Read-Only)",
            "hidden": "Hidden (Private)",
            "public": "Normal (Public)",
        }
        priv_disp = f"`{privacy_names.get(self.privacy_mode, 'Locked')}`"

        overview_lines = [f"> {dot} **Modules:** {mod_disp}"]
        if slide_key in ("channel", "privacy", "deploy"):
            overview_lines.append(f"> {dot} **Summary Channel:** {ch_disp}")
        if slide_key in ("privacy", "deploy"):
            overview_lines.append(f"> {dot} **Channel Mode:** {priv_disp}")
        overview_lines.append(f"> {dot} **Status:** {sw_on}")

        container.add_text("\n".join(overview_lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Step {self.current_slide_idx + 1} of 4 • Kyro Meeting Setup")
        return container

    async def _on_modules_selected(self, interaction: discord.Interaction) -> None:
        """Handle selection from modules multi-select dropdown."""
        select: ui.Select = interaction.data["values"]  # type: ignore
        values = set(select)

        if "all" in values:
            if len(self.selected_modules) == len(ALL_MEETING_KEYS):
                self.selected_modules.clear()
            else:
                self.selected_modules = set(ALL_MEETING_KEYS)
        else:
            self.selected_modules = values

        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_channel_selected(self, interaction: discord.Interaction) -> None:
        """Handle selection from channel select menu."""
        values = interaction.data.get("values", [])  # type: ignore
        if values:
            self.selected_channel_id = int(values[0])
            self.channel_mode = "existing"
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_privacy_selected(self, interaction: discord.Interaction) -> None:
        """Handle selection from privacy select menu."""
        values = interaction.data.get("values", [])  # type: ignore
        if values:
            self.privacy_mode = values[0]
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_continue_clicked(self, interaction: discord.Interaction) -> None:
        """Advance to next slide."""
        if self.current_slide_idx < len(self.SLIDES) - 1:
            self.current_slide_idx += 1
            self._build_components_for_slide()
            await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_back_clicked(self, interaction: discord.Interaction) -> None:
        """Navigate back to previous slide."""
        if self.current_slide_idx > 0:
            self.current_slide_idx -= 1
            self._build_components_for_slide()
            await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_deploy_clicked(self, interaction: discord.Interaction) -> None:
        """Deploy and persist meeting setup."""
        await interaction.response.defer()

        # Ensure channel is created / secured
        target_ch, is_new = await ensure_meeting_channel(
            self.bot,
            self.guild,
            self.author,
            channel_id=self.selected_channel_id,
            privacy_mode=self.privacy_mode,
        )

        ch_id = target_ch.id if target_ch else None
        modules_str = ",".join(sorted(self.selected_modules))

        # Persist to meeting_settings table
        try:
            query = """
            INSERT INTO meeting_settings (guild_id, enabled, channel_id, privacy_mode, modules)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT(guild_id) DO UPDATE SET
                enabled = EXCLUDED.enabled,
                channel_id = EXCLUDED.channel_id,
                privacy_mode = EXCLUDED.privacy_mode,
                modules = EXCLUDED.modules;
            """
            await self.bot.db.execute(query, self.guild.id, True, ch_id, self.privacy_mode, modules_str)
        except Exception as e:
            logger.error(f"Error persisting meeting_settings in guild {self.guild.id}: {e}", exc_info=True)

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
        ch_str = target_ch.mention if target_ch else "`Not configured`"

        privacy_names = {
            "locked": "Locked (Read-Only)",
            "hidden": "Hidden (Private)",
            "public": "Normal (Public)",
        }
        priv_str = privacy_names.get(self.privacy_mode, "Locked")

        card = KyroContainer(accent_color=None)
        card.add_section(
            content="**Kyro Meeting Intelligence Activated**\n> Meeting recording and executive summarization is now configured."
        )
        card.add_separator(divider=True)
        card.add_text(
            f"> {dot} **Status:** {sw_on}\n"
            f"> {dot} **Feed Channel:** {ch_str}\n"
            f"> {dot} **Channel Access:** `{priv_str}`\n"
            f"> {dot} **Modules Enabled:** `{len(self.selected_modules)}/5 Modules Active`"
        )
        card.add_separator(divider=True)
        card.add_text(
            f"> **Next step:** Connect to any VC and type `,meeting start` to begin recording."
        )
        card.add_separator(divider=True)
        card.add_text(f"-# Configured by {self.author.display_name} • <t:{int(discord.utils.utcnow().timestamp())}:f>")

        await edit_container_response(interaction, card, view=None)
