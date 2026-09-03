"""
Kyro Discord Bot - Native Music Cog
High-Fidelity in-process Discord Audio Engine with zero Lavalink dependencies.
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
from src.cogs.music._commands.play import execute_play
from src.cogs.music._commands.pause import execute_pause, execute_resume
from src.cogs.music._commands.skip import execute_skip
from src.cogs.music._commands.stop import execute_stop
from src.cogs.music._commands.queue import execute_queue
from src.cogs.music._commands.nowplaying import execute_nowplaying
from src.cogs.music._commands.autoplay import execute_autoplay
from src.cogs.music._commands.controls import (
    execute_loop,
    execute_shuffle,
    execute_clear,
    execute_volume,
)
from src.cogs.music._commands.playlist import handle_playlist, handle_like, handle_unlike

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Music")


class Music(commands.Cog):
    """High-Performance Native Discord Audio & Studio Music Engine."""
    category: str = "Music"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.controller = MusicController(bot)
        # Register persistent view for button interactions
        self.bot.add_view(MusicControlView(bot, None))

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Auto-disconnect player if everyone leaves the voice channel."""
        if member.id == self.bot.user.id and after.channel is None:
            # Bot was disconnected
            player = self.controller.get_player(member.guild.id)
            if player:
                player.queue.clear()
                player.current = None
                player.voice_client = None
            return

        if before.channel and before.channel.guild:
            guild = before.channel.guild
            player = self.controller.get_player(guild.id)
            if player and player.voice_client and player.voice_client.channel == before.channel:
                # Count non-bot members
                members = [m for m in before.channel.members if not m.bot]
                if len(members) == 0:
                    logger.info(f"Voice channel #{before.channel.name} empty. Stopping player.")
                    await player.stop()

    # ==========================================
    # Prefix & Slash Commands
    # ==========================================

    @commands.hybrid_command(
        name="play",
        aliases=["p"],
        description="Play high-fidelity music tracks directly in your voice channel.",
    )
    @app_commands.describe(query="Song title, artist name, Spotify or YouTube URL")
    async def play(self, ctx: CustomContext, *, query: Optional[str] = None) -> None:
        """Play high-fidelity music tracks in your voice channel."""
        await execute_play(self, ctx, query)

    @commands.hybrid_command(
        name="autoplay",
        aliases=["ap"],
        description="Toggle Smart Autoplay to play continuous radio based on played songs.",
    )
    @app_commands.describe(state="Action: on, off, or toggle")
    async def autoplay(self, ctx: CustomContext, state: Optional[str] = "") -> None:
        """Toggle Autoplay mode."""
        await execute_autoplay(self, ctx, state or "")

    @commands.hybrid_command(
        name="pause",
        description="Pause the currently playing music stream.",
    )
    async def pause(self, ctx: CustomContext) -> None:
        """Pause playback."""
        await execute_pause(self, ctx)

    @commands.hybrid_command(
        name="resume",
        aliases=["unpause"],
        description="Resume paused music stream.",
    )
    async def resume(self, ctx: CustomContext) -> None:
        """Resume playback."""
        await execute_resume(self, ctx)

    @commands.hybrid_command(
        name="skip",
        aliases=["s", "next"],
        description="Skip the current track to the next song in queue.",
    )
    async def skip(self, ctx: CustomContext) -> None:
        """Skip currently playing track."""
        await execute_skip(self, ctx)

    @commands.hybrid_command(
        name="stop",
        aliases=["disconnect", "dc"],
        description="Stop playback, clear queue, and disconnect from voice.",
    )
    async def stop(self, ctx: CustomContext) -> None:
        """Stop music, clear queue and leave voice."""
        await execute_stop(self, ctx)

    @commands.hybrid_command(
        name="queue",
        aliases=["q"],
        description="Display the upcoming server music playlist.",
    )
    @app_commands.describe(page="Queue page number")
    async def queue(self, ctx: CustomContext, page: int = 1) -> None:
        """Show current song queue."""
        await execute_queue(self, ctx, page)

    @commands.hybrid_command(
        name="nowplaying",
        aliases=["now", "playing"],
        description="Display the currently playing song with interactive controls.",
    )
    async def nowplaying(self, ctx: CustomContext) -> None:
        """Show currently playing song details."""
        await execute_nowplaying(self, ctx)

    @commands.hybrid_command(
        name="loop",
        description="Toggle loop mode between off, track, and entire queue.",
    )
    @app_commands.describe(mode="Loop mode: off, track, or queue")
    async def loop(self, ctx: CustomContext, mode: str = "track") -> None:
        """Toggle loop mode."""
        await execute_loop(self, ctx, mode)

    @commands.hybrid_command(
        name="shuffle",
        description="Randomize the order of upcoming songs in queue.",
    )
    async def shuffle(self, ctx: CustomContext) -> None:
        """Shuffle queue."""
        await execute_shuffle(self, ctx)

    @commands.hybrid_command(
        name="clear",
        description="Clear all upcoming tracks from the queue.",
    )
    async def clear(self, ctx: CustomContext) -> None:
        """Clear queue."""
        await execute_clear(self, ctx)

    @commands.hybrid_command(
        name="volume",
        aliases=["vol"],
        description="Adjust playback volume (0 to 200 percent).",
    )
    @app_commands.describe(volume="Volume percentage from 0 to 200")
    async def volume(self, ctx: CustomContext, volume: int = 100) -> None:
        """Adjust playback volume."""
        await execute_volume(self, ctx, volume)

    @commands.hybrid_command(
        name="like",
        aliases=["fav", "favorite"],
        description="Save the currently playing song into your personal Favorites playlist.",
    )
    async def like(self, ctx: CustomContext) -> None:
        """Save current song to Favorites playlist."""
        await handle_like(ctx, self)

    @commands.hybrid_command(
        name="unlike",
        aliases=["unfav", "dislike"],
        description="Remove a song from your personal Favorites playlist by title or playing track.",
    )
    @app_commands.describe(query="Optional song title or track number to remove from Favorites")
    async def unlike(self, ctx: CustomContext, *, query: Optional[str] = None) -> None:
        """Remove a song from Favorites playlist."""
        await handle_unlike(ctx, self, query=query)

    @commands.hybrid_command(
        name="playlist",
        aliases=["pl"],
        description="Manage, play, view, and save custom song playlists.",
    )
    @app_commands.describe(
        action="Action: add, play, list, view, delete",
        name="Playlist name",
        query="Optional song title or URL (if adding a specific song)",
    )
    async def playlist(
        self,
        ctx: CustomContext,
        action: Optional[str] = None,
        name: Optional[str] = None,
        *,
        query: Optional[str] = None,
    ) -> None:
        """Manage custom user playlists."""
        await handle_playlist(ctx, self, action, name, query=query)


async def setup(bot: KyroBot) -> None:
    """Load the Music Cog into KyroBot."""
    await bot.add_cog(Music(bot))
