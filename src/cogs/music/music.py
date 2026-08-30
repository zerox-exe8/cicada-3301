"""
Cicada 3301 Discord Bot - High Performance Music Cog (Lavalink v4 / Wavelink 3)
Provides ultra low-latency 320kbps HD audio streaming, multi-node resiliency, and voice playback.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

import discord
from discord import app_commands
from discord.ext import commands
import wavelink

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import CicadaContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("cicada.music")


def format_duration(ms: int) -> str:
    """Format milliseconds into mm:ss or hh:mm:ss."""
    seconds = int(ms / 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class Music(commands.Cog):
    """High-Quality Music System powered by Lavalink v4."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot: CicadaBot = bot
        self._connected: bool = False
        self.bot.loop.create_task(self._connect_nodes())

    async def _connect_nodes(self) -> None:
        """Wait until bot is logged in so bot.user.id is available, then connect Lavalink nodes."""
        await self.bot.wait_until_ready()
        if self._connected:
            return
        self._connected = True

        nodes: list[wavelink.Node] = []
        if Config.LAVALINK_URI:
            nodes.append(
                wavelink.Node(
                    identifier="Private-Dedicated-Node",
                    uri=Config.LAVALINK_URI,
                    password=Config.LAVALINK_PASSWORD,
                    inactive_player_timeout=300,
                )
            )

        # Fallback community nodes
        nodes.extend([
            wavelink.Node(
                identifier="Serenetia-V4-SSL",
                uri="https://lavalinkv4.serenetia.com:443",
                password="https://seretia.link/discord",
                inactive_player_timeout=300,
            ),
            wavelink.Node(
                identifier="Minecuta-V4",
                uri="http://lavav4.minecuta.com:2333",
                password="discord.gg/gKuXdHs",
                inactive_player_timeout=300,
            ),
            wavelink.Node(
                identifier="Millohost-SSL",
                uri="https://lava-v4.millohost.my.id:443",
                password="https://discord.gg/mjS5J2K3ep",
                inactive_player_timeout=300,
            ),
        ])
        try:
            await wavelink.Pool.connect(nodes=nodes, client=self.bot, cache_capacity=100)
            logger.info("Connected to Wavelink Lavalink v4 nodes pool successfully!")
        except Exception as e:
            logger.error(f"Error during Wavelink pool connection: {e}")

    # ─── WAVELINK EVENT LISTENERS ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        """Fired when a Lavalink node finishes handshake."""
        logger.info(f"Lavalink Node [{payload.node.identifier}] is ready! Session: {payload.session_id}")

    @commands.Cog.listener()
    async def on_wavelink_node_closed(self, payload: wavelink.NodeClosedEventPayload) -> None:
        """Fired when a Lavalink node disconnects."""
        logger.warning(f"Lavalink Node [{payload.node.identifier}] closed. Code: {payload.code}")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        """Fired when a track begins playing."""
        player: wavelink.Player | None = payload.player
        if not player or not player.guild:
            return
        track: wavelink.Playable = payload.track
        logger.info(f"Track started in guild {player.guild.name}: {track.title} by {track.author}")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        """Fired when a track finishes. Plays next song in queue automatically."""
        player: wavelink.Player | None = payload.player
        if not player or not player.guild:
            return
        if not player.queue.is_empty:
            try:
                next_track = await player.queue.get_wait()
                await player.play(next_track)
            except Exception as e:
                logger.error(f"Error playing next queued track: {e}")

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload) -> None:
        """Fired when an error occurs during track playback."""
        logger.error(f"Track exception on {payload.player}: {payload.exception}")
        player: wavelink.Player | None = payload.player
        if player and not player.queue.is_empty:
            try:
                next_track = await player.queue.get_wait()
                await player.play(next_track)
            except Exception:
                pass

    # ─── MUSIC PLAY COMMANDS ──────────────────────────────────────────────────

    @commands.hybrid_command(name="play", aliases=["p"], description="Play any song or audio stream in voice channel.")
    @app_commands.describe(query="Song title, artist name, YouTube/Spotify/SoundCloud link")
    async def play(self, ctx: CustomContext, *, query: str) -> None:
        """Join voice channel and stream 320kbps HD audio."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send_error("You must be in a Voice Channel to play music.")
            return

        # Ensure node pool is ready (wait up to 4s if bot just started)
        if not wavelink.Pool.nodes:
            for _ in range(4):
                await asyncio.sleep(1)
                if wavelink.Pool.nodes:
                    break

        user_channel = ctx.author.voice.channel
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)

        if not player:
            try:
                player = await user_channel.connect(cls=wavelink.Player)
            except Exception as e:
                await ctx.send_error(f"Could not connect to voice channel: `{e}`")
                return
        elif player.channel != user_channel:
            if not player.playing:
                await player.move_to(user_channel)
            else:
                await ctx.send_error(f"I am already playing audio in {player.channel.mention}.")
                return

        # Defer if interaction
        if ctx.interaction:
            await ctx.defer()

        # Search track across high-speed sources
        try:
            if query.startswith("http://") or query.startswith("https://"):
                tracks: wavelink.Search = await wavelink.Playable.search(query)
            else:
                tracks = await wavelink.Playable.search(query, source=wavelink.TrackSource.YouTubeMusic)
                if not tracks:
                    tracks = await wavelink.Playable.search(query, source=wavelink.TrackSource.SoundCloud)
                if not tracks:
                    tracks = await wavelink.Playable.search(query, source=wavelink.TrackSource.YouTube)
        except Exception as e:
            await ctx.send_error(f"Failed to fetch audio: `{e}`")
            return

        if not tracks:
            await ctx.send_error(f"No tracks found for `{query}`.")
            return

        arrow = self.bot.custom_emojis.get("icons_rightarrow", "›")

        if isinstance(tracks, wavelink.Playlist):
            # Playlist loaded
            added_count = len(tracks.tracks)
            if not player.playing:
                await player.play(tracks.tracks[0])
                for t in tracks.tracks[1:]:
                    await player.queue.put_wait(t)
            else:
                for t in tracks.tracks:
                    await player.queue.put_wait(t)

            container = CicadaContainer(accent_color=0x5865F2)
            container.add_section(
                content=(
                    f"**Playlist Loaded**\n"
                    f"> **Title:** {tracks.name}\n"
                    f"> **Tracks Added:** `{added_count}` songs\n"
                    f"> **Requested By:** {ctx.author.mention}"
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Streaming in {user_channel.name}")
            await send_container_response(ctx, container)
            return

        track: wavelink.Playable = tracks[0]

        if not player.playing:
            await player.play(track)
            duration_str = format_duration(track.length) if track.length else "Live Stream"

            accessory = None
            if track.artwork:
                accessory = {"type": 11, "media": {"url": track.artwork}}

            container = CicadaContainer(accent_color=0x2ECC71)
            container.add_section(
                content=(
                    f"**Now Playing**\n"
                    f"{arrow} **[{track.title}]({track.uri})**\n"
                    f"> **Artist:** `{track.author}`\n"
                    f"> **Duration:** `{duration_str}`\n"
                    f"> **Requested By:** {ctx.author.mention}"
                ),
                accessory=accessory,
            )
            container.add_separator(divider=True)
            container.add_text(f"-# High-Definition 320kbps Audio {arrow} {user_channel.name}")
            await send_container_response(ctx, container)
        else:
            await player.queue.put_wait(track)
            duration_str = format_duration(track.length) if track.length else "Live Stream"

            container = CicadaContainer(accent_color=0xF39C12)
            container.add_section(
                content=(
                    f"**Added to Queue (Position #{player.queue.count})**\n"
                    f"{arrow} **[{track.title}]({track.uri})**\n"
                    f"> **Artist:** `{track.author}` | **Length:** `{duration_str}`\n"
                    f"> **Requested By:** {ctx.author.mention}"
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Queue size: {player.queue.count} tracks")
            await send_container_response(ctx, container)

    @commands.hybrid_command(name="pause", description="Pause currently playing music.")
    async def pause(self, ctx: CustomContext) -> None:
        """Pause playback."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or not player.playing:
            await ctx.send_error("No audio is currently playing.")
            return

        if player.paused:
            await ctx.send_warning("Music is already paused. Use `?resume` to resume.")
            return

        await player.pause(True)
        await ctx.send_success("Music paused. Use `?resume` to continue.")

    @commands.hybrid_command(name="resume", aliases=["unpause"], description="Resume paused music.")
    async def resume(self, ctx: CustomContext) -> None:
        """Resume playback."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player:
            await ctx.send_error("I am not connected to any voice channel.")
            return

        if not player.paused:
            await ctx.send_warning("Music is not paused.")
            return

        await player.pause(False)
        await ctx.send_success("Music resumed.")

    @commands.hybrid_command(name="skip", aliases=["next", "s"], description="Skip the current track.")
    async def skip(self, ctx: CustomContext) -> None:
        """Skip currently playing track."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or not player.playing:
            await ctx.send_error("No track is currently playing to skip.")
            return

        await player.skip(force=True)
        await ctx.send_success("Skipped to next track.")

    @commands.hybrid_command(name="stop", aliases=["disconnect", "dc", "st"], description="Stop playback and leave voice channel.")
    async def stop(self, ctx: CustomContext) -> None:
        """Stop music, clear queue, and disconnect from voice."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player:
            await ctx.send_error("I am not connected to any voice channel.")
            return

        player.queue.clear()
        await player.disconnect()
        await ctx.send_success("Stopped music and disconnected from voice channel.")

    @commands.hybrid_command(name="volume", aliases=["vol", "v"], description="Adjust player volume (1 - 100).")
    @app_commands.describe(level="Volume level percentage (1 - 100)")
    async def volume(self, ctx: CustomContext, level: int) -> None:
        """Change player audio volume."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or not player.playing:
            await ctx.send_error("No track is currently playing.")
            return

        if not (1 <= level <= 100):
            await ctx.send_error("Volume level must be between `1` and `100`.")
            return

        await player.set_volume(level)
        await ctx.send_success(f"Volume adjusted to **{level}%**.")

    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="Show information about the currently playing track.")
    async def nowplaying(self, ctx: CustomContext) -> None:
        """Display currently playing song info."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or not player.current:
            await ctx.send_error("No track is currently playing.")
            return

        track: wavelink.Playable = player.current
        pos_str = format_duration(int(player.position))
        len_str = format_duration(track.length) if track.length else "Live"
        arrow = self.bot.custom_emojis.get("icons_rightarrow", "›")

        accessory = None
        if track.artwork:
            accessory = {"type": 11, "media": {"url": track.artwork}}

        container = CicadaContainer(accent_color=0x5865F2)
        container.add_section(
            content=(
                f"**Now Playing**\n"
                f"{arrow} **[{track.title}]({track.uri})**\n"
                f"> **Artist:** `{track.author}`\n"
                f"> **Progress:** `{pos_str} / {len_str}`\n"
                f"> **Volume:** `{player.volume}%` | **Status:** `{'Paused' if player.paused else 'Playing'}`"
            ),
            accessory=accessory,
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Streaming in {player.channel.name if player.channel else 'VC'}")
        await send_container_response(ctx, container)

    @commands.hybrid_command(name="queue", aliases=["q"], description="Display the current song queue.")
    async def queue(self, ctx: CustomContext) -> None:
        """Show list of upcoming songs in the queue."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or (not player.current and player.queue.is_empty):
            await ctx.send_error("The queue is currently empty.")
            return

        arrow = self.bot.custom_emojis.get("icons_rightarrow", "›")
        lines = []
        if player.current:
            cur_len = format_duration(player.current.length) if player.current.length else "Live"
            lines.append(f"**Now Playing:**\n{arrow} **[{player.current.title}]({player.current.uri})** (`{cur_len}`)")

        if not player.queue.is_empty:
            lines.append("\n**Up Next:**")
            for i, track in enumerate(list(player.queue)[:10], 1):
                dur = format_duration(track.length) if track.length else "Live"
                lines.append(f"`{i}.` **[{track.title}]({track.uri})** (`{dur}`)")
            if player.queue.count > 10:
                lines.append(f"-# ...and `{player.queue.count - 10}` more songs")

        container = CicadaContainer(accent_color=0x5865F2)
        container.add_section(content="\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Total in Queue: {player.queue.count} tracks")
        await send_container_response(ctx, container)


async def setup(bot: CicadaBot) -> None:
    """Load the Music Cog into Cicada 3301."""
    await bot.add_cog(Music(bot))
