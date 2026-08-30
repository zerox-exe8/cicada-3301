"""
Cicada 3301 Discord Bot - Clean Direct Audio Player (Lavalink v4)
High-performance, minimal, zero-bloat music engine.
Streams lossless 320kbps direct CDN audio straight to Discord voice channels.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, cast

import discord
from discord.ext import commands
import wavelink

from src.core.config import Config
from src.core.context import CustomContext
from src.cogs.music.direct_resolver import DirectStreamResolver

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("cicada.music")


class Music(commands.Cog):
    """Clean & Ultra-Fast Music Engine powered by Lavalink v4."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot
        self._node_lock = asyncio.Lock()

    async def _ensure_node(self) -> bool:
        """Connects or verifies Lavalink Node connection with active readiness wait."""
        async with self._node_lock:
            # 1. Check if an existing node is already connected
            for nid, n in list(wavelink.Pool.nodes.items()):
                if n.status == wavelink.NodeStatus.CONNECTED:
                    return True
                elif n.status == wavelink.NodeStatus.DISCONNECTED:
                    wavelink.Pool.nodes.pop(nid, None)

            try:
                uri = Config.LAVALINK_URI
                password = Config.LAVALINK_PASSWORD
                node = wavelink.Node(
                    uri=uri,
                    password=password,
                    retries=10,
                    inactive_player_timeout=300
                )
                await wavelink.Pool.connect(nodes=[node], client=self.bot)

                # Wait up to 5 seconds for WebSocket handshake to reach CONNECTED state
                for _ in range(25):
                    for n in wavelink.Pool.nodes.values():
                        if n.status == wavelink.NodeStatus.CONNECTED:
                            logger.info(f"Connected to Lavalink Node at {uri}")
                            return True
                    await asyncio.sleep(0.2)
            except Exception as e:
                logger.error(f"Failed to connect to Lavalink: {e}")
                return False
        return False

    @commands.hybrid_command(name="play", aliases=["p"], description="Play any song in your voice channel.")
    async def play(self, ctx: CustomContext, *, query: str) -> None:
        """Play any song with direct lossless 320kbps CDN stream."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You must be in a Voice Channel to play music.")
            return

        if not await self._ensure_node():
            await ctx.send("Audio server is initializing, please try again in 5 seconds.")
            return

        user_channel = ctx.author.voice.channel

        # 1. Connect Voice Client
        player: wavelink.Player | None = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or not player.connected:
            try:
                player = await user_channel.connect(cls=wavelink.Player, self_deaf=True)
            except Exception as e:
                await ctx.send(f"Could not connect to voice channel: `{e}`")
                return
        elif player.channel != user_channel:
            await player.move_to(user_channel)

        # 2. Resolve Direct Lossless Stream URL
        status_msg = await ctx.send(f"Searching for **{query}**...")
        
        track = None
        # 1. Best Unblocked 320kbps Audio Stream Engine (Zero Blocks, 100% Guaranteed Audio)
        try:
            resolved = await DirectStreamResolver.resolve(query)
            if resolved and resolved.get("stream_url"):
                search_res = await wavelink.Playable.search(resolved["stream_url"])
                if search_res:
                    track = search_res[0] if isinstance(search_res, list) else search_res
                    if resolved.get("title"):
                        track._title = resolved["title"]
                    if resolved.get("author"):
                        track._author = resolved["author"]
                    if resolved.get("artwork"):
                        track._artwork = resolved["artwork"]
        except Exception as e:
            logger.warning(f"Direct stream resolve failed: {e}")
            track = None

        # 2. Raw URL Fallback (for direct .mp3 / .wav streams)
        if not track and (query.startswith("http://") or query.startswith("https://")):
            try:
                search_res = await wavelink.Playable.search(query)
                if search_res:
                    track = search_res[0] if isinstance(search_res, list) else search_res
            except Exception:
                track = None

        if not track:
            await status_msg.edit(content=f"No results found for **{query}**.")
            return

        # 3. Play Track or Add to Queue
        if not player.playing:
            try:
                # Apply Studio Master EQ (Boost bass & crystal-clear treble frequencies)
                filters = wavelink.Filters()
                filters.equalizer.set(bands=[
                    {"band": 0, "gain": 0.15},
                    {"band": 1, "gain": 0.12},
                    {"band": 2, "gain": 0.08},
                    {"band": 11, "gain": 0.10},
                    {"band": 12, "gain": 0.12},
                    {"band": 13, "gain": 0.15}
                ])
                await player.set_filters(filters)
            except Exception:
                pass

            await player.set_volume(100)
            await player.play(track, volume=100, paused=False)
            embed = discord.Embed(
                title="Now Playing",
                description=f"**[{track.title}]({track.uri})**\nArtist: `{track.author}`",
                color=0x2B2D31
            )
            if getattr(track, "artwork", None):
                embed.set_thumbnail(url=track.artwork)
            embed.set_footer(text=f"Requested by {ctx.author.display_name} | 320 kbps HD")
            await status_msg.edit(content=None, embed=embed)
        else:
            await player.queue.put_wait(track)
            embed = discord.Embed(
                title="Track Queued",
                description=f"**[{track.title}]({track.uri})**\nPosition #{player.queue.count}",
                color=0x2B2D31
            )
            await status_msg.edit(content=None, embed=embed)

    @commands.hybrid_command(name="pause", description="Pause currently playing music.")
    async def pause(self, ctx: CustomContext) -> None:
        """Pause playback."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or not player.playing:
            await ctx.send("No music is currently playing.")
            return
        await player.pause(True)
        await ctx.send("Playback paused.")

    @commands.hybrid_command(name="resume", aliases=["unpause"], description="Resume paused music.")
    async def resume(self, ctx: CustomContext) -> None:
        """Resume playback."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player:
            await ctx.send("I am not connected to a voice channel.")
            return
        await player.pause(False)
        await ctx.send("Playback resumed.")

    @commands.hybrid_command(name="skip", aliases=["s", "next"], description="Skip the current track.")
    async def skip(self, ctx: CustomContext) -> None:
        """Skip currently playing track."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or not player.playing:
            await ctx.send("No track is currently playing.")
            return
        await player.skip(force=True)
        await ctx.send("Skipped to next track.")

    @commands.hybrid_command(name="stop", aliases=["disconnect", "dc"], description="Stop playback and leave voice.")
    async def stop(self, ctx: CustomContext) -> None:
        """Stop music, clear queue and leave voice."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player:
            await ctx.send("I am not connected to a voice channel.")
            return
        player.queue.clear()
        await player.disconnect()
        await ctx.send("Stopped playback and disconnected.")

    @commands.hybrid_command(name="queue", aliases=["q"], description="Show song queue.")
    async def queue(self, ctx: CustomContext) -> None:
        """Show current song queue."""
        player: wavelink.Player = cast(wavelink.Player, ctx.guild.voice_client)
        if not player or (not player.current and player.queue.is_empty):
            await ctx.send("The queue is empty.")
            return
        lines = []
        if player.current:
            lines.append(f"**Now Playing:** {player.current.title}")
        if not player.queue.is_empty:
            lines.append("\n**Up Next:**")
            for i, t in enumerate(list(player.queue)[:10], 1):
                lines.append(f"`{i}.` {t.title}")
        await ctx.send("\n".join(lines))

    # Auto-play next track in queue when current finishes
    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        player: wavelink.Player = payload.player
        reason_str = str(getattr(payload, "reason", "")).lower()
        if "replaced" in reason_str:
            return
        if not player.queue.is_empty:
            next_track = await player.queue.get_wait()
            await player.play(next_track, volume=100, paused=False)


async def setup(bot: CicadaBot) -> None:
    """Load the Music Cog into Cicada 3301."""
    await bot.add_cog(Music(bot))
