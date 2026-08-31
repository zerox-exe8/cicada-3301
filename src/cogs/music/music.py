"""
Cicada 3301 Discord Bot - Music Cog Entrypoint
Clean modular architecture connecting all command handlers to the central controller.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from discord.ext import commands

from src.cogs.music._controller import MusicController
from src.cogs.music._commands.play import handle_play
from src.cogs.music._commands.pause import handle_pause, handle_resume
from src.cogs.music._commands.skip import handle_skip
from src.cogs.music._commands.stop import handle_stop
from src.cogs.music._commands.queue import handle_queue
from src.cogs.music._commands.nowplaying import handle_nowplaying
from src.core.context import CustomContext

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("cicada.music")


class Music(commands.Cog):
    """Modular Studio-Grade Discord Music Engine."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot
        self.controller = MusicController(bot)

    @commands.hybrid_command(name="play", aliases=["p"], description="Play music with rock-solid unbreakable connection.")
    async def play(self, ctx: CustomContext, *, query: str) -> None:
        """Play exact music tracks in voice channel."""
        await handle_play(ctx, self.controller, query)

    @commands.hybrid_command(name="pause", description="Pause currently playing music.")
    async def pause(self, ctx: CustomContext) -> None:
        """Pause playback."""
        await handle_pause(ctx, self.controller)

    @commands.hybrid_command(name="resume", aliases=["unpause"], description="Resume paused music.")
    async def resume(self, ctx: CustomContext) -> None:
        """Resume playback."""
        await handle_resume(ctx, self.controller)

    @commands.hybrid_command(name="skip", aliases=["s", "next"], description="Skip the current track.")
    async def skip(self, ctx: CustomContext) -> None:
        """Skip currently playing track."""
        await handle_skip(ctx, self.controller)

    @commands.hybrid_command(name="stop", aliases=["disconnect", "dc"], description="Stop playback and leave voice.")
    async def stop(self, ctx: CustomContext) -> None:
        """Stop music, clear queue and leave voice."""
        await handle_stop(ctx, self.controller)

    @commands.hybrid_command(name="queue", aliases=["q"], description="Show song queue.")
    async def queue(self, ctx: CustomContext) -> None:
        """Show current song queue."""
        await handle_queue(ctx, self.controller)

    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="Show currently playing song.")
    async def nowplaying(self, ctx: CustomContext) -> None:
        """Show currently playing song details."""
        await handle_nowplaying(ctx, self.controller)


async def setup(bot: CicadaBot) -> None:
    """Load the Music Cog into Cicada 3301."""
    await bot.add_cog(Music(bot))
