"""
Kyro Discord Bot - Native Music Controller Interactive Views
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord

if TYPE_CHECKING:
    from src.core.bot import KyroBot
    from src.cogs.music._player import GuildPlayer

logger = logging.getLogger("Kyro.Music.Views")


class MusicControlView(discord.ui.View):
    """Interactive media control row matching exact screenshot design."""

    def __init__(self, bot: KyroBot, player: Optional[GuildPlayer] = None, guild_id: Optional[int] = None) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.player = player
        self.guild_id = guild_id or (player.guild.id if player else 0)

    def _get_player(self, interaction: discord.Interaction) -> Optional[GuildPlayer]:
        if self.player:
            return self.player
        music_cog = self.bot.get_cog("Music")
        if music_cog and hasattr(music_cog, "controller"):
            return music_cog.controller.get_player(interaction.guild_id)
        return None

    @discord.ui.button(
        label="Pause",
        emoji="⏸️",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:playpause",
    )
    async def btn_pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player or not player.is_connected:
            await interaction.response.send_message("❌ Player is not connected to a voice channel.", ephemeral=True)
            return

        if player.is_paused:
            player.resume()
            button.label = "Pause"
            button.emoji = "⏸️"
            state = "Resumed"
        elif player.is_playing:
            player.pause()
            button.label = "Resume"
            button.emoji = "▶️"
            state = "Paused"
        else:
            state = "Idle"

        await interaction.response.send_message(f"▶️ **{state}** playback.", ephemeral=True)

    @discord.ui.button(
        label="Skip",
        emoji="⏭️",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:skip",
    )
    async def btn_skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player or not player.is_connected:
            await interaction.response.send_message("❌ Player is not connected.", ephemeral=True)
            return

        await player.skip()
        await interaction.response.send_message("⏭️ **Skipped** to the next song.", ephemeral=True)

    @discord.ui.button(
        label="Vol -",
        emoji="🔉",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:voldown",
    )
    async def btn_vol_down(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("❌ Player not active.", ephemeral=True)
            return

        cur_vol = int(player.volume * 100)
        new_vol = player.set_volume(cur_vol - 10)
        await interaction.response.send_message(f"🔉 Volume set to **{new_vol}%**", ephemeral=True)

    @discord.ui.button(
        label="Vol +",
        emoji="🔊",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:volup",
    )
    async def btn_vol_up(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("❌ Player not active.", ephemeral=True)
            return

        cur_vol = int(player.volume * 100)
        new_vol = player.set_volume(cur_vol + 10)
        await interaction.response.send_message(f"🔊 Volume set to **{new_vol}%**", ephemeral=True)

    @discord.ui.button(
        label="Stop",
        emoji="⏹️",
        style=discord.ButtonStyle.danger,
        custom_id="kyro:music:stop",
    )
    async def btn_stop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("❌ Player not active.", ephemeral=True)
            return

        await player.stop()
        await interaction.response.send_message("⏹️ Player **Stopped** and disconnected.", ephemeral=True)
