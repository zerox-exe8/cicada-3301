"""
Kyro Discord Bot - Interactive UI Components (Views, Buttons, Modals)
"""

from __future__ import annotations

import discord
from discord.ext import commands


class ConfirmView(discord.ui.View):
    """Interactive confirmation prompt with Accept and Decline buttons."""

    def __init__(self, author: discord.User | discord.Member, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.value: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ You are not authorized to interact with this prompt.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancel_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        self.value = False
        self.stop()
        await interaction.response.defer()
