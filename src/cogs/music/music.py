"""
Cicada 3301 Discord Bot - Music Cog
Exposes High-Fidelity Music Commands with 100% Exact Matching, Smart Autoplay, and Components V2 Container Cards.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.music._controller import MusicController
from src.cogs.music._views import MusicControlView
from src.cogs.music._commands.play import handle_play
from src.cogs.music._commands.pause import handle_pause, handle_resume
from src.cogs.music._commands.skip import handle_skip
from src.cogs.music._commands.stop import handle_stop
from src.cogs.music._commands.queue import handle_queue
from src.cogs.music._commands.nowplaying import handle_nowplaying
from src.cogs.music._commands.autoplay import handle_autoplay
from src.cogs.music._commands.controls import (
    handle_loop,
    handle_shuffle,
    handle_clear,
    handle_remove,
    handle_volume,
)

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("Cicada.Music")


class Music(commands.Cog):
    """High-Performance Discord Studio Audio & Music Engine."""
    category: str = "Music"

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot
        self.controller = MusicController(bot)
        # Register persistent view so button interactions respond instantly across all servers
        self.bot.add_view(MusicControlView(bot, self.controller))

    @commands.hybrid_command(
        name="play",
        aliases=["p"],
        description="Play high-fidelity music tracks in your voice channel.",
    )
    @app_commands.describe(query="Song title, artist name, Spotify or YouTube URL")
    async def play(self, ctx: CustomContext, *, query: str) -> None:
        """Play high-fidelity music tracks in your voice channel."""
        await handle_play(ctx, self.controller, query)

    @commands.hybrid_command(
        name="autoplay",
        aliases=["ap"],
        description="Toggle Autoplay to automatically play continuous radio based on your played songs.",
    )
    @app_commands.describe(action="Action: on, off, or toggle")
    async def autoplay(self, ctx: CustomContext, action: Optional[str] = None) -> None:
        """Toggle Autoplay mode and view status."""
        await handle_autoplay(ctx, self.controller, action)

    @commands.hybrid_command(
        name="pause",
        description="Pause the currently playing music stream.",
    )
    async def pause(self, ctx: CustomContext) -> None:
        """Pause playback."""
        await handle_pause(ctx, self.controller)

    @commands.hybrid_command(
        name="resume",
        aliases=["unpause"],
        description="Resume paused music stream.",
    )
    async def resume(self, ctx: CustomContext) -> None:
        """Resume playback."""
        await handle_resume(ctx, self.controller)

    @commands.hybrid_command(
        name="skip",
        aliases=["s", "next"],
        description="Skip the current track to the next song in queue.",
    )
    async def skip(self, ctx: CustomContext) -> None:
        """Skip currently playing track."""
        await handle_skip(ctx, self.controller)

    @commands.hybrid_command(
        name="stop",
        aliases=["disconnect", "dc"],
        description="Stop playback, clear queue, and disconnect from voice.",
    )
    async def stop(self, ctx: CustomContext) -> None:
        """Stop music, clear queue and leave voice."""
        await handle_stop(ctx, self.controller)

    @commands.hybrid_command(
        name="queue",
        aliases=["q"],
        description="Display the upcoming server music playlist.",
    )
    async def queue(self, ctx: CustomContext) -> None:
        """Show current song queue."""
        await handle_queue(ctx, self.controller)

    @commands.hybrid_command(
        name="nowplaying",
        aliases=["np"],
        description="Display the currently playing song with interactive controls.",
    )
    async def nowplaying(self, ctx: CustomContext) -> None:
        """Show currently playing song details."""
        await handle_nowplaying(ctx, self.controller)

    @commands.hybrid_command(
        name="loop",
        description="Toggle loop mode between off, track, and entire queue.",
    )
    @app_commands.describe(mode="Loop mode: off, track, or queue")
    async def loop(self, ctx: CustomContext, mode: str = "track") -> None:
        """Toggle loop mode."""
        await handle_loop(ctx, self.controller, mode)

    @commands.hybrid_command(
        name="shuffle",
        description="Randomize the order of upcoming songs in queue.",
    )
    async def shuffle(self, ctx: CustomContext) -> None:
        """Shuffle queue."""
        await handle_shuffle(ctx, self.controller)

    @commands.hybrid_command(
        name="clear",
        description="Clear all upcoming tracks from the queue.",
    )
    async def clear(self, ctx: CustomContext) -> None:
        """Clear queue."""
        await handle_clear(ctx, self.controller)

    @commands.hybrid_command(
        name="remove",
        description="Remove a specific song from queue by position number.",
    )
    @app_commands.describe(position="Position number in ?queue (e.g. 1, 2, 3)")
    async def remove(self, ctx: CustomContext, position: int) -> None:
        """Remove a track from queue."""
        await handle_remove(ctx, self.controller, position)

    @commands.hybrid_command(
        name="volume",
        aliases=["vol"],
        description="Adjust playback volume (0 to 150 percent).",
    )
    @app_commands.describe(level="Volume level from 0 to 150")
    async def volume(self, ctx: CustomContext, level: int = 100) -> None:
        """Adjust playback volume."""
        await handle_volume(ctx, self.controller, level)

    # ==========================================
    # Global Fallback Music Interaction Router
    # ==========================================

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Fallback router for music component buttons across all card types."""
        if interaction.type != discord.InteractionType.component or not interaction.data:
            return

        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("music:"):
            return

        if interaction.response.is_done():
            return

        guild = interaction.guild
        if not guild:
            return

        # Voice Verification
        if not interaction.user or not isinstance(interaction.user, discord.Member):
            if not interaction.response.is_done():
                await interaction.response.send_message("Invalid user context.", ephemeral=True)
            return

        if not interaction.user.voice or not interaction.user.voice.channel:
            if not interaction.response.is_done():
                await interaction.response.send_message("You must be in a Voice Channel to use music controls.", ephemeral=True)
            return

        vc = guild.voice_client
        if vc and vc.channel != interaction.user.voice.channel:
            if not interaction.response.is_done():
                await interaction.response.send_message("You must be in the same voice channel as the bot.", ephemeral=True)
            return

        action = custom_id.split(":")[-1]
        e_reg = self.bot.custom_emojis

        if action == "pause":
            if not vc or (not vc.is_playing() and not vc.is_paused()):
                if not interaction.response.is_done():
                    await interaction.response.send_message("No active audio stream.", ephemeral=True)
                return
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

        elif action == "skip":
            if not vc or (not vc.is_playing() and not vc.is_paused()):
                if not interaction.response.is_done():
                    await interaction.response.send_message("No track is currently playing.", ephemeral=True)
                return
            vc.stop()
            skip_icon = e_reg.get("skip", "")
            prefix = f"{skip_icon} " if skip_icon else ""
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{prefix}Skipped track.", ephemeral=True)

        elif action == "vol_down":
            cur_vol = self.controller.get_volume(guild.id)
            new_vol = max(0.0, round(cur_vol - 0.1, 2))
            self.controller.set_volume(guild.id, new_vol)
            if vc and vc.source and hasattr(vc.source, "volume"):
                vc.source.volume = new_vol
            vol_icon = e_reg.get("volume_down", "")
            prefix = f"{vol_icon} " if vol_icon else ""
            pct = int(new_vol * 100)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{prefix}Volume decreased to **{pct}%**.", ephemeral=True)

        elif action == "vol_up":
            cur_vol = self.controller.get_volume(guild.id)
            new_vol = min(1.5, round(cur_vol + 0.1, 2))
            self.controller.set_volume(guild.id, new_vol)
            if vc and vc.source and hasattr(vc.source, "volume"):
                vc.source.volume = new_vol
            vol_icon = e_reg.get("volume_up", "")
            prefix = f"{vol_icon} " if vol_icon else ""
            pct = int(new_vol * 100)
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{prefix}Volume increased to **{pct}%**.", ephemeral=True)

        elif action == "stop":
            if not vc:
                if not interaction.response.is_done():
                    await interaction.response.send_message("I am not connected to a voice channel.", ephemeral=True)
                return
            self.controller.clear_guild(guild.id)
            await vc.disconnect()
            stop_icon = e_reg.get("icons_stop_button", "")
            prefix = f"{stop_icon} " if stop_icon else ""
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{prefix}Playback stopped and disconnected.", ephemeral=True)


async def setup(bot: CicadaBot) -> None:
    """Load the Music Cog into CicadaBot."""
    await bot.add_cog(Music(bot))
