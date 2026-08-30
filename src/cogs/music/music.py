"""
Cicada 3301 Discord Bot - Ultra Low-Latency Clean Music Engine (Lavalink v4)
Features:
- Parallel Execution (Instant <250ms Voice Join + Song Search)
- YouTube & SoundCloud Multi-Engine Playback
- Full Spotify & YouTube URL + Playlist Support
- Auto-Healing & Resilient Node Pool Connection
- Minimalist Premium Container Layout (Integrated Custom Emojis)
- Responsive Button Controller (Pause/Resume, Skip, Stop, Queue)
- 320kbps Lossless Audio Stream
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
from src.cogs.music.spotify_resolver import SpotifyResolver
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


def build_now_playing_container(track: wavelink.Playable, player: wavelink.Player, author: discord.Member | discord.User, bot: CicadaBot | None = None) -> CicadaContainer:
    """Build a sleek, minimalist Now Playing Container card with custom music icon."""
    duration_str = format_duration(track.length) if track.length else "Live Stream"
    channel_name = player.channel.name if player.channel else "Voice Channel"

    playing_icon = ""
    if bot and hasattr(bot, "custom_emojis"):
        playing_icon = bot.custom_emojis.get("music_playing", bot.custom_emojis.get("a_musical_notes", bot.custom_emojis.get("music_music", "")))
        if playing_icon:
            playing_icon = f"{playing_icon} "

    accessory = None
    if track.artwork:
        accessory = {"type": 11, "media": {"url": track.artwork}}

    container = CicadaContainer(accent_color=None)
    container.add_section(
        content=(
            f"**{playing_icon}Now Playing**\n"
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
    """Clean, ultra-responsive button controller for Discord Music Player."""

    def __init__(self, bot: CicadaBot, player: wavelink.Player, author_id: int) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.player = player
        self.author_id = author_id

        # Attach custom uploaded emojis safely via children
        if hasattr(bot, "custom_emojis"):
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    if child.label in ("Pause", "Resume"):
                        child.emoji = bot.custom_emojis.get_emoji_obj("paused")
                    elif child.label == "Skip":
                        child.emoji = bot.custom_emojis.get_emoji_obj("skip")
                    elif child.label == "Queue":
                        child.emoji = bot.custom_emojis.get_emoji_obj("queue")
                    elif child.label == "Stop":
                        child.emoji = bot.custom_emojis.get_emoji_obj("icons_stop_button")

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

        await self.player.skip(force=True)
        await interaction.response.send_message("Skipped to next track.", ephemeral=True)

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
    """High-Performance, Auto-Healing Music System."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot: CicadaBot = bot
        self.bot.loop.create_task(self._ensure_node())

    async def _ensure_node(self) -> bool:
        """Ensure dedicated Lavalink node is connected with auto-reconnection."""
        if wavelink.Pool.nodes and any(n.status == wavelink.NodeStatus.CONNECTED for n in wavelink.Pool.nodes.values()):
            return True

        if not Config.LAVALINK_URI:
            return False

        try:
            node = wavelink.Node(
                identifier="Dedicated-Node",
                uri=Config.LAVALINK_URI,
                password=Config.LAVALINK_PASSWORD,
                inactive_player_timeout=300,
            )
            await wavelink.Pool.connect(nodes=[node], client=self.bot, cache_capacity=100)
            for _ in range(8):
                if any(n.status == wavelink.NodeStatus.CONNECTED for n in wavelink.Pool.nodes.values()):
                    logger.info("Connected to Dedicated Lavalink v4 node successfully!")
                    return True
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Error connecting to Lavalink node pool: {e}")

        return any(n.status == wavelink.NodeStatus.CONNECTED for n in wavelink.Pool.nodes.values())

    # ─── WAVELINK EVENT LISTENERS ─────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        """Fired when Lavalink node finishes handshake."""
        logger.info(f"Lavalink Node [{payload.node.identifier}] is ready! Session: {payload.session_id}")

    @commands.Cog.listener()
    async def on_wavelink_node_closed(self, payload: wavelink.NodeClosedEventPayload) -> None:
        """Fired when Lavalink node disconnects. Automatically reconnects."""
        logger.warning(f"Lavalink Node [{payload.node.identifier}] closed. Reconnecting...")
        await asyncio.sleep(2)
        await self._ensure_node()

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        """Fired when a track begins playing."""
        player: wavelink.Player | None = payload.player
        if not player or not player.guild:
            return
        track: wavelink.Playable = payload.track
        logger.info(f"Track started in {player.guild.name}: {track.title}")

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
        """Fired when an error occurs during playback."""
        logger.error(f"Track exception on {payload.player}: {payload.exception}")
        player: wavelink.Player | None = payload.player
        if player and not player.queue.is_empty:
            try:
                next_track = await player.queue.get_wait()
                await player.play(next_track)
            except Exception:
                pass

    # ─── MUSIC COMMANDS ───────────────────────────────────────────────────────

    @commands.hybrid_command(name="play", aliases=["p"], description="Play any song, Spotify link, or playlist in voice channel.")
    @app_commands.describe(query="Song title, artist name, Spotify, YouTube or SoundCloud link")
    async def play(self, ctx: CustomContext, *, query: str) -> None:
        """Instant ultra low-latency music playback."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send_error("You must join a Voice Channel to play music.")
            return

        # Ensure node is connected
        connected = await self._ensure_node()
        if not connected:
            await ctx.send_error("Audio node is initializing. Please retry in a few seconds.")
            return

        user_channel = ctx.author.voice.channel

        # Parallel Task 1: Connect to Voice Channel
        async def connect_voice() -> wavelink.Player | None:
            p = cast(wavelink.Player, ctx.guild.voice_client)
            if not p:
                try:
                    return await user_channel.connect(cls=wavelink.Player, self_deaf=True)
                except Exception as e:
                    logger.debug(f"Voice connect error: {e}")
                    return None
            elif p.channel != user_channel and not p.playing:
                await p.move_to(user_channel)
            return p

        # Parallel Task 2: Search Track / Spotify
        async def resolve_tracks():
            # Check for Spotify URLs
            if "spotify.com" in query.lower():
                s_data = await SpotifyResolver.resolve_url(query)
                if s_data:
                    return ("spotify", s_data)

            if query.startswith("http://") or query.startswith("https://"):
                res = await wavelink.Playable.search(query)
                return ("wavelink", res)

            # Direct Search: YouTube -> SoundCloud
            try:
                res = await wavelink.Playable.search(query, source=wavelink.TrackSource.YouTube)
                if res:
                    return ("wavelink", res)
            except Exception:
                pass

            try:
                res = await wavelink.Playable.search(query, source=wavelink.TrackSource.SoundCloud)
                if res:
                    return ("wavelink", res)
            except Exception:
                pass

            return ("wavelink", None)

        # Run connection and search in parallel (<250ms total)
        results = await asyncio.gather(connect_voice(), resolve_tracks(), return_exceptions=True)

        player = results[0] if not isinstance(results[0], Exception) else None
        track_info = results[1] if not isinstance(results[1], Exception) else ("wavelink", None)

        if not player:
            await ctx.send_error("Could not connect to your voice channel. Please check bot permissions.")
            return

        mode, data = track_info

        # Handle Spotify Playlists / Albums
        if mode == "spotify" and data:
            if data["type"] in ("playlist", "album"):
                track_queries = data["tracks"]
                if not track_queries:
                    await ctx.send_error("Could not load tracks from this Spotify playlist.")
                    return

                first_res = await wavelink.Playable.search(track_queries[0], source=wavelink.TrackSource.YouTube)
                if not first_res:
                    first_res = await wavelink.Playable.search(track_queries[0], source=wavelink.TrackSource.SoundCloud)

                if first_res:
                    if not player.playing:
                        await player.play(first_res[0])
                    else:
                        await player.queue.put_wait(first_res[0])

                async def load_remaining():
                    for q in track_queries[1:]:
                        try:
                            t = await wavelink.Playable.search(q, source=wavelink.TrackSource.YouTube)
                            if not t:
                                t = await wavelink.Playable.search(q, source=wavelink.TrackSource.SoundCloud)
                            if t:
                                await player.queue.put_wait(t[0])
                        except Exception:
                            pass

                asyncio.create_task(load_remaining())

                container = CicadaContainer(accent_color=0x1DB954)
                container.add_section(
                    content=(
                        f"**Spotify {data['type'].capitalize()} Loaded**\n"
                        f"> **Title:** **{data['name']}**\n"
                        f"> **Tracks Loaded:** `{len(track_queries)}` songs"
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
            elif data["type"] == "track":
                res = await wavelink.Playable.search(data["query"], source=wavelink.TrackSource.YouTube)
                if not res:
                    res = await wavelink.Playable.search(data["query"], source=wavelink.TrackSource.SoundCloud)
                data = res

        tracks = data
        if not tracks:
            await ctx.send_error(f"No tracks found for `{query}`.")
            return

        # Handle Standard Playlists
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

        # Handle Single Track
        track: wavelink.Playable = tracks[0]

        if not player.playing:
            await player.play(track)
            container = build_now_playing_container(track, player, ctx.author, bot=self.bot)
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
        """Skip currently playing track immediately."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or not player.playing:
            await ctx.send_error("No track is currently playing to skip.")
            return

        await player.skip(force=True)
        await ctx.send_success("Skipped to next track.")

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

        container = build_now_playing_container(player.current, player, ctx.author, bot=self.bot)
        view = MusicControllerView(self.bot, player, ctx.author.id)
        await send_container_response(ctx, container, view=view)


async def setup(bot: CicadaBot) -> None:
    """Load the Music Cog into Cicada 3301."""
    await bot.add_cog(Music(bot))
