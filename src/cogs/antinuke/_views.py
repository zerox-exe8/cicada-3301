from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord import ui

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
        from src.utils.containers import build_container_payload

        payload = build_container_payload(container)
        await interaction.response.edit_message(content=payload.get("content"), embed=payload.get("embed"), view=new_view)

    @ui.select(
        cls=ui.Select,
        placeholder="Select Punishment Action...",
        options=[
            discord.SelectOption(label="Ban Perpetrator", value="ban", description="Bans the unauthorized attacker"),
            discord.SelectOption(label="Kick Perpetrator", value="kick", description="Kicks the unauthorized attacker"),
            discord.SelectOption(label="Strip Roles Only", value="strip_roles", description="Strips all manageable roles"),
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
            discord.SelectOption(label="Anti-Ban", value="ban", description="Rollback unauthorized bans"),
            discord.SelectOption(label="Anti-Kick", value="kick", description="Prevent unauthorized member kicks"),
            discord.SelectOption(label="Anti-Bot", value="bot", description="Block unauthorized bot additions"),
            discord.SelectOption(label="Anti-Channel Create", value="channel_create", description="Block mass channel spam"),
            discord.SelectOption(label="Anti-Channel Delete", value="channel_delete", description="Auto-recreate deleted channels"),
            discord.SelectOption(label="Anti-Channel Update", value="channel_update", description="Prevent channel overwrites tampering"),
            discord.SelectOption(label="Anti-Role Create", value="role_create", description="Block mass role spam"),
            discord.SelectOption(label="Anti-Role Delete", value="role_delete", description="Auto-recreate deleted roles"),
            discord.SelectOption(label="Anti-Role Update", value="role_update", description="Prevent role tampering"),
            discord.SelectOption(label="Anti-Everyone Disarm", value="everyone", description="Disarm @everyone permissions escalation"),
            discord.SelectOption(label="Anti-Member Role", value="member_role", description="Prevent backdoor admin role grants"),
            discord.SelectOption(label="Anti-Vanity", value="vanity", description="Restore hijacked vanity URLs"),
            discord.SelectOption(label="Anti-Webhook Create", value="webhook_create", description="Instant rogue webhook killer"),
            discord.SelectOption(label="Anti-Webhook Delete", value="webhook_delete", description="Protect webhook deletions"),
            discord.SelectOption(label="Anti-Prune", value="prune", description="Intercept mass member prune raids"),
            discord.SelectOption(label="Anti-Server Update", value="guild_update", description="Prevent server settings tampering"),
            discord.SelectOption(label="Anti-AutoMod Rule", value="automod", description="Protect AutoMod rules against abuse"),
            discord.SelectOption(label="Anti-Emoji", value="emoji", description="Prevent mass emoji deletion raids"),
            discord.SelectOption(label="Anti-Sticker", value="sticker", description="Prevent mass sticker deletion raids"),
            discord.SelectOption(label="Anti-Integration", value="integration", description="Block unauthorized integrations"),
        ],
        row=2,
    )
    async def toggle_module(self, interaction: discord.Interaction, select: ui.Select) -> None:
        """Toggle an individual protection module."""
        chosen_module = select.values[0]
        curr_state = self.bot.antinuke_mgr.is_module_enabled(self.guild.id, chosen_module)
        key = f"{chosen_module}_protection"
        await self.bot.antinuke_mgr.update_settings(self.guild.id, **{key: not curr_state})

        from src.cogs.antinuke.panel import build_antinuke_card
        container, new_view = build_antinuke_card(self.bot, self.guild, self.author_id)
        from src.utils.containers import build_container_payload

        payload = build_container_payload(container)
        await interaction.response.edit_message(content=payload.get("content"), embed=payload.get("embed"), view=new_view)
