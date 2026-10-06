from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
import discord
from discord import ui

from src.utils.containers import KyroContainer, edit_container_response, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.Setup")

MODULE_CHOICES = [
    ("all", "Select All"),
    ("ban", "Anti-Ban"),
    ("kick", "Anti-Kick"),
    ("bot", "Anti-Bot"),
    ("prune", "Anti-Prune"),
    ("channel_create", "Anti-Channel Create"),
    ("channel_delete", "Anti-Channel Delete"),
    ("channel_update", "Anti-Channel Update"),
    ("role_create", "Anti-Role Create"),
    ("role_delete", "Anti-Role Delete"),
    ("role_update", "Anti-Role Update"),
    ("everyone", "Anti-Everyone"),
    ("member_role", "Anti-Member Role"),
    ("vanity", "Anti-Vanity"),
    ("webhook_create", "Anti-Webhook Create"),
    ("webhook_delete", "Anti-Webhook Delete"),
    ("guild_update", "Anti-Server Update"),
    ("automod", "Anti-AutoMod"),
    ("emoji", "Anti-Emoji Delete"),
    ("sticker", "Anti-Sticker Delete"),
    ("integration", "Anti-Integration"),
]

ALL_MODULE_KEYS = [k for k, _ in MODULE_CHOICES if k != "all"]


class AntinukeSetupWizard(ui.View):
    """
    Slide-Based Setup for `,antinuke setup`:
    Slide 1: Select Protection Modules (Multi-Select with 'Select All' at top) + Continue >
    Slide 2: Punishment Action (Ban / Kick / Quarantine) + < Back + Continue >
    Slide 3: Logs Channel (Auto-Create Private #kyro_logs OR Select Channel) + < Back + Continue >
    Slide 4: Review Summary & Save Action
    """

    SLIDES = [
        ("modules", "Step 1: Select Modules", "Choose which protection modules you want to enable for your server."),
        ("punishment", "Step 2: Punishment Action", "Choose what action to take when someone attacks or breaks rules."),
        ("logs", "Step 3: Logs Channel", "Choose where antinuke alerts and server audit logs should be sent."),
        ("deploy", "Step 4: Review & Finish", "Review your settings and enable Antinuke."),
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

        # Pre-populate state from existing settings if available
        existing_cfg = self.bot.antinuke_mgr.get_settings(guild.id)
        self.punishment: str = existing_cfg.get("punishment", "ban")

        # Load currently enabled modules (default to all if new setup)
        self.selected_modules: set[str] = set()
        for k in ALL_MODULE_KEYS:
            if existing_cfg.get(f"{k}_protection", True):
                self.selected_modules.add(k)
        if not self.selected_modules:
            self.selected_modules = set(ALL_MODULE_KEYS)

        existing_log = self.bot.antinuke_mgr.get_log_channel(guild)
        if existing_log:
            self.log_mode: str = "existing"
            self.selected_log_channel_id: int | None = existing_log.id
        else:
            self.log_mode: str = "auto"
            self.selected_log_channel_id = None

        self._build_components_for_slide()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the invoker can control this setup session."""
        if interaction.user.id != self.author.id:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=f"**Access Denied**\n> Only {self.author.mention} can control this setup session."
            )
            await send_container_response(interaction, container, ephemeral=True)
            return False
        return True

    def _build_components_for_slide(self) -> None:
        """Rebuild view items dynamically according to current slide index."""
        self.clear_items()
        slide_key, _, _ = self.SLIDES[self.current_slide_idx]

        if slide_key == "modules":
            # Slide 1: Multi-Select Modules with "Select All" at top
            is_all_selected = len(self.selected_modules) == len(ALL_MODULE_KEYS)
            options: list[discord.SelectOption] = []

            for key, label in MODULE_CHOICES:
                if key == "all":
                    options.append(
                        discord.SelectOption(
                            label=label,
                            value=key,
                            default=is_all_selected,
                        )
                    )
                else:
                    options.append(
                        discord.SelectOption(
                            label=label,
                            value=key,
                            default=(key in self.selected_modules),
                        )
                    )

            select = ui.Select(
                placeholder="Select modules to enable...",
                min_values=1,
                max_values=len(options),
                options=options,
                custom_id="setup_select_modules",
                row=0,
            )
            select.callback = self._on_modules_selected
            self.add_item(select)

            # Back button (disabled on Slide 1)
            btn_back_dis = ui.Button(
                label="Back",
                style=discord.ButtonStyle.secondary,
                disabled=True,
                row=1,
            )
            self.add_item(btn_back_dis)

            btn_continue = ui.Button(
                label="Continue >",
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "punishment":
            # Slide 2: Punishment Select Menu (Clean options: Ban, Kick, Quarantine)
            select = ui.Select(
                placeholder="Select punishment action...",
                options=[
                    discord.SelectOption(
                        label="Ban",
                        value="ban",
                        default=(self.punishment == "ban"),
                    ),
                    discord.SelectOption(
                        label="Kick",
                        value="kick",
                        default=(self.punishment == "kick"),
                    ),
                    discord.SelectOption(
                        label="Quarantine",
                        value="strip_roles",
                        default=(self.punishment == "strip_roles"),
                    ),
                ],
                custom_id="setup_select_punishment",
                row=0,
            )
            select.callback = self._on_punishment_selected
            self.add_item(select)

            btn_back = ui.Button(
                label="< Back",
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_continue = ui.Button(
                label="Continue >",
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "logs":
            # Slide 3: Unified Logs Configuration (Optional dropdown - defaults to auto-created #kyro_logs)
            channel_select = ui.ChannelSelect(
                channel_types=[discord.ChannelType.text],
                placeholder="Select logs channel (Optional)...",
                custom_id="setup_select_log_ch",
                row=0,
            )
            channel_select.callback = self._on_log_channel_selected
            self.add_item(channel_select)

            btn_back = ui.Button(
                label="< Back",
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_continue = ui.Button(
                label="Continue >",
                style=discord.ButtonStyle.secondary,
                row=1,
            )
            btn_continue.callback = self._on_continue_clicked
            self.add_item(btn_continue)

        elif slide_key == "deploy":
            # Slide 4: Review & Deploy
            btn_back = ui.Button(
                label="< Back",
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_deploy = ui.Button(
                label="Enable Antinuke",
                style=discord.ButtonStyle.success,
                custom_id="setup_btn_deploy",
                row=0,
            )
            btn_deploy.callback = self._on_deploy_clicked
            self.add_item(btn_deploy)

    def get_dashboard_container(self) -> KyroContainer:
        """Render the clean Components V2 Antinuke Setup container."""
        container = KyroContainer(accent_color=None)
        slide_key, slide_title, slide_desc = self.SLIDES[self.current_slide_idx]
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")

        container.add_section(
            content=(
                "**Kyro Antinuke**\n"
                f"> **{slide_title}**\n"
                f"> *{slide_desc}*"
            )
        )
        container.add_separator(divider=True)

        total_mods = len(ALL_MODULE_KEYS)
        sel_count = len(self.selected_modules)
        if sel_count == total_mods:
            mod_disp = f"`All Modules ({total_mods}/{total_mods})`"
        else:
            mod_disp = f"`{sel_count}/{total_mods} Modules Selected`"

        overview_lines = [
            f"> {dot} **Protection Modules:** {mod_disp}",
            f"> {dot} **Status:** {sw_on}",
        ]
        container.add_text("\n".join(overview_lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Step {self.current_slide_idx + 1}/4 • Setup for {self.author.display_name}")

        return container

    async def _on_modules_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        was_all_selected = len(self.selected_modules) == len(ALL_MODULE_KEYS)

        if not values:
            self.selected_modules = set(ALL_MODULE_KEYS)
        elif "all" in values and not was_all_selected:
            # User newly selected "Select All"
            self.selected_modules = set(ALL_MODULE_KEYS)
        elif "all" in values and was_all_selected and len(values) < len(MODULE_CHOICES):
            # User was at all selected, but unchecked one or more specific items
            self.selected_modules = set(v for v in values if v != "all")
        else:
            # Explicit selection of specific modules
            self.selected_modules = set(v for v in values if v != "all")
            if not self.selected_modules and "all" in values:
                self.selected_modules = set(ALL_MODULE_KEYS)

        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_punishment_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        if values:
            self.punishment = values[0]
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_log_channel_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        if values:
            self.selected_log_channel_id = int(values[0])
            self.log_mode = "existing"
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_continue_clicked(self, interaction: discord.Interaction) -> None:
        if self.current_slide_idx < len(self.SLIDES) - 1:
            self.current_slide_idx += 1
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_back_clicked(self, interaction: discord.Interaction) -> None:
        if self.current_slide_idx > 0:
            self.current_slide_idx -= 1
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_deploy_clicked(self, interaction: discord.Interaction) -> None:
        """Persist settings, initialize unified logs channel, snapshot guild, and display final panel."""
        await interaction.response.defer()

        # 1. Resolve & secure log channel
        target_log_channel: discord.TextChannel | None = None
        if self.log_mode == "auto":
            from src.cogs.antinuke.panel import ensure_unified_log_channel
            target_log_channel, _ = await ensure_unified_log_channel(self.bot, self.guild, self.author)
        elif self.selected_log_channel_id:
            target_log_channel = self.guild.get_channel(self.selected_log_channel_id)
            if target_log_channel:
                try:
                    if target_log_channel.permissions_for(self.guild.default_role).view_channel:
                        await target_log_channel.set_permissions(
                            self.guild.default_role,
                            view_channel=False,
                            read_messages=False,
                            send_messages=False,
                            reason="Kyro Antinuke: secure designated log channel",
                        )
                except Exception as e:
                    logger.warning(f"Could not secure channel {target_log_channel.id}: {e}")

                await self.bot.antinuke_mgr.update_settings(
                    self.guild.id, log_channel_id=target_log_channel.id
                )
                try:
                    await self.bot.log_mgr.set_log_channel(self.guild.id, "all", target_log_channel.id)
                except Exception:
                    pass

        # 2. Update all module settings
        module_updates = {}
        for k in ALL_MODULE_KEYS:
            module_updates[f"{k}_protection"] = (k in self.selected_modules)

        # 3. Update master settings
        await self.bot.antinuke_mgr.update_settings(
            self.guild.id,
            enabled=True,
            punishment=self.punishment,
            **module_updates,
        )

        # 4. Snapshot state
        self.bot.antinuke_mgr.snapshot_guild_state(self.guild)

        # 5. Success confirmation response
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")

        total_mods = len(ALL_MODULE_KEYS)
        sel_count = len(self.selected_modules)
        if sel_count == total_mods:
            mod_disp = f"`All Modules ({total_mods}/{total_mods})`"
        else:
            mod_disp = f"`{sel_count}/{total_mods} Modules Selected`"

        success_container = KyroContainer(accent_color=None)
        success_container.add_section(
            content=(
                "**Kyro Antinuke**\n"
                "> *Antinuke is now active and protecting your server.*"
            )
        )
        success_container.add_separator(divider=True)
        summary_lines = [
            f"> {dot} **Protection Modules:** {mod_disp}",
            f"> {dot} **Status:** {sw_on}",
        ]
        success_container.add_text("\n".join(summary_lines))
        success_container.add_separator(divider=True)
        success_container.add_text(f"-# Configured by {self.author.display_name} • <t:{int(discord.utils.utcnow().timestamp())}:f>")

        # Attach control panel view so user can manage further
        from src.cogs.antinuke._views import AntinukeControlView
        ctrl_view = AntinukeControlView(self.bot, self.guild, self.author.id)
        await edit_container_response(interaction, success_container, view=ctrl_view)
