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

    @ui.button(label="Toggle Antinuke", style=discord.ButtonStyle.primary, row=0)
    async def toggle_switch(self, interaction: discord.Interaction, button: ui.Button) -> None:
        """Toggle Antinuke master switch on or off."""
        is_active = self.bot.antinuke_mgr.is_enabled(self.guild.id)
        new_state = not is_active
        await self.bot.antinuke_mgr.update_settings(self.guild.id, enabled=new_state)

        from src.cogs.antinuke.panel import build_antinuke_card
        container, new_view = build_antinuke_card(self.bot, self.guild, self.author_id)
        from src.utils.containers import edit_container_response
        await edit_container_response(interaction, container, view=new_view)

    @ui.select(
        cls=ui.Select,
        placeholder="Select Punishment Action...",
        options=[
            discord.SelectOption(label="Ban Perpetrator", value="ban"),
            discord.SelectOption(label="Kick Perpetrator", value="kick"),
            discord.SelectOption(label="Strip Roles Only", value="strip_roles"),
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
            discord.SelectOption(label="Channel Create", value="channel_create"),
            discord.SelectOption(label="Channel Delete", value="channel_delete"),
            discord.SelectOption(label="Channel Update", value="channel_update"),
            discord.SelectOption(label="Role Create", value="role_create"),
            discord.SelectOption(label="Role Delete", value="role_delete"),
            discord.SelectOption(label="Role Update", value="role_update"),
            discord.SelectOption(label="Everyone Disarm", value="everyone"),
            discord.SelectOption(label="Member Role", value="member_role"),
            discord.SelectOption(label="Vanity URL", value="vanity"),
            discord.SelectOption(label="Webhook Create", value="webhook_create"),
            discord.SelectOption(label="Webhook Delete", value="webhook_delete"),
            discord.SelectOption(label="Server Update", value="guild_update"),
            discord.SelectOption(label="AutoMod Rule", value="automod"),
            discord.SelectOption(label="Emoji Delete", value="emoji"),
            discord.SelectOption(label="Sticker Delete", value="sticker"),
            discord.SelectOption(label="Integrations", value="integration"),
        ],
        row=2,
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
        else:
            for mod in selected_values:
                curr_state = self.bot.antinuke_mgr.is_module_enabled(self.guild.id, mod)
                updates[f"{mod}_protection"] = not curr_state

        await self.bot.antinuke_mgr.update_settings(self.guild.id, **updates)

        from src.cogs.antinuke.panel import build_antinuke_card
        container, new_view = build_antinuke_card(self.bot, self.guild, self.author_id)
        from src.utils.containers import edit_container_response
        await edit_container_response(interaction, container, view=new_view)
