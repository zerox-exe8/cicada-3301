"""
Cicada 3301 Discord Bot - Hyper-Fast Ultra-Resilient Music Engine
Instant in-memory caching, multi-client parallel search, and unbreakable streaming buffers.
"""

from __future__ import annotations

import asyncio
import logging
import re
import aiohttp
from typing import TYPE_CHECKING, Dict, List, Optional, Any

import discord
from discord.ext import commands
import yt_dlp

from src.core.context import CustomContext

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("cicada.music")

# Ultra-Reliable Streaming Buffer Options (Prevents mid-song drops & stuttering)
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 32M -analyzeduration 0',
    'options': '-vn -b:a 320k -bufsize 8192k'
}

YDL_OPTS = {
    'format': 'bestaudio[ext=m4a]/bestaudio/best',
    'quiet': True,
    'no_warnings': True,
    'extract_flat': False,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'source_address': '0.0.0.0',
    'socket_timeout': 6,
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios'],
            'skip': ['dash', 'hls', 'translated_subs']
        }
    }
}


class TrackItem:
    def __init__(self, title: str, author: str, duration: int, url: str, stream_url: str, thumbnail: str, requester: str):
        self.title = title
        self.author = author
        self.duration = duration
        self.url = url
        self.stream_url = stream_url
        self.thumbnail = thumbnail
        self.requester = requester


class MusicResolver:
    """Hyper-Fast Multi-Tier Stream Resolver with Instant RAM Caching."""
    _client_id = "Pb72ranhoyt6gw7hM7TkzUItXlMWSNSo"
    _CACHE: Dict[str, TrackItem] = {}

    @classmethod
    async def resolve(cls, query: str) -> Optional[TrackItem]:
        clean_q = query.strip()
        cache_key = clean_q.lower()

        # Step 0: Instant 0ms RAM Cache Check
        if cache_key in cls._CACHE:
            cached = cls._CACHE[cache_key]
            logger.info(f"Instant cache hit for '{clean_q}' (0ms)")
            return TrackItem(
                title=cached.title,
                author=cached.author,
                duration=cached.duration,
                url=cached.url,
                stream_url=cached.stream_url,
                thumbnail=cached.thumbnail,
                requester=""
            )

        is_url = clean_q.startswith("http://") or clean_q.startswith("https://")
        
        # Tier 1: yt-dlp Android Fast Studio Client
        loop = asyncio.get_event_loop()
        def _yt_extract():
            target = clean_q if is_url else f"ytsearch1:{clean_q}"
            try:
                with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                    info = ydl.extract_info(target, download=False)
                    if info:
                        if 'entries' in info and info['entries']:
                            return info['entries'][0]
                        return info
            except Exception as e:
                logger.warning(f"yt-dlp Tier 1 extraction notice for '{clean_q}': {e}")
            return None

        entry = await loop.run_in_executor(None, _yt_extract)
        if entry and entry.get('url'):
            raw_title = entry.get('title', clean_q)
            clean_t = re.sub(r'\(Full Video\)|\[Official Video\]|\(Official Audio\)|\|.*$', '', raw_title, flags=re.IGNORECASE).strip()
            author = entry.get('uploader') or entry.get('artist') or entry.get('channel') or 'Official Artist'
            track = TrackItem(
                title=clean_t or raw_title,
                author=author,
                duration=int(entry.get('duration', 0)),
                url=entry.get('webpage_url') or clean_q,
                stream_url=entry.get('url'),
                thumbnail=entry.get('thumbnail', ''),
                requester=""
            )
            cls._CACHE[cache_key] = track
            return track

        # Tier 2: Apple Music / iTunes Canonical Resolution + High-Speed Direct Stream
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with aiohttp.ClientSession(headers=headers) as s:
            canonical_t = clean_q
            canonical_a = "Official Artist"
            canonical_art = ""
            duration_s = 240
            
            try:
                itunes_url = f"https://itunes.apple.com/search?term={clean_q}&entity=song&limit=1"
                async with s.get(itunes_url, timeout=aiohttp.ClientTimeout(total=3)) as ir:
                    if ir.status == 200:
                        idata = await ir.json(content_type=None)
                        res = idata.get("results", [])
                        if res:
                            canonical_t = res[0].get("trackName", clean_q)
                            canonical_a = res[0].get("artistName", "Official Artist")
                            canonical_art = res[0].get("artworkUrl100", "").replace("100x100bb", "600x600bb")
                            duration_s = int(res[0].get("trackTimeMillis", 240000) / 1000)
            except Exception:
                pass

            # Multi-Candidate Fast Stream Search
            search_variations = [f"{canonical_t} {canonical_a}", canonical_t, clean_q]
            for term in search_variations:
                params = {"q": term, "client_id": cls._client_id, "limit": 6}
                try:
                    async with s.get(
                        "https://api-v2.soundcloud.com/search/tracks",
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=4)
                    ) as sr:
                        if sr.status == 200:
                            sdata = await sr.json()
                            items = sdata.get("collection", [])
                            if items:
                                for item in items:
                                    trans = item.get("media", {}).get("transcodings", [])
                                    sorted_trans = sorted(
                                        trans,
                                        key=lambda x: 0 if x.get("format", {}).get("protocol") == "progressive" else 1
                                    )
                                    for t in sorted_trans:
                                        meta_url = t.get("url")
                                        async with s.get(meta_url, params={"client_id": cls._client_id}, timeout=2) as mr:
                                            if mr.status == 200:
                                                mdata = await mr.json()
                                                direct_url = mdata.get("url")
                                                if direct_url:
                                                    track = TrackItem(
                                                        title=canonical_t,
                                                        author=canonical_a,
                                                        duration=duration_s,
                                                        url=item.get("permalink_url", clean_q),
                                                        stream_url=direct_url,
                                                        thumbnail=canonical_art or item.get("artwork_url", ""),
                                                        requester=""
                                                    )
                                                    cls._CACHE[cache_key] = track
                                                    return track
                except Exception:
                    continue
        return None


class Music(commands.Cog):
    """Ultra-Resilient Discord Music Engine."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot
        self.queues: Dict[int, List[TrackItem]] = {}
        self.current_tracks: Dict[int, TrackItem] = {}

    def _get_queue(self, guild_id: int) -> List[TrackItem]:
        if guild_id not in self.queues:
            self.queues[guild_id] = []
        return self.queues[guild_id]

    def _play_next(self, ctx: CustomContext) -> None:
        guild_id = ctx.guild.id
        voice_client: discord.VoiceClient = ctx.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            return

        queue = self._get_queue(guild_id)
        if queue:
            next_track = queue.pop(0)
            self.current_tracks[guild_id] = next_track
            try:
                source = discord.FFmpegOpusAudio(next_track.stream_url, **FFMPEG_OPTIONS)
                voice_client.play(source, after=lambda e: self._play_next(ctx))
                embed = discord.Embed(
                    title="Now Playing",
                    description=f"**[{next_track.title}]({next_track.url})**\nArtist: `{next_track.author}`",
                    color=0x2B2D31
                )
                if next_track.thumbnail:
                    embed.set_thumbnail(url=next_track.thumbnail)
                embed.set_footer(text=f"Requested by {next_track.requester} | HD Lossless Audio")
                asyncio.run_coroutine_threadsafe(ctx.send(embed=embed), self.bot.loop)
            except Exception as ex:
                logger.error(f"Error starting next track: {ex}")
                self._play_next(ctx)
        else:
            self.current_tracks.pop(guild_id, None)

    @commands.hybrid_command(name="play", aliases=["p"], description="Play any song in your voice channel with ultra-fast search.")
    async def play(self, ctx: CustomContext, *, query: str) -> None:
        """Play exact music tracks with hyper-fast search."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You must be in a Voice Channel to play music.")
            return

        user_channel = ctx.author.voice.channel
        voice_client: discord.VoiceClient = ctx.guild.voice_client

        # 1. Connect or Move Voice Client safely
        if not voice_client or not voice_client.is_connected():
            try:
                voice_client = await user_channel.connect(self_deaf=True, timeout=15.0)
            except Exception as e:
                await ctx.send(f"Could not connect to voice channel: `{e}`")
                return
        elif voice_client.channel != user_channel:
            await voice_client.move_to(user_channel)

        status_msg = await ctx.send(f"Searching for **{query}**...")

        # 2. Resolve Track with Hyper-Fast Multi-Tier Engine
        track = await MusicResolver.resolve(query)
        if not track or not track.stream_url:
            await status_msg.edit(content=f"No results found for **{query}**.")
            return

        track.requester = ctx.author.display_name
        guild_id = ctx.guild.id
        queue = self._get_queue(guild_id)

        # 3. Play or Queue Track
        if not voice_client.is_playing() and not voice_client.is_paused():
            self.current_tracks[guild_id] = track
            try:
                source = discord.FFmpegOpusAudio(track.stream_url, **FFMPEG_OPTIONS)
                voice_client.play(source, after=lambda e: self._play_next(ctx))
                embed = discord.Embed(
                    title="Now Playing",
                    description=f"**[{track.title}]({track.url})**\nArtist: `{track.author}`",
                    color=0x2B2D31
                )
                if track.thumbnail:
                    embed.set_thumbnail(url=track.thumbnail)
                embed.set_footer(text=f"Requested by {track.requester} | HD Lossless Audio")
                await status_msg.edit(content=None, embed=embed)
            except Exception as e:
                logger.error(f"Error starting playback: {e}")
                await status_msg.edit(content=f"Error playing track: `{e}`")
        else:
            queue.append(track)
            embed = discord.Embed(
                title="Track Queued",
                description=f"**[{track.title}]({track.url})**\nPosition #{len(queue)}",
                color=0x2B2D31
            )
            await status_msg.edit(content=None, embed=embed)

    @commands.hybrid_command(name="pause", description="Pause currently playing music.")
    async def pause(self, ctx: CustomContext) -> None:
        """Pause playback."""
        voice_client: discord.VoiceClient = ctx.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await ctx.send("No music is currently playing.")
            return
        voice_client.pause()
        await ctx.send("Playback paused.")

    @commands.hybrid_command(name="resume", aliases=["unpause"], description="Resume paused music.")
    async def resume(self, ctx: CustomContext) -> None:
        """Resume playback."""
        voice_client: discord.VoiceClient = ctx.guild.voice_client
        if not voice_client or not voice_client.is_paused():
            await ctx.send("Music is not paused.")
            return
        voice_client.resume()
        await ctx.send("Playback resumed.")

    @commands.hybrid_command(name="skip", aliases=["s", "next"], description="Skip the current track.")
    async def skip(self, ctx: CustomContext) -> None:
        """Skip currently playing track."""
        voice_client: discord.VoiceClient = ctx.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            await ctx.send("No track is currently playing.")
            return
        voice_client.stop()
        await ctx.send("Skipped to next track.")

    @commands.hybrid_command(name="stop", aliases=["disconnect", "dc"], description="Stop playback and leave voice.")
    async def stop(self, ctx: CustomContext) -> None:
        """Stop music, clear queue and leave voice."""
        voice_client: discord.VoiceClient = ctx.guild.voice_client
        if not voice_client:
            await ctx.send("I am not connected to a voice channel.")
            return
        self.queues.pop(ctx.guild.id, None)
        self.current_tracks.pop(ctx.guild.id, None)
        await voice_client.disconnect()
        await ctx.send("Stopped playback and disconnected.")

    @commands.hybrid_command(name="queue", aliases=["q"], description="Show song queue.")
    async def queue(self, ctx: CustomContext) -> None:
        """Show current song queue."""
        guild_id = ctx.guild.id
        current = self.current_tracks.get(guild_id)
        queue = self._get_queue(guild_id)

        if not current and not queue:
            await ctx.send("The queue is empty.")
            return

        lines = []
        if current:
            lines.append(f"**Now Playing:** {current.title} (`{current.author}`)")
        if queue:
            lines.append("\n**Up Next:**")
            for i, t in enumerate(queue[:10], 1):
                lines.append(f"`{i}.` {t.title} (`{t.author}`)")
        await ctx.send("\n".join(lines))


async def setup(bot: CicadaBot) -> None:
    """Load the Music Cog into Cicada 3301."""
    await bot.add_cog(Music(bot))
