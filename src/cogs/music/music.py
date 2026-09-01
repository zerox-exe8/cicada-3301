"""
Kyro Discord Bot - Music Cog
Exposes High-Fidelity Music Commands powered by dedicated Lavalink V4 with Zero-Lag Streaming.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands
import wavelink

from src.core.context import CustomContext
from src.cogs.music._player import KyroPlayer
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
from src.cogs.music._commands.playlist import handle_playlist, handle_like

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Music")


class Music(commands.Cog):
    """High-Performance Discord Studio Audio & Music Engine (Lavalink V4)."""
    category: str = "Music"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.controller = MusicController(bot)
        # Register persistent view so button interactions respond instantly across all servers
        self.bot.add_view(MusicControlView(bot, None))

    # ==========================================
    # Wavelink V3 Event Listeners
    # ==========================================

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        """Fired when Lavalink V4 node is connected and ready."""
        logger.info(f"Lavalink V4 Node '{payload.node.identifier}' is ready and connected! Resumed: {payload.resumed}")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        """Fired when any track begins playback across any server."""
        player: KyroPlayer = payload.player  # type: ignore
        if not player or not payload.track:
            return

        logger.info(f"Started playback: '{payload.track.title}' in guild {player.guild.id}")

        # Update session memory and pre-fetch next recommendation in background
        player.record_track_start(payload.track)

        # Send/Update Now Playing card in the active command channel
        if player.home_channel:
            await player.update_now_playing(payload.track)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        """Fired when a track finishes playback."""
        player: KyroPlayer = payload.player  # type: ignore
        if not player:
            return

        # CRITICAL ANTI-CASCADE GUARD:
        # Ignore 'replaced', 'stopped', 'cleanup', 'loadFailed' to prevent rapid-fire skip loops!
        if payload.reason != "finished":
            logger.debug(f"Ignoring track end event with reason='{payload.reason}'")
            return

        # If queue has tracks, Wavelink's AutoPlayMode.partial automatically advances player.queue smoothly.
        if not player.queue.is_empty:
            return

        # If queue is completely empty AND Smart Autoplay is enabled, seamlessly transition to next curated track
        if player.smart_autoplay:
            next_track = player.prefetched_autoplay_track
            player.prefetched_autoplay_track = None

            if not next_track:
                from src.cogs.music._autoplay import SmartAutoplayEngine
                next_track = await SmartAutoplayEngine.get_next_track(
                    current_track=payload.track,
                    played_history=player.played_history,
                    consecutive_same_artist=player.consecutive_same_artist,
                )

            if next_track:
                logger.info(f"Smart Autoplay seamlessly playing next track: '{next_track.title}'")
                await player.play(next_track)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload) -> None:
        """Fired when a track fails to decode or stream from source (e.g. YouTube 403 block)."""
        player: KyroPlayer = payload.player  # type: ignore
        if not player or not payload.track:
            return

        logger.warning(f"Track exception for '{payload.track.title}' in guild {player.guild.id}: {payload.exception}")

        # Intelligent Auto-Recovery: Try resolving and playing via unblocked Deezer/SoundCloud stream
        try:
            from src.cogs.music._resolver import MusicResolver, clean_track_title
            clean_t = clean_track_title(payload.track.title or "")
            clean_a = payload.track.author or ""
            fallback_query = f"{clean_t} {clean_a}".strip()

            recovered = await MusicResolver.resolve(fallback_query)
            if recovered:
                rec_track = recovered[0] if isinstance(recovered, list) else (
                    recovered.tracks[0] if isinstance(recovered, wavelink.Playlist) else recovered
                )
                if rec_track and rec_track.uri != payload.track.uri:
                    logger.info(f"Auto-Recovered stream for '{payload.track.title}' via {rec_track.source}: '{rec_track.title}'")
                    await player.play(rec_track)
                    return
        except Exception as ex:
            logger.debug(f"Auto-recovery notice: {ex}")

        # If recovery also failed, skip cleanly
        if player:
            await player.skip(force=True)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: KyroPlayer) -> None:
        """Fired when a player has been inactive in voice channel."""
        logger.info(f"Disconnecting inactive player in guild {player.guild.id}")
        try:
            if player.home_channel:
                await player.home_channel.send("-# Disconnected due to inactivity in voice channel.")
            player.queue.clear()
            await player.disconnect()
        except Exception as e:
            logger.debug(f"Inactive player disconnect notice: {e}")

    # ==========================================
    # Commands
    # ==========================================

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
        description="View current volume or adjust playback volume (0 to 100 percent).",
    )
    @app_commands.describe(level="Optional volume level from 0 to 100")
    async def volume(self, ctx: CustomContext, level: Optional[int] = None) -> None:
        """View or adjust playback volume."""
        await handle_volume(ctx, self.controller, level)

    @commands.hybrid_command(
        name="like",
        aliases=["fav", "favorite"],
        description="Save the currently playing song into your personal Favorites playlist.",
    )
    async def like(self, ctx: CustomContext) -> None:
        """Save current song to Favorites playlist."""
        await handle_like(ctx, self.controller)

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
        await handle_playlist(ctx, self.controller, action, name, query=query)


async def setup(bot: KyroBot) -> None:
    """Load the Music Cog into KyroBot."""
    await bot.add_cog(Music(bot))
