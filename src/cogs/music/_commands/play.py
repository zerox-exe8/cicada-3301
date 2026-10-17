from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.cogs.music._extractor import NativeExtractor, is_playlist_url
from src.cogs.music._models import Track
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music

logger = logging.getLogger("Kyro.Music.Play")


async def execute_play(cog: Music, ctx: commands.Context, query: Optional[str] = None) -> None:
    """Execute native play command."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        container = KyroContainer(accent_color=None)
        container.add_text("**You must be in a voice channel to play music.**")
        await send_container_response(ctx, container)
        return

    voice_channel = ctx.author.voice.channel

    # Check if bot is already connected to another VC in this guild
    bot_vc = ctx.guild.me.voice.channel if ctx.guild.me.voice else None
    if bot_vc and bot_vc.id != voice_channel.id:
        player_check = cog.controller.get_player(ctx.guild.id)
        current_listeners = [m for m in bot_vc.members if not m.bot]
        # Only block moving if actively streaming music AND has active human listeners
        if player_check and player_check.is_playing and len(current_listeners) > 0:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Voice Channel Conflict**\n"
                    f"> I am currently playing music for {len(current_listeners)} listener(s) in {bot_vc.mention}.\n"
                    "> Please join that channel or wait until playback concludes."
                )
            )
            await send_container_response(ctx, container)
            return

    player = cog.controller.get_or_create_player(ctx.guild)
    player.home_channel = ctx.channel
    player.cancel_empty_vc_timer(auto_resume=False)

    # Connect to voice
    try:
        await player.connect_voice(voice_channel)
    except Exception as e:
        logger.error(f"Voice connect error: {e}")
        container = KyroContainer(accent_color=None)
        container.add_text(f"**Failed to connect to voice channel:** `{e}`")
        await send_container_response(ctx, container)
        return

    # Handle empty query
    if not query or not query.strip():
        if player.is_paused:
            player.resume()
            container = KyroContainer(accent_color=None)
            container.add_text("**Resumed playback.**")
            await send_container_response(ctx, container)
            return
        elif player.queue and not player.is_playing:
            next_track = player.queue.pop(0)
            await player.play_track(next_track)
            return
        else:
            container = KyroContainer(accent_color=None)
            container.add_text("**Please provide a song title or URL.**\n> Usage: `?play <song title or URL>`")
            await send_container_response(ctx, container)
            return

    import wavelink

    # Send Searching Track card
    search_container = KyroContainer(accent_color=None)
    search_container.add_text(f"**Searching:** `{query}`...")
    search_msg = await send_container_response(ctx, search_container)

    # ── Step 1: Direct Lavalink Search (Instant official YouTube, Spotify, SoundCloud & Queries) ──
    track: Optional[Track] = None
    try:
        results = await wavelink.Playable.search(query)
        if isinstance(results, wavelink.Playlist) and results.tracks:
            pl = results
            was_idle = not player.is_playing and not player.is_paused
            first_p = pl.tracks[0]
            first_track = Track(
                title=first_p.title or "Unknown Track",
                author=first_p.author or "Unknown Artist",
                url=first_p.uri or query,
                stream_url="",
                duration=int((first_p.length or 0) / 1000),
                thumbnail=first_p.artwork,
                requester=ctx.author.display_name,
                requester_id=ctx.author.id,
                query=query,
            )
            first_track._playable = first_p
            for p in pl.tracks[1:]:
                t = Track(
                    title=p.title or "Unknown Track",
                    author=p.author or "Unknown Artist",
                    url=p.uri or query,
                    stream_url="",
                    duration=int((p.length or 0) / 1000),
                    thumbnail=p.artwork,
                    requester=ctx.author.display_name,
                    requester_id=ctx.author.id,
                    query=query,
                )
                t._playable = p
                player.queue.append(t)
            if was_idle:
                await player.play_track(first_track, message_to_edit=search_msg)
            else:
                player.queue.insert(0, first_track)
            pl_card = KyroContainer(accent_color=None)
            pl_card.add_section(
                content=(
                    f"**Queued Playlist: [{pl.name}]({query})**\n"
                    f"> **Total Tracks:** `{len(pl.tracks)} songs`\n"
                    f"> **Now Playing:** [{first_track.title}]({first_track.url}) by `{first_track.author}`\n"
                    f"> **Requested By:** `{ctx.author.display_name}`"
                ) if was_idle else (
                    f"**Queued Playlist: [{pl.name}]({query})**\n"
                    f"> **Total Tracks Added:** `{len(pl.tracks)} songs`\n"
                    f"> **Requested By:** `{ctx.author.display_name}`"
                )
            )
            await send_container_response(ctx, pl_card)
            return
        elif results and not isinstance(results, wavelink.Playlist):
            top_p = results[0]
            track = Track(
                title=top_p.title or "Unknown Track",
                author=top_p.author or "Unknown Artist",
                url=top_p.uri or query,
                stream_url="",
                duration=int((top_p.length or 0) / 1000),
                thumbnail=top_p.artwork,
                requester=ctx.author.display_name,
                requester_id=ctx.author.id,
                query=query,
            )
            track._playable = top_p
    except Exception as e:
        logger.debug(f"Direct Wavelink search notice: {e}")

    # ── Step 2: Native Extractor Fallback ──
    if not track:
        try:
            track = await NativeExtractor.extract(query, requester=ctx.author.display_name)
        except Exception as e:
            logger.debug(f"NativeExtractor fallback notice: {e}")

    if not track:
        err_container = KyroContainer(accent_color=None)
        err_container.add_text(f"**No results found for:** `{query}`")
        if search_msg and isinstance(search_msg, discord.Message):
            try:
                await edit_container_response(search_msg, err_container)
                return
            except Exception:
                pass
        await send_container_response(ctx, err_container)
        return

    track.query = query
    track.requester_id = ctx.author.id

    # Record analytics if available
    if hasattr(cog, "analytics") and cog.analytics:
        _q = query.strip()
        _src = "spotify_url" if "spotify" in _q else ("youtube_url" if "youtu" in _q else "search")
        try:
            await cog.analytics.record_play(
                user_id=ctx.author.id,
                guild_id=ctx.guild.id if ctx.guild else None,
                track_title=track.title,
                artist=track.author,
                source=_src,
            )
        except Exception:
            pass

    # Play immediately if idle, else enqueue
    if not player.is_playing and not player.is_paused:
        await player.play_track(track, message_to_edit=search_msg)
    else:
        player.queue.append(track)
        pos = len(player.queue)
        queue_container = KyroContainer(accent_color=None)
        queue_container.add_section(
            content=(
                f"**Added to Queue [Position #{pos}]**\n"
                f"> **Track:** [{track.title}]({track.url})\n"
                f"> **Artist:** `{track.author}`\n"
                f"> **Duration:** `{track.formatted_duration}`\n"
                f"> **Requested By:** `{track.requester}`"
            ),
            accessory={"type": 11, "media": {"url": track.thumbnail}} if track.thumbnail else None,
        )
        if search_msg and isinstance(search_msg, discord.Message):
            try:
                await edit_container_response(search_msg, queue_container)
                return
            except Exception:
                pass
        await send_container_response(ctx, queue_container)
    return

