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

        # Apply custom application emojis from assets/
        e_reg = bot.custom_emojis
        pause_em = e_reg.get_emoji_obj("paused")
        skip_em = e_reg.get_emoji_obj("skip")
        queue_em = e_reg.get_emoji_obj("queue")
        stop_em = e_reg.get_emoji_obj("icons_stop_button")
        loop_em = e_reg.get_emoji_obj("icons_loop")
        shuffle_em = e_reg.get_emoji_obj("icons_shuffle")
        autoplay_em = e_reg.get_emoji_obj("icons_loop") or e_reg.get_emoji_obj("music_playing")

        if pause_em:
            self.pause_button.emoji = pause_em
        if skip_em:
            self.skip_button.emoji = skip_em
        if queue_em:
            self.queue_button.emoji = queue_em
        if stop_em:
            self.stop_button.emoji = stop_em
        if loop_em:
            self.loop_button.emoji = loop_em
        if shuffle_em:
            self.shuffle_button.emoji = shuffle_em
        if autoplay_em:
            self.autoplay_button.emoji = autoplay_em

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
        e_reg = self.bot.custom_emojis
        if vc.is_playing():
            vc.pause()
            button.label = "Resume"
            resume_em = e_reg.get_emoji_obj("music_playing")
            if resume_em:
                button.emoji = resume_em
            pause_icon = e_reg.get("paused", "")
            prefix = f"{pause_icon} " if pause_icon else ""
            await interaction.response.send_message(f"{prefix}Playback paused.", ephemeral=True)
        elif vc.is_paused():
            vc.resume()
            button.label = "Pause"
            pause_em = e_reg.get_emoji_obj("paused")
            if pause_em:
                button.emoji = pause_em
            play_icon = e_reg.get("music_playing", "")
            prefix = f"{play_icon} " if play_icon else ""
            await interaction.response.send_message(f"{prefix}Playback resumed.", ephemeral=True)
        else:
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
        if not guild or not guild.voice_client or not guild.voice_client.is_playing():
            await interaction.response.send_message("No track is currently playing.", ephemeral=True)
            return

        guild.voice_client.stop()
        e_reg = self.bot.custom_emojis
        skip_icon = e_reg.get("skip", "")
        prefix = f"{skip_icon} " if skip_icon else ""
        await interaction.response.send_message(f"{prefix}Skipped track.", ephemeral=True)

    @discord.ui.button(
        label="Queue",
        style=discord.ButtonStyle.secondary,
        custom_id="music:queue",
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
        e_reg = self.bot.custom_emojis
        stop_icon = e_reg.get("icons_stop_button", "")
        prefix = f"{stop_icon} " if stop_icon else ""
        await interaction.response.send_message(f"{prefix}Playback stopped and disconnected.", ephemeral=True)

    # Row 1: Extended Controls (Loop, Autoplay, Shuffle)
    @discord.ui.button(
        label="Loop",
        style=discord.ButtonStyle.secondary,
        custom_id="music:loop",
        row=1,
    )
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        current = self.controller.get_loop(self.guild_id)
        next_mode = "track" if current == "off" else ("queue" if current == "track" else "off")
        self.controller.set_loop(self.guild_id, next_mode)
        e_reg = self.bot.custom_emojis
        loop_icon = e_reg.get("icons_loop", "")
        prefix = f"{loop_icon} " if loop_icon else ""
        await interaction.response.send_message(f"{prefix}Loop mode set to **{next_mode.upper()}**.", ephemeral=True)

    @discord.ui.button(
        label="Autoplay",
        style=discord.ButtonStyle.secondary,
        custom_id="music:autoplay",
        row=1,
    )
    async def autoplay_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not await self._check_user_voice(interaction):
            return

        current = self.controller.get_autoplay(self.guild_id)
        new_state = not current
        self.controller.set_autoplay(self.guild_id, new_state)
        state_str = "ENABLED (AI Smart Radio)" if new_state else "DISABLED"
        e_reg = self.bot.custom_emojis
        ap_icon = e_reg.get("icons_loop", e_reg.get("music_playing", ""))
        prefix = f"{ap_icon} " if ap_icon else ""
        await interaction.response.send_message(f"{prefix}AI Autoplay is now **{state_str}**.", ephemeral=True)

    @discord.ui.button(
        label="Shuffle",
        style=discord.ButtonStyle.secondary,
        custom_id="music:shuffle",
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
        e_reg = self.bot.custom_emojis
        shuf_icon = e_reg.get("icons_shuffle", "")
        prefix = f"{shuf_icon} " if shuf_icon else ""
        await interaction.response.send_message(f"{prefix}Shuffled **{len(queue)}** upcoming tracks.", ephemeral=True)
