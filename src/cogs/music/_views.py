"""
Cicada 3301 Discord Bot - Music Interactive UI Views
Interactive Components V2 Action Row Buttons for Now Playing Player Card.
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
    """Interactive button row for Now Playing player container."""

    def __init__(self, bot: CicadaBot, controller: MusicController, guild_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.controller = controller
        self.guild_id = guild_id

    async def _check_user_voice(self, interaction: discord.Interaction) -> bool:
        """Ensure user is connected to the same voice channel as the bot."""
        if not interaction.user or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Invalid user context.", ephemeral=True)
            return False

        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You must be in a Voice Channel to use music controls.", ephemeral=True)
            return False

        guild = interaction.guild
        if guild and guild.voice_client and guild.voice_client.channel != interaction.user.voice.channel:
            await interaction.response.send_message("You must be in the same voice channel as the bot.", ephemeral=True)
            return False

        return True

    @discord.ui.button(
        label="Pause / Resume",
        style=discord.ButtonStyle.secondary,
        custom_id="music:pause_resume",
        emoji="⏯️",
    )
    async def pause_resume_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        guild = interaction.guild
        if not guild or not guild.voice_client:
            await interaction.response.send_message("No music is currently active.", ephemeral=True)
            return

        vc: discord.VoiceClient = guild.voice_client
        if vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Playback paused.", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Playback resumed.", ephemeral=True)
        else:
            await interaction.response.send_message("No active audio stream.", ephemeral=True)

    @discord.ui.button(
        label="Skip",
        style=discord.ButtonStyle.secondary,
        custom_id="music:skip",
        emoji="⏭️",
    )
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        guild = interaction.guild
        if not guild or not guild.voice_client or not guild.voice_client.is_playing():
            await interaction.response.send_message("No track is currently playing.", ephemeral=True)
            return

        guild.voice_client.stop()
        await interaction.response.send_message("⏭️ Skipped track.", ephemeral=True)

    @discord.ui.button(
        label="Stop",
        style=discord.ButtonStyle.danger,
        custom_id="music:stop",
        emoji="⏹️",
    )
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        guild = interaction.guild
        if not guild or not guild.voice_client:
            await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
            return

        self.controller.clear_guild(guild.id)
        await guild.voice_client.disconnect()
        await interaction.response.send_message("⏹️ Playback stopped and disconnected.", ephemeral=True)

    @discord.ui.button(
        label="Loop",
        style=discord.ButtonStyle.secondary,
        custom_id="music:loop",
        emoji="🔁",
    )
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        current = self.controller.get_loop(self.guild_id)
        next_mode = "track" if current == "off" else ("queue" if current == "track" else "off")
        self.controller.set_loop(self.guild_id, next_mode)
        await interaction.response.send_message(f"🔁 Loop mode set to **{next_mode.upper()}**.", ephemeral=True)

    @discord.ui.button(
        label="Queue",
        style=discord.ButtonStyle.secondary,
        custom_id="music:queue",
        emoji="📜",
    )
    async def queue_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        queue = self.controller.get_queue(self.guild_id)
        current = self.controller.get_current(self.guild_id)

        if not current and not queue:
            await interaction.response.send_message("The queue is currently empty.", ephemeral=True)
            return

        lines = []
        if current:
            dur_m = current.duration // 60
            dur_s = current.duration % 60
            lines.append(f"**Now Playing:** [{current.title}]({current.url}) (`{dur_m}:{dur_s:02d}`)\n")
        if queue:
            lines.append(f"**Up Next ({len(queue)} tracks):**")
            for i, t in enumerate(queue[:10], 1):
                dm = t.duration // 60
                ds = t.duration % 60
                lines.append(f"`{i}.` [{t.title}]({t.url}) - `{dm}:{ds:02d}`")
            if len(queue) > 10:
                lines.append(f"-# ...and {len(queue) - 10} more tracks in queue.")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)
