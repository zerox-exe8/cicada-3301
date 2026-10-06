from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
import discord
from discord import ui

from src.utils.containers import KyroContainer, edit_container_response, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.SetupWizard")


class AntinukeSetupWizard(ui.View):
    """
    Slide-Based Setup Wizard for `,antinuke setup`:
    Slide 1: Master Defense Switch (Enable / Disable) + Continue >
    Slide 2: Attacker Punishment Action (Ban / Kick / Quarantine) + < Back + Continue >
    Slide 3: Unified Security & Audit Logs (Auto-Create Private #kyro_logs OR Select Channel) + < Back + Continue >
    Slide 4: Review Summary & Deploy / Arm Action
    """

    SLIDES = [
        ("status", "Step 1: Master Defense Switch", "Enable or arm the core Antinuke defense protocol across your server."),
        ("punishment", "Step 2: Punishment Action", "Choose the disciplinary measure taken against unauthorized attackers or compromised admins."),
        ("logs", "Step 3: Unified Security Logs", "Configure where security alerts and server audit streams are posted (strictly secured)."),
        ("deploy", "Step 4: Review & Deploy", "Review your configured settings and arm real-time protection."),
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
        self.enabled: bool = True  # Default to armed for wizard setup
        self.punishment: str = existing_cfg.get("punishment", "ban")
        existing_log = self.bot.antinuke_mgr.get_log_channel(guild)
        if existing_log:
            self.log_mode: str = "existing"
            self.selected_log_channel_id: int | None = existing_log.id
        else:
            self.log_mode: str = "auto"
            self.selected_log_channel_id = None

        self._build_components_for_slide()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the invoker can control this setup wizard session."""
        if interaction.user.id != self.author.id:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=f"**Access Denied**\n> Only {self.author.mention} can control this setup wizard session."
            )
            await send_container_response(interaction, container, ephemeral=True)
            return False
        return True

    def _build_components_for_slide(self) -> None:
        """Rebuild view items dynamically according to current slide index."""
        self.clear_items()
        slide_key, _, _ = self.SLIDES[self.current_slide_idx]

        if slide_key == "status":
            # Slide 1: Status Select Menu
            select = ui.Select(
                placeholder="Choose defense protocol status...",
                options=[
                    discord.SelectOption(
                        label="Armed & Active (Recommended)",
                        value="true",
                        description="Activate master defense and arm all 20 protection modules",
                        default=self.enabled,
                    ),
                    discord.SelectOption(
                        label="Disarmed (Configure Only)",
                        value="false",
                        description="Save configuration but keep master switch turned off",
                        default=not self.enabled,
                    ),
                ],
                custom_id="wiz_select_status",
                row=0,
            )
            select.callback = self._on_status_selected
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
            # Slide 2: Punishment Select Menu
            select = ui.Select(
                placeholder="Select disciplinary punishment...",
                options=[
                    discord.SelectOption(
                        label="Ban Perpetrator (Recommended)",
                        value="ban",
                        description="Instantly strip permissions and ban unauthorized attacker",
                        default=(self.punishment == "ban"),
                    ),
                    discord.SelectOption(
                        label="Kick Perpetrator",
                        value="kick",
                        description="Instantly strip permissions and kick attacker from server",
                        default=(self.punishment == "kick"),
                    ),
                    discord.SelectOption(
                        label="Quarantine (Strip Roles Only)",
                        value="strip_roles",
                        description="Neutralize dangerous permissions without ban or kick",
                        default=(self.punishment == "strip_roles"),
                    ),
                ],
                custom_id="wiz_select_punishment",
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
            # Slide 3: Unified Logs Configuration
            btn_auto = ui.Button(
                label="✓ Auto-Create #kyro_logs (Private)" if self.log_mode == "auto" else "Auto-Create #kyro_logs (Private)",
                style=discord.ButtonStyle.primary if self.log_mode == "auto" else discord.ButtonStyle.secondary,
                custom_id="wiz_btn_auto_logs",
                row=0,
            )
            btn_auto.callback = self._on_auto_logs_clicked
            self.add_item(btn_auto)

            channel_select = ui.ChannelSelect(
                channel_types=[discord.ChannelType.text],
                placeholder="Or pick an existing text channel...",
                custom_id="wiz_select_log_ch",
                row=1,
            )
            channel_select.callback = self._on_log_channel_selected
            self.add_item(channel_select)

            btn_back = ui.Button(
                label="< Back",
                style=discord.ButtonStyle.secondary,
                row=2,
            )
            btn_back.callback = self._on_back_clicked
            self.add_item(btn_back)

            btn_continue = ui.Button(
                label="Continue >",
                style=discord.ButtonStyle.secondary,
                row=2,
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
                label="Arm Antinuke 🛡️",
                style=discord.ButtonStyle.success,
                custom_id="wiz_btn_deploy",
                row=0,
            )
            btn_deploy.callback = self._on_deploy_clicked
            self.add_item(btn_deploy)

    def get_dashboard_container(self) -> KyroContainer:
        """Render the sleek Components V2 Antinuke Setup Wizard container."""
        container = KyroContainer(accent_color=None)
        slide_key, slide_title, slide_desc = self.SLIDES[self.current_slide_idx]
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "`[ON]`")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "`[OFF]`")

        container.add_section(
            content=(
                "**Kyro Antinuke Setup Wizard**\n"
                f"> **{slide_title}**\n"
                f"> *{slide_desc}*"
            )
        )
        container.add_separator(divider=True)

        status_tag = f"{sw_on} `Armed`" if self.enabled else f"{sw_off} `Disarmed`"
        punish_map = {"ban": "Ban Perpetrator", "kick": "Kick Perpetrator", "strip_roles": "Quarantine"}
        punish_tag = f"`{punish_map.get(self.punishment, self.punishment.capitalize())}`"

        if self.log_mode == "auto":
            log_tag = "`Auto-Create #kyro_logs (Private)`"
        elif self.selected_log_channel_id:
            log_tag = f"<#{self.selected_log_channel_id}>"
        else:
            log_tag = "`Unassigned`"

        overview_lines = [
            f"> {dot} **Master Switch:** {status_tag}",
            f"> {dot} **Attack Punishment:** {punish_tag}",
            f"> {dot} **Unified Logs:** {log_tag}",
            f"> {dot} **Protection Modules:** `All 20 Active`" if self.enabled else f"> {dot} **Protection Modules:** `Inactive`",
        ]
        container.add_text("\n".join(overview_lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Step {self.current_slide_idx + 1}/4 • Setup Session for {self.author.display_name}")

        return container

    async def _on_status_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        if values:
            self.enabled = (values[0] == "true")
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_punishment_selected(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", [])
        if values:
            self.punishment = values[0]
        self._build_components_for_slide()
        await edit_container_response(interaction, self.get_dashboard_container(), view=self)

    async def _on_auto_logs_clicked(self, interaction: discord.Interaction) -> None:
        self.log_mode = "auto"
        self.selected_log_channel_id = None
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
        """Persist settings, initialize unified logs channel, snapshot guild, and display final armed panel."""
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
                    # Secure permissions on existing selected channel if needed
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

        # 2. Update master settings
        await self.bot.antinuke_mgr.update_settings(
            self.guild.id,
            enabled=self.enabled,
            punishment=self.punishment,
        )

        # 3. Snapshot state
        self.bot.antinuke_mgr.snapshot_guild_state(self.guild)

        # 4. Success confirmation response
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        shield = self.bot.custom_emojis.get("icon_shield", "")
        badge_str = f"{shield} " if shield else ""
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "`[ON]`")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "`[OFF]`")

        punish_map = {"ban": "Ban", "kick": "Kick", "strip_roles": "Quarantine"}
        punish_tag = f"`{punish_map.get(self.punishment, self.punishment.capitalize())}`"
        status_switch = sw_on if self.enabled else sw_off
        log_tag = target_log_channel.mention if target_log_channel else "`None`"

        success_container = KyroContainer(accent_color=None)
        success_container.add_section(
            content=(
                f"**{badge_str}Antinuke Protocol Deployed**\n"
                "> *Server defense configuration has been successfully saved and armed.*"
            )
        )
        success_container.add_separator(divider=True)
        summary_lines = [
            f"> {dot} **Master Status:** {status_switch}",
            f"> {dot} **Disciplinary Action:** {punish_tag}",
            f"> {dot} **Unified Logs:** {log_tag}",
            f"> {dot} **Protection Modules:** `20 Modules Configured`",
        ]
        success_container.add_text("\n".join(summary_lines))
        success_container.add_separator(divider=True)
        success_container.add_text(f"-# Deployed by {self.author.display_name} • <t:{int(discord.utils.utcnow().timestamp())}:f>")

        # Also provide the standard control view so user can manage further
        from src.cogs.antinuke._views import AntinukeControlView
        ctrl_view = AntinukeControlView(self.bot, self.guild, self.author.id)
        await edit_container_response(interaction, success_container, view=ctrl_view)
