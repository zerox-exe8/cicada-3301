"""
Cicada 3301 Discord Bot - Music Interactive UI Views
Essential Components V2 Action Row Buttons for Now Playing Player Card.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord

if TYPE_CHECKING:
    from src.core.bot import CicadaBot
    from src.cogs.music._controller import MusicController

logger = logging.getLogger("Cicada.Music.Views")


class MusicControlView(discord.ui.View):
    """Essential, responsive music button controller."""

    def __init__(self, bot: CicadaBot, controller: MusicController, guild_id: int = 0) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.controller = controller
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

    async def _check_user_voice(self, interaction: discord.Interaction) -> bool:
        """Ensure user is connected to the same voice channel as the bot."""
        if not interaction.user or not isinstance(interaction.user, discord.Member):
            if not interaction.response.is_done():
                await interaction.response.send_message("Invalid user context.", ephemeral=True)
            return False

        if not interaction.user.voice or not interaction.user.voice.channel:
            if not interaction.response.is_done():
                await interaction.response.send_message("You must be in a Voice Channel to use music controls.", ephemeral=True)
            return False

        guild = interaction.guild
        if guild and guild.voice_client and guild.voice_client.channel != interaction.user.voice.channel:
            if not interaction.response.is_done():
                await interaction.response.send_message("You must be in the same voice channel as the bot.", ephemeral=True)
            return False

        return True

    @discord.ui.button(
        label="Pause",
        style=discord.ButtonStyle.secondary,
        custom_id="music:pause",
        row=0,
    )
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        guild = interaction.guild
        if not guild or not guild.voice_client:
            if not interaction.response.is_done():
                await interaction.response.send_message("No music is currently active.", ephemeral=True)
            return

        vc: discord.VoiceClient = guild.voice_client
        e_reg = self.bot.custom_emojis
        if vc.is_playing():
            vc.pause()
            pause_icon = e_reg.get("paused", "")
            prefix = f"{pause_icon} " if pause_icon else ""
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{prefix}Playback paused.", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            play_icon = e_reg.get("music_playing", "")
            prefix = f"{play_icon} " if play_icon else ""
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{prefix}Playback resumed.", ephemeral=True)
        else:
            if not interaction.response.is_done():
                await interaction.response.send_message("No active audio stream.", ephemeral=True)

    @discord.ui.button(
        label="Skip",
        style=discord.ButtonStyle.secondary,
        custom_id="music:skip",
        row=0,
    )
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        guild = interaction.guild
        if not guild or not guild.voice_client or (not guild.voice_client.is_playing() and not guild.voice_client.is_paused()):
            if not interaction.response.is_done():
                await interaction.response.send_message("No track is currently playing.", ephemeral=True)
            return

        guild.voice_client.stop()
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

        gid = interaction.guild_id or self.guild_id
        cur_vol = self.controller.get_volume(gid)
        new_vol = max(0.0, round(cur_vol - 0.1, 2))
        self.controller.set_volume(gid, new_vol)

        vc = interaction.guild.voice_client if interaction.guild else None
        if vc and vc.source and hasattr(vc.source, "volume"):
            vc.source.volume = new_vol

        e_reg = self.bot.custom_emojis
        vol_icon = e_reg.get("volume_down", "")
        prefix = f"{vol_icon} " if vol_icon else ""
        pct = int(new_vol * 100)
        if not interaction.response.is_done():
            await interaction.response.send_message(f"{prefix}Volume decreased to **{pct}%**.", ephemeral=True)

    @discord.ui.button(
        label="Vol +",
        style=discord.ButtonStyle.secondary,
        custom_id="music:vol_up",
        row=0,
    )
    async def volup_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        gid = interaction.guild_id or self.guild_id
        cur_vol = self.controller.get_volume(gid)
        new_vol = min(1.5, round(cur_vol + 0.1, 2))
        self.controller.set_volume(gid, new_vol)

        vc = interaction.guild.voice_client if interaction.guild else None
        if vc and vc.source and hasattr(vc.source, "volume"):
            vc.source.volume = new_vol

        e_reg = self.bot.custom_emojis
        vol_icon = e_reg.get("volume_up", "")
        prefix = f"{vol_icon} " if vol_icon else ""
        pct = int(new_vol * 100)
        if not interaction.response.is_done():
            await interaction.response.send_message(f"{prefix}Volume increased to **{pct}%**.", ephemeral=True)

    @discord.ui.button(
        label="Stop",
        style=discord.ButtonStyle.danger,
        custom_id="music:stop",
        row=0,
    )
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        guild = interaction.guild
        if not guild or not guild.voice_client:
            if not interaction.response.is_done():
                await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
            return

        self.controller.clear_guild(guild.id)
        await guild.voice_client.disconnect()
        e_reg = self.bot.custom_emojis
        stop_icon = e_reg.get("icons_stop_button", "")
        prefix = f"{stop_icon} " if stop_icon else ""
        if not interaction.response.is_done():
            await interaction.response.send_message(f"{prefix}Playback stopped and disconnected.", ephemeral=True)
