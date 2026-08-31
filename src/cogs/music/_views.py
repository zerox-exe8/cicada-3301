"""
Cicada 3301 Discord Bot - Music Interactive UI Views
Interactive Components V2 Action Row Buttons for Now Playing Player Card.
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING
import discord

if TYPE_CHECKING:
    from src.core.bot import CicadaBot
    from src.cogs.music._controller import MusicController

logger = logging.getLogger("Cicada.Music.Views")


class MusicControlView(discord.ui.View):
    """Interactive button row matching the signature Cicada Now Playing player design."""

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

    # Row 0: Primary Controls (Pause, Skip, Queue, Stop)
    @discord.ui.button(
        label="Pause",
        style=discord.ButtonStyle.secondary,
        custom_id="music:pause",
        emoji="⏸️",
        row=0,
    )
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        guild = interaction.guild
        if not guild or not guild.voice_client:
            await interaction.response.send_message("No music is currently active.", ephemeral=True)
            return

        vc: discord.VoiceClient = guild.voice_client
        if vc.is_playing():
            vc.pause()
            button.label = "Resume"
            button.emoji = "▶️"
            await interaction.response.send_message("⏸️ Playback paused.", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            button.label = "Pause"
            button.emoji = "⏸️"
            await interaction.response.send_message("▶️ Playback resumed.", ephemeral=True)
        else:
            await interaction.response.send_message("No active audio stream.", ephemeral=True)

    @discord.ui.button(
        label="Skip",
        style=discord.ButtonStyle.secondary,
        custom_id="music:skip",
        emoji="⏭️",
        row=0,
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
        label="Queue",
        style=discord.ButtonStyle.secondary,
        custom_id="music:queue",
        emoji="📜",
        row=0,
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
            lines.append(f"**Now Playing:** [{current.title}]({current.url}) (`{dur_m:02d}:{dur_s:02d}`)\n")
        if queue:
            lines.append(f"**Up Next ({len(queue)} tracks):**")
            for i, t in enumerate(queue[:10], 1):
                dm = t.duration // 60
                ds = t.duration % 60
                lines.append(f"`{i}.` [{t.title}]({t.url}) - `{dm:02d}:{ds:02d}`")
            if len(queue) > 10:
                lines.append(f"-# ...and {len(queue) - 10} more tracks in queue.")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @discord.ui.button(
        label="Stop",
        style=discord.ButtonStyle.danger,
        custom_id="music:stop",
        emoji="⏹️",
        row=0,
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

    # Row 1: Extended Controls (Loop, Autoplay, Shuffle)
    @discord.ui.button(
        label="Loop",
        style=discord.ButtonStyle.secondary,
        custom_id="music:loop",
        emoji="🔁",
        row=1,
    )
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        current = self.controller.get_loop(self.guild_id)
        next_mode = "track" if current == "off" else ("queue" if current == "track" else "off")
        self.controller.set_loop(self.guild_id, next_mode)
        await interaction.response.send_message(f"🔁 Loop mode set to **{next_mode.upper()}**.", ephemeral=True)

    @discord.ui.button(
        label="Autoplay",
        style=discord.ButtonStyle.secondary,
        custom_id="music:autoplay",
        emoji="♾️",
        row=1,
    )
    async def autoplay_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        current = self.controller.get_autoplay(self.guild_id)
        new_state = not current
        self.controller.set_autoplay(self.guild_id, new_state)
        state_str = "ENABLED (AI Smart Radio)" if new_state else "DISABLED"
        await interaction.response.send_message(f"♾️ AI Autoplay is now **{state_str}**.", ephemeral=True)

    @discord.ui.button(
        label="Shuffle",
        style=discord.ButtonStyle.secondary,
        custom_id="music:shuffle",
        emoji="🔀",
        row=1,
    )
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        queue = self.controller.get_queue(self.guild_id)
        if len(queue) < 2:
            await interaction.response.send_message("Need at least 2 tracks in queue to shuffle.", ephemeral=True)
            return

        random.shuffle(queue)
        await interaction.response.send_message(f"🔀 Shuffled **{len(queue)}** upcoming tracks.", ephemeral=True)
