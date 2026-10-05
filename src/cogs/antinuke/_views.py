from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord import ui

from src.utils.containers import KyroContainer

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class AntinukeControlView(ui.View):
    """Interactive Control Panel for Server Antinuke configuration."""

    def __init__(self, bot: KyroBot, guild: discord.Guild, author_id: int) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.guild = guild
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only the invoker (who must be Owner or Extra Owner) can click the controls."""
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

        # Re-render dashboard
        from src.cogs.antinuke.panel import build_antinuke_card

        container, new_view = build_antinuke_card(self.bot, self.guild, self.author_id)
        from src.utils.containers import build_container_payload

        payload = build_container_payload(container)
        await interaction.response.edit_message(content=payload.get("content"), embed=payload.get("embed"), view=new_view)

    @ui.select(
        cls=ui.Select,
        placeholder="Select Punishment Action...",
        options=[
            discord.SelectOption(label="Ban Perpetrator", value="ban", description="Instantly bans the unauthorized attacker"),
            discord.SelectOption(label="Kick Perpetrator", value="kick", description="Kicks the unauthorized attacker from server"),
            discord.SelectOption(label="Strip Roles", value="strip_roles", description="Strips all roles without banning or kicking"),
        ],
        row=1,
    )
    async def select_punishment(self, interaction: discord.Interaction, select: ui.Select) -> None:
        """Update punishment type."""
        chosen = select.values[0]
        await self.bot.antinuke_mgr.update_settings(self.guild.id, punishment=chosen)

        from src.cogs.antinuke.panel import build_antinuke_card

        container, new_view = build_antinuke_card(self.bot, self.guild, self.author_id)
        from src.utils.containers import build_container_payload

        payload = build_container_payload(container)
        await interaction.response.edit_message(content=payload.get("content"), embed=payload.get("embed"), view=new_view)

    @ui.select(
        cls=ui.Select,
        placeholder="Toggle Protection Module...",
        options=[
            discord.SelectOption(label="Vanity URL Protection", value="vanity"),
            discord.SelectOption(label="@everyone Escalation Disarm", value="everyone"),
            discord.SelectOption(label="Role Protection (Create/Delete/Edit)", value="role"),
            discord.SelectOption(label="Channel Protection (Create/Delete/Edit)", value="channel"),
            discord.SelectOption(label="Anti-Bot (Unauthorized Bot Adds)", value="bot"),
            discord.SelectOption(label="Anti-Webhook (Instant Webhook Killer)", value="webhook"),
            discord.SelectOption(label="Anti-Ban & Anti-Kick Protection", value="ban"),
            discord.SelectOption(label="Anti-AutoMod Rule Hijack", value="automod"),
        ],
        row=2,
    )
    async def toggle_module(self, interaction: discord.Interaction, select: ui.Select) -> None:
        """Toggle an individual sub-protection module."""
        chosen_module = select.values[0]
        curr_state = self.bot.antinuke_mgr.is_module_enabled(self.guild.id, chosen_module)
        key = f"{chosen_module}_protection"
        await self.bot.antinuke_mgr.update_settings(self.guild.id, **{key: not curr_state})

        from src.cogs.antinuke.panel import build_antinuke_card

        container, new_view = build_antinuke_card(self.bot, self.guild, self.author_id)
        from src.utils.containers import build_container_payload

        payload = build_container_payload(container)
        await interaction.response.edit_message(content=payload.get("content"), embed=payload.get("embed"), view=new_view)
