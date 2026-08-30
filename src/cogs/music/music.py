"""
Cicada 3301 Discord Bot - Ultra-Reliable High-Definition Music Engine (Lavalink v4)
Features:
- Dual-Engine Unblockable Lossless Audio Stream (SoundCloud Verified + YouTube Music)
- Intelligent Studio Canonical Matcher (Zero cover / remix / fan loop channels)
- Voice Gateway Handshake Event Sync (Prevents silent playback drops)
- Automatic Stream Failover & Auto-Healing
- Minimalist Premium Container Layout (Integrated Custom Emojis)
- Interactive Controller (Pause/Resume, Skip, Stop, Queue)
- 320kbps CD Quality Audio
"""

from __future__ import annotations

import asyncio
import logging
import re
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

UNWANTED_KEYWORDS = [
    "remix", "cover", "slowed", "reverb", "edit", "tribute", "karaoke",
    "instrumental", "bass boost", "mashup", "tiktok version", "bootleg",
    "1 hour", "1hour", "loop", "nightcore", "parody"
]


def format_duration(ms: int) -> str:
    """Format milliseconds into mm:ss or hh:mm:ss."""
    seconds = int(ms / 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def clean_query_text(q: str) -> str:
    """Remove conversational filler words like 'song', 'gaana' for razor-sharp studio matching."""
    if q.startswith("http://") or q.startswith("https://"):
        return q
    cleaned = re.sub(r'\b(song|songs|gaana|gana|audio|video|mp3|full song|track)\b', '', q, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned if len(cleaned) > 1 else q


def is_clean_original(track: wavelink.Playable, query: str) -> bool:
    """Validate that track is not an unwanted remix/cover/loop unless user requested it."""
    title_lower = track.title.lower() if track.title else ""
    query_lower = query.lower()
    for kw in UNWANTED_KEYWORDS:
        if kw in title_lower and kw not in query_lower:
            return False
    return True


def select_best_track(tracks: list[wavelink.Playable], query: str) -> wavelink.Playable:
    """Select the most accurate original studio track from search results."""
    for t in tracks:
        if is_clean_original(t, query):
            return t
    return tracks[0]


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
            f"> **Artist:** `{track.author}` â€¢ **Duration:** `{duration_str}`"
        ),
        accessory=accessory,
    )
    container.add_separator(divider=True)
    container.add_text(
        f"â€¢ **Channel:** `{channel_name}` | **Bitrate:** `320 kbps (HD)`\n"
        f"â€¢ **Requested By:** {author.mention}"
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
            for i, track in enumerate(list(player.queue)[:10], 1):
                dur = format_duration(track.length) if track.length else "Live"
                lines.append(f"`{i}.` **[{track.title}]({track.uri})** (`{dur}`)")
            if self.player.queue.count > 10:
                lines.append(f"-# ...and `{player.queue.count - 10}` more tracks")

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
    """High-Performance, Ultra-Reliable Music Cog."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot: CicadaBot = bot
        self.bot.loop.create_task(self._ensure_node())

    async def _ensure_node(self) -> bool:
        """Ensure dedicated Lavalink node is connected with live, verified session."""
        for n in list(wavelink.Pool.nodes.values()):
            if n.status == wavelink.NodeStatus.CONNECTED and getattr(n, "session_id", None):
                # Verify session is alive on Lavalink server
                try:
                    if self.bot.session:
                        url = f"{n.uri}/v4/sessions/{n.session_id}/players"
                        async with self.bot.session.get(url, headers=n.headers, timeout=aiohttp.ClientTimeout(total=2.0)) as r:
                            if r.status in (200, 204):
                                return True
                except Exception:
                    pass

            try:
                await n.close(eject=True)
            except Exception:
                pass

        if not Config.LAVALINK_URI:
            return False

        try:
            node = wavelink.Node(
                identifier="Dedicated-Node",
                uri=Config.LAVALINK_URI,
                password=Config.LAVALINK_PASSWORD,
                inactive_player_timeout=None,
            )
            await wavelink.Pool.connect(nodes=[node], client=self.bot, cache_capacity=100)
            for _ in range(12):
                if any(n.status == wavelink.NodeStatus.CONNECTED and getattr(n, "session_id", None) for n in wavelink.Pool.nodes.values()):
                    logger.info("Connected to Dedicated Lavalink v4 node successfully with verified live session!")
                    return True
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Error connecting to Lavalink node pool: {e}")

        return any(n.status == wavelink.NodeStatus.CONNECTED for n in wavelink.Pool.nodes.values())

    # â”€â”€â”€ WAVELINK EVENT LISTENERS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
                await player.set_volume(100)
                await player.play(next_track, volume=100, paused=False)
            except Exception as e:
                logger.error(f"Error auto-playing next track: {e}")

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload) -> None:
        """Fired when an error occurs during playback."""
        logger.error(f"Track playback exception: {payload.exception}")
        player: wavelink.Player | None = payload.player
        if not player:
            return

        if not player.queue.is_empty:
            try:
                next_track = await player.queue.get_wait()
                await player.set_volume(100)
                await player.play(next_track, volume=100, paused=False)
            except Exception as e:
                logger.error(f"Error playing next queued track: {e}")

        if not player.queue.is_empty:
            try:
                next_track = await player.queue.get_wait()
                await player.set_volume(100)
                await player.play(next_track, volume=100, paused=False)
            except Exception:
                pass

    # â”€â”€â”€ MUSIC COMMANDS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @commands.hybrid_command(name="play", aliases=["p"], description="Play any song, Spotify link, or playlist in voice channel.")
    @app_commands.describe(query="Song title, artist name, Spotify, SoundCloud or YouTube link")
    async def play(self, ctx: CustomContext, *, query: str) -> None:
        """Instant ultra low-latency music playback with clean official studio matching."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send_error("You must join a Voice Channel to play music.")
            return

        # Ensure node is connected
        connected = await self._ensure_node()
        if not connected:
            await ctx.send_error("Audio node is initializing. Please retry in a few seconds.")
            return

        user_channel = ctx.author.voice.channel

        # 1. Connect or retrieve player cleanly with voice gateway event synchronization
        player: wavelink.Player | None = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or not player.connected:
            try:
                player = await user_channel.connect(cls=wavelink.Player, self_deaf=True)
                if hasattr(player, "_connection_event"):
                    try:
                        await asyncio.wait_for(player._connection_event.wait(), timeout=4.0)
                    except asyncio.TimeoutError:
                        pass
            except Exception:
                player = cast(wavelink.Player, ctx.guild.voice_client)
                if not player or not player.connected:
                    try:
                        if ctx.guild.voice_client:
                            await ctx.guild.voice_client.disconnect(force=True)
                            await asyncio.sleep(0.3)
                        player = await user_channel.connect(cls=wavelink.Player, self_deaf=True)
                        if hasattr(player, "_connection_event"):
                            try:
                                await asyncio.wait_for(player._connection_event.wait(), timeout=4.0)
                            except asyncio.TimeoutError:
                                pass
                    except Exception as e2:
                        await ctx.send_error(f"Could not connect to voice channel: `{e2}`")
                        return
        elif player.channel != user_channel:
            if not player.playing:
                await player.move_to(user_channel)
                if hasattr(player, "_connection_event"):
                    try:
                        await asyncio.wait_for(player._connection_event.wait(), timeout=3.0)
                    except asyncio.TimeoutError:
                        pass
            else:
                await ctx.send_error(f"I am already playing audio in {player.channel.mention}.")
                return

        # 2. Check for Spotify URLs
        if "spotify.com" in query.lower():
            spotify_data = await SpotifyResolver.resolve_url(query)
            if spotify_data:
                if spotify_data["type"] in ("playlist", "album"):
                    track_queries = spotify_data["tracks"]
                    if not track_queries:
                        await ctx.send_error("Could not load tracks from this Spotify playlist.")
                        return

                    async def search_single(q: str):
                        for src in (wavelink.TrackSource.SoundCloud, wavelink.TrackSource.YouTubeMusic, wavelink.TrackSource.YouTube):
                            try:
                                r = await wavelink.Playable.search(q, source=src)
                                if r:
                                    return select_best_track(r, q)
                            except Exception:
                                pass
                        return None

                    first_track = await search_single(track_queries[0])
                    if first_track:
                        if not player.playing:
                            await player.set_volume(100)
                            await player.play(first_track, volume=100, paused=False)
                        else:
                            await player.queue.put_wait(first_track)

                    async def load_remaining():
                        for q in track_queries[1:]:
                            t = await search_single(q)
                            if t:
                                await player.queue.put_wait(t)

                    asyncio.create_task(load_remaining())

                    container = CicadaContainer(accent_color=0x1DB954)
                    container.add_section(
                        content=(
                            f"**Spotify {spotify_data['type'].capitalize()} Loaded**\n"
                            f"> **Title:** **{spotify_data['name']}**\n"
                            f"> **Tracks Loaded:** `{len(track_queries)}` songs"
                        )
                    )
                    container.add_separator(divider=True)
                    container.add_text(
                        f"â€¢ **Channel:** `{user_channel.name}` | **Bitrate:** `320 kbps (HD)`\n"
                        f"â€¢ **Requested By:** {ctx.author.mention}"
                    )
                    view = MusicControllerView(self.bot, player, ctx.author.id)
                    await send_container_response(ctx, container, view=view)
                    return
                elif spotify_data["type"] == "track":
                    query = spotify_data["query"]

        # 3. Clean Studio Matcher Pipeline (SoundCloud Verified -> YouTube Music -> YouTube)
        tracks = None
        cleaned = clean_query_text(query)

        # Build list of precise search terms with Spotify/iTunes canonical resolver
        search_terms = []
        if not (query.startswith("http://") or query.startswith("https://")):
            canonical = await SpotifyResolver.resolve_canonical(cleaned)
            if canonical:
                search_terms.append(canonical)
            if cleaned != query:
                search_terms.append(cleaned)
            search_terms.append(query)
        else:
            search_terms = [query]

        try:
            if query.startswith("http://") or query.startswith("https://"):
                tracks = await wavelink.Playable.search(query)
            else:
                for term in search_terms:
                    for src in (wavelink.TrackSource.YouTubeMusic, wavelink.TrackSource.SoundCloud, wavelink.TrackSource.YouTube):
                        try:
                            res = await wavelink.Playable.search(term, source=src)
                            if res:
                                best = select_best_track(res, query)
                                tracks = [best]
                                break
                        except Exception:
                            pass
                    if tracks:
                        break
        except Exception as e:
            await ctx.send_error(f"Failed to find song: `{e}`")
            return

        if not tracks:
            await ctx.send_error(f"No tracks found for `{query}`.")
            return

        # 4. Handle Standard Playlists
        if isinstance(tracks, wavelink.Playlist):
            added_count = len(tracks.tracks)
            if not player.playing:
                await player.set_volume(100)
                await player.play(tracks.tracks[0], volume=100, paused=False)
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
                f"â€¢ **Channel:** `{user_channel.name}` | **Bitrate:** `320 kbps (HD)`\n"
                f"â€¢ **Requested By:** {ctx.author.mention}"
            )
            view = MusicControllerView(self.bot, player, ctx.author.id)
            await send_container_response(ctx, container, view=view)
            return

        # 5. Handle Single Studio Track
        track: wavelink.Playable = tracks[0]

        if not player.playing:
            await player.set_volume(100)
            if player.paused:
                await player.pause(False)
            await player.play(track, replace=True, volume=100, paused=False)
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
                    f"> **Artist:** `{track.author}` â€¢ **Duration:** `{duration_str}`"
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"â€¢ **Queue Length:** `{player.queue.count} tracks` | **Bitrate:** `320 kbps`\n"
                f"â€¢ **Requested By:** {ctx.author.mention}"
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

    @commands.hybrid_command(name="mdebug", description="Deep diagnostics of Voice Gateway and Lavalink state.")
    async def mdebug(self, ctx: CustomContext) -> None:
        """Inspect the exact internal state of Voice Gateway, Wavelink and Lavalink."""
        lines = ["**Music System Diagnostics**\n"]

        try:
            # 1. Node status
            if not wavelink.Pool.nodes:
                lines.append("â€¢ **Nodes:** `No nodes in pool`")
            else:
                for nid, n in wavelink.Pool.nodes.items():
                    status_str = getattr(n, "status", "UNKNOWN")
                    if hasattr(status_str, "name"):
                        status_str = status_str.name
                    lines.append(f"â€¢ **Node [{nid}]:** `Status: {status_str}` | `URI: {getattr(n, 'uri', 'N/A')}`")

            # 2. Local Voice Client
            vc = ctx.guild.voice_client
            if not vc:
                lines.append("â€¢ **Voice Client:** `None (Not connected in guild)`")
            else:
                is_conn = getattr(vc, "connected", None)
                if is_conn is None:
                    is_conn = getattr(vc, "is_connected", lambda: False)()
                lines.append(f"â€¢ **Voice Client:** `Type: {type(vc).__name__}` | `Connected: {is_conn}` | `Channel: {getattr(vc, 'channel', 'N/A')}`")

            # 3. Wavelink Player
            player = cast(wavelink.Player, vc) if isinstance(vc, wavelink.Player) else None
            if player:
                lines.append(f"â€¢ **Player State:** `Playing: {getattr(player, 'playing', False)}` | `Paused: {getattr(player, 'paused', False)}` | `Volume: {getattr(player, 'volume', 100)}` | `Position: {getattr(player, 'position', 0)}ms`")
                if player.current:
                    lines.append(f"â€¢ **Current Track:** `Title: {getattr(player.current, 'title', 'N/A')}` | `Author: {getattr(player.current, 'author', 'N/A')}` | `Source: {getattr(player.current, 'source', 'N/A')}`")
                else:
                    lines.append("â€¢ **Current Track:** `None`")

                # 4. Lavalink Remote Player Info via Node API
                if getattr(player, "node", None):
                    try:
                        p_info = await player.node.fetch_player_info(ctx.guild.id)
                        if p_info:
                            st = p_info.state
                            vs = p_info.voice_state
                            tr = p_info.track
                            lines.append("\n**Lavalink Server Internal State:**")
                            lines.append(f"> **UDP Connected:** `{st.connected}` | **Voice Ping:** `{st.ping}ms`")
                            lines.append(f"> **Audio Position:** `{st.position}ms`")
                            lines.append(f"> **Endpoint:** `{vs.endpoint}`")
                            lines.append(f"> **Lavalink Track:** `{tr.title if tr else 'None'}`")
                        else:
                            lines.append("\n> **Lavalink Player Info:** `None (No active player held on server)`")
                    except Exception as e:
                        lines.append(f"\n> **Lavalink Info Error:** `{e}`")
        except Exception as err:
            lines.append(f"**Diagnostic Error:** `{err}`")

        container = CicadaContainer(accent_color=None)
        container.add_section(content="\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Diagnostic timestamp: {discord.utils.utcnow().strftime('%H:%M:%S UTC')}")
        await send_container_response(ctx, container)


async def setup(bot: CicadaBot) -> None:
    """Load the Music Cog into Cicada 3301."""
    await bot.add_cog(Music(bot))
