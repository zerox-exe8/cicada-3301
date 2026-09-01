"""
Kyro Discord Bot - Music Interactive UI Views
Essential Components V2 Action Row Buttons for Lavalink V4 Player Card.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
import wavelink

if TYPE_CHECKING:
    from src.core.bot import KyroBot
    from src.cogs.music._player import KyroPlayer

logger = logging.getLogger("Kyro.Music.Views")


class MusicControlView(discord.ui.View):
    """Interactive Components V2 Action Row controller for KyroPlayer."""

    def __init__(
        self,
        bot: KyroBot,
        player: Optional[KyroPlayer] = None,
        guild_id: int = 0,
    ) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.player = player
        self.guild_id = guild_id

        # Apply custom application emojis from assets/
        e_reg = bot.custom_emojis
        pause_em = e_reg.get_emoji_obj("paused")
        skip_em = e_reg.get_emoji_obj("skip")
        voldn_em = e_reg.get_emoji_obj("volume_down")
        volup_em = e_reg.get_emoji_obj("volume_up")
        stop_em = e_reg.get_emoji_obj("icons_stop_button")

        if pause_em:
            self.pause_button.emoji = pause_em
        if skip_em:
            self.skip_button.emoji = skip_em
        if voldn_em:
            self.voldn_button.emoji = voldn_em
        if volup_em:
            self.volup_button.emoji = volup_em
        if stop_em:
            self.stop_button.emoji = stop_em

    def _get_player(self, guild: Optional[discord.Guild]) -> Optional[KyroPlayer]:
        """Fetch active player instance."""
        if self.player:
            return self.player
        if guild and isinstance(guild.voice_client, wavelink.Player):
            return guild.voice_client  # type: ignore
        return None

    async def _check_user_voice(self, interaction: discord.Interaction) -> bool:
        """Ensure user is in the same voice channel as the bot."""
        if not interaction.user or not isinstance(interaction.user, discord.Member):
            if not interaction.response.is_done():
                await interaction.response.send_message("Invalid user context.", ephemeral=True)
            return False

        if not interaction.user.voice or not interaction.user.voice.channel:
            if not interaction.response.is_done():
                await interaction.response.send_message("You must be in a Voice Channel to use music controls.", ephemeral=True)
            return False

        guild = interaction.guild
        player = self._get_player(guild)
        if player and player.channel and player.channel != interaction.user.voice.channel:
            if not interaction.response.is_done():
                await interaction.response.send_message("You must be in the same voice channel as the bot.", ephemeral=True)
            return False

        return True

    @discord.ui.button(
        label="Pause / Resume",
        style=discord.ButtonStyle.secondary,
        custom_id="music:pause",
        row=0,
    )
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        player = self._get_player(interaction.guild)
        if not player or not player.connected:
            if not interaction.response.is_done():
                await interaction.response.send_message("No active music player found.", ephemeral=True)
            return

        e_reg = self.bot.custom_emojis
        if player.paused:
            await player.pause(False)
            play_icon = e_reg.get("music_playing", "")
            prefix = f"{play_icon} " if play_icon else ""
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{prefix}Playback resumed.", ephemeral=True)
        else:
            await player.pause(True)
            pause_icon = e_reg.get("paused", "")
            prefix = f"{pause_icon} " if pause_icon else ""
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{prefix}Playback paused.", ephemeral=True)

    @discord.ui.button(
        label="Skip",
        style=discord.ButtonStyle.secondary,
        custom_id="music:skip",
        row=0,
    )
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        player = self._get_player(interaction.guild)
        if not player or not player.current:
            if not interaction.response.is_done():
                await interaction.response.send_message("No track is currently playing.", ephemeral=True)
            return

        await player.skip(force=True)
        e_reg = self.bot.custom_emojis
        skip_icon = e_reg.get("skip", "")
        prefix = f"{skip_icon} " if skip_icon else ""
        if not interaction.response.is_done():
            await interaction.response.send_message(f"{prefix}Skipped track.", ephemeral=True)

    @discord.ui.button(
        label="Vol -",
        style=discord.ButtonStyle.secondary,
        custom_id="music:vol_down",
        row=0,
    )
    async def voldn_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        player = self._get_player(interaction.guild)
        if not player:
            if not interaction.response.is_done():
                await interaction.response.send_message("No active music player found.", ephemeral=True)
            return

        new_vol = max(0, player.volume - 10)
        await player.set_volume(new_vol)

        e_reg = self.bot.custom_emojis
        vol_icon = e_reg.get("volume_down", "")
        prefix = f"{vol_icon} " if vol_icon else ""
        if not interaction.response.is_done():
            await interaction.response.send_message(f"{prefix}Volume decreased to **{new_vol}%**.", ephemeral=True)

    @discord.ui.button(
        label="Vol +",
        style=discord.ButtonStyle.secondary,
        custom_id="music:vol_up",
        row=0,
    )
    async def volup_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        player = self._get_player(interaction.guild)
        if not player:
            if not interaction.response.is_done():
                await interaction.response.send_message("No active music player found.", ephemeral=True)
            return

        if player.volume >= 100:
            if not interaction.response.is_done():
                await interaction.response.send_message("Volume is already at maximum studio safe limit (**100%**).", ephemeral=True)
            return

        new_vol = min(100, player.volume + 10)
        await player.set_volume(new_vol)

        e_reg = self.bot.custom_emojis
        vol_icon = e_reg.get("volume_up", "")
        prefix = f"{vol_icon} " if vol_icon else ""
        if not interaction.response.is_done():
            await interaction.response.send_message(f"{prefix}Volume increased to **{new_vol}%**.", ephemeral=True)

    @discord.ui.button(
        label="Stop",
        style=discord.ButtonStyle.danger,
        custom_id="music:stop",
        row=0,
    )
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        player = self._get_player(interaction.guild)
        if not player or not player.connected:
            if not interaction.response.is_done():
                await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
            return

        player.queue.clear()
        await player.disconnect()

        e_reg = self.bot.custom_emojis
        stop_icon = e_reg.get("icons_stop_button", "")
        prefix = f"{stop_icon} " if stop_icon else ""
        if not interaction.response.is_done():
            await interaction.response.send_message(f"{prefix}Playback stopped and disconnected from voice.", ephemeral=True)
