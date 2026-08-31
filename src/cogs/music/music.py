"""
Cicada 3301 Discord Bot - Music Cog
Exposes High-Fidelity Music Commands with 100% Exact Matching, AI Autoplay, and Components V2 Container Cards.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.music._controller import MusicController
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
        description="Toggle AI Autoplay to automatically play continuous radio matching user tastes.",
    )
    @app_commands.describe(action="Action: on, off, status, or toggle")
    async def autoplay(self, ctx: CustomContext, action: Optional[str] = None) -> None:
        """Toggle AI Autoplay and view listener taste profile."""
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
    # Background Music Intelligence Listeners
    # ==========================================

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        """Detect Spotify Rich Presence changes to build user music profile."""
        if after.bot:
            return
        for act in after.activities:
            if isinstance(act, discord.Spotify):
                await self.controller.analytics.ingest_spotify_presence(after, act)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Analyze song plays triggered across other bots in the server."""
        if message.author.bot or not message.guild:
            return
        await self.controller.analytics.ingest_message_activity(message)


async def setup(bot: CicadaBot) -> None:
    """Load the Music Cog into CicadaBot."""
    await bot.add_cog(Music(bot))
