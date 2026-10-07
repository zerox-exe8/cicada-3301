from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord import ui

if TYPE_CHECKING:
    from src.core.bot import KyroBot

ALL_PROTECTION_KEYS = [
    "ban",
    "kick",
    "bot",
    "prune",
    "channel_create",
    "channel_delete",
    "channel_update",
    "role_create",
    "role_delete",
    "role_update",
    "everyone",
    "member_role",
    "vanity",
    "webhook_create",
    "webhook_delete",
    "guild_update",
    "automod",
    "emoji",
    "sticker",
    "integration",
]


class AntinukeControlView(ui.View):
    """Interactive Control Panel for Server Antinuke configuration."""

    def __init__(self, bot: KyroBot, guild: discord.Guild, author_id: int) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.guild = guild
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the invoker (Server Owner or Extra Owner) can click the controls."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "You are not authorized to interact with this control panel.", ephemeral=True
            )
            return False
        return True

    def to_container_components(self) -> list[dict[str, Any]]:
        """Return container components with a visual separator line between dropdown categories and the button."""
        raw = self.to_components()
        comps: list[dict[str, Any]] = []
        for r in raw:
            items = r.get("components", [])
            is_button_row = any(item.get("type") == 2 for item in items)
            if is_button_row and comps:
                comps.append({"type": 14, "divider": True})
            comps.append(r)
        return comps

    @ui.select(
        cls=ui.Select,
        placeholder="Select module(s) to toggle...",
        min_values=1,
        max_values=21,
        options=[
            discord.SelectOption(label="All Modules", value="all"),
            discord.SelectOption(label="Anti-Ban", value="ban"),
            discord.SelectOption(label="Anti-Kick", value="kick"),
            discord.SelectOption(label="Anti-Bot", value="bot"),
            discord.SelectOption(label="Anti-Prune", value="prune"),
            discord.SelectOption(label="Anti-Channel Create", value="channel_create"),
            discord.SelectOption(label="Anti-Channel Delete", value="channel_delete"),
            discord.SelectOption(label="Anti-Channel Update", value="channel_update"),
            discord.SelectOption(label="Anti-Role Create", value="role_create"),
            discord.SelectOption(label="Anti-Role Delete", value="role_delete"),
            discord.SelectOption(label="Anti-Role Update", value="role_update"),
            discord.SelectOption(label="Anti-Everyone", value="everyone"),
            discord.SelectOption(label="Anti-Member Role", value="member_role"),
            discord.SelectOption(label="Anti-Vanity", value="vanity"),
            discord.SelectOption(label="Anti-Webhook Create", value="webhook_create"),
            discord.SelectOption(label="Anti-Webhook Delete", value="webhook_delete"),
            discord.SelectOption(label="Anti-Server Update", value="guild_update"),
            discord.SelectOption(label="Anti-AutoMod", value="automod"),
            discord.SelectOption(label="Anti-Emoji Delete", value="emoji"),
            discord.SelectOption(label="Anti-Sticker Delete", value="sticker"),
            discord.SelectOption(label="Anti-Integration", value="integration"),
        ],
        row=0,
    )
    async def toggle_module(self, interaction: discord.Interaction, select: ui.Select) -> None:
        """Toggle one or more selected protection modules."""
        selected_values = select.values
        updates = {}

        if "all" in selected_values:
            curr_cfg = self.bot.antinuke_mgr.get_settings(self.guild.id)
            # If any module is currently False, enable all; else disable all
            any_disabled = any(not curr_cfg.get(f"{m}_protection", True) for m in ALL_PROTECTION_KEYS)
            new_target = True if any_disabled else False
            for m in ALL_PROTECTION_KEYS:
                updates[f"{m}_protection"] = new_target
            updates["channel_protection"] = new_target
            updates["role_protection"] = new_target
            updates["webhook_protection"] = new_target
        else:
            for mod in selected_values:
                curr_state = self.bot.antinuke_mgr.is_module_enabled(self.guild.id, mod)
                updates[f"{mod}_protection"] = not curr_state

            # Keep parent fallback flags synchronized
            updates["channel_protection"] = any(
                updates.get(f"{k}_protection", self.bot.antinuke_mgr.is_module_enabled(self.guild.id, k))
                for k in ["channel_create", "channel_delete", "channel_update"]
            )
            updates["role_protection"] = any(
                updates.get(f"{k}_protection", self.bot.antinuke_mgr.is_module_enabled(self.guild.id, k))
                for k in ["role_create", "role_delete", "role_update"]
            )
            updates["webhook_protection"] = any(
                updates.get(f"{k}_protection", self.bot.antinuke_mgr.is_module_enabled(self.guild.id, k))
                for k in ["webhook_create", "webhook_delete"]
            )

        await self.bot.antinuke_mgr.update_settings(self.guild.id, **updates)

        from src.cogs.antinuke.panel import build_antinuke_card
        container, new_view = build_antinuke_card(self.bot, self.guild, self.author_id)
        from src.utils.containers import edit_container_response
        await edit_container_response(interaction, container, view=new_view)

    @ui.select(
        cls=ui.Select,
        placeholder="Select Punishment Action...",
        options=[
            discord.SelectOption(label="ban", value="ban"),
            discord.SelectOption(label="kick", value="kick"),
            discord.SelectOption(label="quarantine", value="strip_roles", description="Remove all roles, no ban/kick"),
        ],
        row=1,
    )
    async def select_punishment(self, interaction: discord.Interaction, select: ui.Select) -> None:
        """Update punishment type."""
        chosen = select.values[0]
        await self.bot.antinuke_mgr.update_settings(self.guild.id, punishment=chosen)

        from src.cogs.antinuke.panel import build_antinuke_card
        container, new_view = build_antinuke_card(self.bot, self.guild, self.author_id)
        from src.utils.containers import edit_container_response
        await edit_container_response(interaction, container, view=new_view)

    @ui.button(label="Toggle Antinuke", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_switch(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Toggle Antinuke master switch on or off."""
        is_active = self.bot.antinuke_mgr.is_enabled(self.guild.id)
        new_state = not is_active
        if new_state:
            from src.cogs.antinuke.panel import ensure_unified_log_channel
            await ensure_unified_log_channel(self.bot, self.guild, interaction.user)

        await self.bot.antinuke_mgr.update_settings(self.guild.id, enabled=new_state)

        from src.cogs.antinuke.panel import build_antinuke_card
        container, new_view = build_antinuke_card(self.bot, self.guild, self.author_id)
        from src.utils.containers import edit_container_response
        await edit_container_response(interaction, container, view=new_view)

    @ui.button(label="Setup", style=discord.ButtonStyle.secondary, row=2)
    async def open_setup_wizard(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Launch the step-by-step setup wizard directly from the control card."""
        from src.cogs.antinuke._setup_view import AntinukeSetupWizard
        wizard = AntinukeSetupWizard(self.bot, self.guild, interaction.user)
        from src.utils.containers import edit_container_response
        await edit_container_response(interaction, wizard.get_dashboard_container(), view=wizard)
