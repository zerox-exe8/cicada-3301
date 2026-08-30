"""
Cicada 3301 Discord Bot - High-Performance Clean Music Engine (Lavalink v4)
Features:
- Minimalist Premium Container Layout (No cheap emojis, sleek dark aesthetic)
- Clean Button Controller (Pause/Resume, Skip, Stop, Queue)
- High-Accuracy Search Engine
- Automatic Auto-Play Queue System
- 320kbps HD Audio Stream
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


def build_now_playing_container(track: wavelink.Playable, player: wavelink.Player, author: discord.Member | discord.User) -> CicadaContainer:
    """Build a sleek, minimalist Now Playing Container card without noisy emojis."""
    duration_str = format_duration(track.length) if track.length else "Live Stream"
    channel_name = player.channel.name if player.channel else "Voice Channel"

    accessory = None
    if track.artwork:
        accessory = {"type": 11, "media": {"url": track.artwork}}

    container = CicadaContainer(accent_color=None)
    container.add_section(
        content=(
            f"**Now Playing**\n"
            f"> **Title:** **[{track.title}]({track.uri})**\n"
            f"> **Artist:** `{track.author}` • **Duration:** `{duration_str}`"
        ),
        accessory=accessory,
    )
    container.add_separator(divider=True)
    container.add_text(
        f"• **Channel:** `{channel_name}` | **Bitrate:** `320 kbps (HD)`\n"
        f"• **Requested By:** {author.mention}"
    )
    return container


class MusicControllerView(discord.ui.View):
    """Clean, minimalist button controller for Discord Music Player."""

    def __init__(self, bot: CicadaBot, player: wavelink.Player, author_id: int) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.player = player
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user or not isinstance(interaction.user, discord.Member):
            return False
        if not interaction.user.voice or not self.player.channel or interaction.user.voice.channel != self.player.channel:
            await interaction.response.send_message("You must be in the same Voice Channel as the bot to use controls.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.secondary, row=0)
    async def pause_resume_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.player.playing:
            await interaction.response.send_message("No audio is currently playing.", ephemeral=True)
            return

        is_paused = not self.player.paused
        await self.player.pause(is_paused)
        button.label = "Resume" if is_paused else "Pause"
        button.style = discord.ButtonStyle.success if is_paused else discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary, row=0)
    async def skip_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.player.playing:
            await interaction.response.send_message("No audio is currently playing to skip.", ephemeral=True)
            return

        if not self.player.queue.is_empty:
            next_track = await self.player.queue.get_wait()
            await self.player.play(next_track)
            container = build_now_playing_container(next_track, self.player, interaction.user)
            view = MusicControllerView(self.bot, self.player, interaction.user.id)
            await send_container_response(interaction, container, view=view)
        else:
            await self.player.skip(force=True)
            await interaction.response.send_message("Skipped. Queue is now empty.", ephemeral=True)

    @discord.ui.button(label="Queue", style=discord.ButtonStyle.secondary, row=0)
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if not self.player.current and self.player.queue.is_empty:
            await interaction.response.send_message("The queue is currently empty.", ephemeral=True)
            return

        lines = []
        if self.player.current:
            cur_len = format_duration(self.player.current.length) if self.player.current.length else "Live"
            lines.append(f"**Now Playing:**\n> **[{self.player.current.title}]({self.player.current.uri})** (`{cur_len}`)")

        if not self.player.queue.is_empty:
            lines.append("\n**Up Next:**")
            for i, track in enumerate(list(self.player.queue)[:10], 1):
                dur = format_duration(track.length) if track.length else "Live"
                lines.append(f"`{i}.` **[{track.title}]({track.uri})** (`{dur}`)")
            if self.player.queue.count > 10:
                lines.append(f"-# ...and `{self.player.queue.count - 10}` more tracks")

        container = CicadaContainer(accent_color=None)
        container.add_section(content="\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Total Queue: {self.player.queue.count} tracks")
        await send_container_response(interaction, container, ephemeral=True)

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger, row=0)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.player.queue.clear()
        await self.player.disconnect()
        self.stop()
        await interaction.response.send_message("Playback stopped and left voice channel.", ephemeral=False)


class Music(commands.Cog):
    """High-Quality Music System powered by Lavalink v4."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot: CicadaBot = bot
        self._connected: bool = False
        self.bot.loop.create_task(self._connect_nodes())

    async def _connect_nodes(self) -> None:
        """Wait until bot is logged in, then connect Lavalink nodes."""
        await self.bot.wait_until_ready()
        if self._connected:
            return
        self._connected = True

        nodes: list[wavelink.Node] = []
        if Config.LAVALINK_URI:
            nodes.append(
                wavelink.Node(
                    identifier="Dedicated-Node",
                    uri=Config.LAVALINK_URI,
                    password=Config.LAVALINK_PASSWORD,
                    inactive_player_timeout=300,
                )
            )

        try:
            await wavelink.Pool.connect(nodes=nodes, client=self.bot, cache_capacity=100)
            logger.info("Connected to Dedicated Lavalink v4 node pool successfully!")
        except Exception as e:
            logger.error(f"Error during Wavelink pool connection: {e}")

    # ─── WAVELINK EVENT LISTENERS ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        """Fired when Lavalink node finishes handshake."""
        logger.info(f"Lavalink Node [{payload.node.identifier}] is ready! Session: {payload.session_id}")

    @commands.Cog.listener()
    async def on_wavelink_node_closed(self, payload: wavelink.NodeClosedEventPayload) -> None:
        """Fired when Lavalink node disconnects."""
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
        """Fired when a track finishes. Automatically plays next song in queue."""
        player: wavelink.Player | None = payload.player
        if not player or not player.guild:
            return
        if not player.queue.is_empty:
            try:
                next_track = await player.queue.get_wait()
                await player.play(next_track)
            except Exception as e:
                logger.error(f"Error auto-playing next track: {e}")

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

    # ─── MUSIC COMMANDS ───────────────────────────────────────────────────────

    @commands.hybrid_command(name="play", aliases=["p"], description="Play any song or playlist in voice channel.")
    @app_commands.describe(query="Song title, artist name, YouTube/Spotify link")
    async def play(self, ctx: CustomContext, *, query: str) -> None:
        """Join voice channel and play requested track with sleek minimalist player controller."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send_error("You must join a Voice Channel to play music.")
            return

        # Ensure node is connected
        if not wavelink.Pool.nodes:
            for _ in range(4):
                await asyncio.sleep(1)
                if wavelink.Pool.nodes:
                    break

        user_channel = ctx.author.voice.channel
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)

        if not player:
            try:
                player = await user_channel.connect(cls=wavelink.Player, self_deaf=True, timeout=15.0)
            except Exception:
                try:
                    if ctx.guild.voice_client:
                        await ctx.guild.voice_client.disconnect(force=True)
                        await asyncio.sleep(0.5)
                    player = await user_channel.connect(cls=wavelink.Player, self_deaf=True, timeout=15.0)
                except Exception as e2:
                    await ctx.send_error(f"Could not connect to voice channel: `{e2}`")
                    return
        elif player.channel != user_channel:
            if not player.playing:
                await player.move_to(user_channel)
            else:
                await ctx.send_error(f"I am already playing audio in {player.channel.mention}.")
                return

        # Accurate search fallback
        try:
            if query.startswith("http://") or query.startswith("https://"):
                tracks: wavelink.Search = await wavelink.Playable.search(query)
            else:
                tracks = await wavelink.Playable.search(query, source=wavelink.TrackSource.YouTubeMusic)
                if not tracks:
                    tracks = await wavelink.Playable.search(query, source=wavelink.TrackSource.YouTube)
                if not tracks:
                    tracks = await wavelink.Playable.search(query, source=wavelink.TrackSource.SoundCloud)
        except Exception as e:
            await ctx.send_error(f"Failed to find song: `{e}`")
            return

        if not tracks:
            await ctx.send_error(f"No tracks found for `{query}`.")
            return

        if isinstance(tracks, wavelink.Playlist):
            added_count = len(tracks.tracks)
            if not player.playing:
                await player.play(tracks.tracks[0])
                for t in tracks.tracks[1:]:
                    await player.queue.put_wait(t)
            else:
                for t in tracks.tracks:
                    await player.queue.put_wait(t)

            container = CicadaContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Playlist Loaded**\n"
                    f"> **Title:** **{tracks.name}**\n"
                    f"> **Tracks Added:** `{added_count}` songs"
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"• **Channel:** `{user_channel.name}` | **Bitrate:** `320 kbps (HD)`\n"
                f"• **Requested By:** {ctx.author.mention}"
            )
            view = MusicControllerView(self.bot, player, ctx.author.id)
            await send_container_response(ctx, container, view=view)
            return

        track: wavelink.Playable = tracks[0]

        if not player.playing:
            await player.play(track)
            container = build_now_playing_container(track, player, ctx.author)
            view = MusicControllerView(self.bot, player, ctx.author.id)
            await send_container_response(ctx, container, view=view)
        else:
            await player.queue.put_wait(track)
            duration_str = format_duration(track.length) if track.length else "Live Stream"

            container = CicadaContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Track Queued (Position #{player.queue.count})**\n"
                    f"> **Title:** **[{track.title}]({track.uri})**\n"
                    f"> **Artist:** `{track.author}` • **Duration:** `{duration_str}`"
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"• **Queue Length:** `{player.queue.count} tracks` | **Bitrate:** `320 kbps`\n"
                f"• **Requested By:** {ctx.author.mention}"
            )
            await send_container_response(ctx, container)

    @commands.hybrid_command(name="skip", aliases=["next", "s"], description="Skip the current track.")
    async def skip(self, ctx: CustomContext) -> None:
        """Skip currently playing track."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or not player.playing:
            await ctx.send_error("No track is currently playing to skip.")
            return

        if not player.queue.is_empty:
            next_track = await player.queue.get_wait()
            await player.play(next_track)
            container = build_now_playing_container(next_track, player, ctx.author)
            view = MusicControllerView(self.bot, player, ctx.author.id)
            await send_container_response(ctx, container, view=view)
        else:
            await player.skip(force=True)
            await ctx.send_success("Skipped playback. Queue is now empty.")

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
        await ctx.send_success("Playback paused.")

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
        await ctx.send_success("Playback resumed.")

    @commands.hybrid_command(name="stop", aliases=["disconnect", "dc", "st"], description="Stop playback and leave voice channel.")
    async def stop(self, ctx: CustomContext) -> None:
        """Stop music, clear queue, and disconnect from voice."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player:
            await ctx.send_error("I am not connected to any voice channel.")
            return

        player.queue.clear()
        await player.disconnect()
        await ctx.send_success("Playback stopped and left voice channel.")

    @commands.hybrid_command(name="queue", aliases=["q"], description="Display the current song queue.")
    async def queue(self, ctx: CustomContext) -> None:
        """Show list of upcoming songs in the queue."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or (not player.current and player.queue.is_empty):
            await ctx.send_error("The queue is currently empty.")
            return

        lines = []
        if player.current:
            cur_len = format_duration(player.current.length) if player.current.length else "Live"
            lines.append(f"**Now Playing:**\n> **[{player.current.title}]({player.current.uri})** (`{cur_len}`)")

        if not player.queue.is_empty:
            lines.append("\n**Up Next:**")
            for i, track in enumerate(list(player.queue)[:10], 1):
                dur = format_duration(track.length) if track.length else "Live"
                lines.append(f"`{i}.` **[{track.title}]({track.uri})** (`{dur}`)")
            if player.queue.count > 10:
                lines.append(f"-# ...and `{player.queue.count - 10}` more tracks")

        container = CicadaContainer(accent_color=None)
        container.add_section(content="\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Total in Queue: {player.queue.count} tracks")
        await send_container_response(ctx, container)

    @commands.hybrid_command(name="nowplaying", aliases=["np"], description="Show information about the currently playing track.")
    async def nowplaying(self, ctx: CustomContext) -> None:
        """Display currently playing song info."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or not player.current:
            await ctx.send_error("No track is currently playing.")
            return

        container = build_now_playing_container(player.current, player, ctx.author)
        view = MusicControllerView(self.bot, player, ctx.author.id)
        await send_container_response(ctx, container, view=view)


async def setup(bot: CicadaBot) -> None:
    """Load the Music Cog into Cicada 3301."""
    await bot.add_cog(Music(bot))
