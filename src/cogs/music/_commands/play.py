"""
Kyro Discord Bot - Native Play Command
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.cogs.music._extractor import NativeExtractor, is_playlist_url
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
    if ctx.guild.me.voice and ctx.guild.me.voice.channel:
        if ctx.guild.me.voice.channel.id != voice_channel.id:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Voice Channel Conflict**\n"
                    f"> I am already active in {ctx.guild.me.voice.channel.mention}. Please join that channel to play music."
                )
            )
            await send_container_response(ctx, container)
            return

    player = cog.controller.get_or_create_player(ctx.guild)
    player.home_channel = ctx.channel

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

    # Check if query is an external Playlist or Album URL
    if is_playlist_url(query):
        search_container = KyroContainer(accent_color=None)
        search_container.add_text(f"**Loading Playlist:** `{query}`...")
        search_msg = await send_container_response(ctx, search_container)

        pl_result = await NativeExtractor.extract_playlist(query, requester=ctx.author.display_name)
        if not pl_result or not pl_result.tracks:
            err_container = KyroContainer(accent_color=None)
            err_container.add_text(f"**Failed to load playlist or playlist is empty:** `{query}`")
            if search_msg and isinstance(search_msg, discord.Message):
                try:
                    await edit_container_response(search_msg, err_container)
                    return
                except Exception:
                    pass
            await send_container_response(ctx, err_container)
            return

        # 1. Resolve first track immediately for instant playback with 0 lag
        first_item = pl_result.tracks[0]
        first_track = await NativeExtractor.extract(first_item.query, requester=ctx.author.display_name)
        if not first_track and first_item.title:
            fallback_q = f"{first_item.title} {first_item.author}".strip()
            first_track = await NativeExtractor.extract(fallback_q, requester=ctx.author.display_name)

        if not first_track:
            for item in pl_result.tracks[1:4]:
                first_track = await NativeExtractor.extract(item.query, requester=ctx.author.display_name)
                if not first_track and item.title:
                    first_track = await NativeExtractor.extract(f"{item.title} {item.author}".strip(), requester=ctx.author.display_name)
                if first_track:
                    break

        if not first_track:
            err_container = KyroContainer(accent_color=None)
            err_container.add_text(f"**Could not resolve any playable tracks from playlist:** `{pl_result.title}`")
            if search_msg and isinstance(search_msg, discord.Message):
                try:
                    await edit_container_response(search_msg, err_container)
                    return
                except Exception:
                    pass
            await send_container_response(ctx, err_container)
            return

        first_track.requester_id = ctx.author.id

        # 2. Append ALL remaining tracks from playlist to queue immediately so the entire queue is visible
        was_idle = not player.is_playing and not player.is_paused
        insert_start_idx = len(player.queue)

        for item in pl_result.tracks[1:]:
            t = Track(
                title=item.title,
                author=item.author,
                url=item.url or item.query,
                stream_url="",
                duration=item.duration,
                thumbnail=pl_result.thumbnail,
                requester=ctx.author.display_name,
                requester_id=ctx.author.id,
                query=item.query,
            )
            player.queue.append(t)

        # 3. Start playback if idle, or append first_track to queue
        if was_idle:
            await player.play_track(first_track, message_to_edit=search_msg)
        else:
            # Insert first_track at front of this newly enqueued batch
            player.queue.insert(insert_start_idx, first_track)

        # 4. Build preview of upcoming tracks for the playlist announcement card
        if was_idle:
            upcoming_items = player.queue[:6]
        else:
            upcoming_items = player.queue[insert_start_idx:insert_start_idx + 6]

        upcoming_lines = []
        for i, it in enumerate(upcoming_items, start=1):
            dur_text = it.formatted_duration
            upcoming_lines.append(f"`{i:02d}.` [{it.title}]({it.url}) `[{dur_text}]` — `{it.author}`")

        upcoming_preview = "\n".join(upcoming_lines) if upcoming_lines else "No upcoming tracks."
        remaining_count = pl_result.track_count - (1 if was_idle else 0) - len(upcoming_lines)

        # 5. Send rich playlist announcement card showing all upcoming songs
        pl_card = KyroContainer(accent_color=None)
        pl_card.add_section(
            content=(
                f"**Queued Playlist: [{pl_result.title}]({pl_result.url})**\n"
                f"> **Curator / Author:** `{pl_result.author}`\n"
                f"> **Total Tracks:** `{pl_result.track_count} songs`\n"
                f"> **Now Playing:** [{first_track.title}]({first_track.url}) by `{first_track.author}`\n"
                f"> **Requested By:** `{ctx.author.display_name}`"
            ) if was_idle else (
                f"**Queued Playlist: [{pl_result.title}]({pl_result.url})**\n"
                f"> **Curator / Author:** `{pl_result.author}`\n"
                f"> **Total Tracks Added:** `{pl_result.track_count} songs`\n"
                f"> **Requested By:** `{ctx.author.display_name}`"
            ),
            accessory={"type": 11, "media": {"url": pl_result.thumbnail}} if pl_result.thumbnail else None,
        )
        pl_card.add_separator(divider=True)
        pl_card.add_text(
            f"**Upcoming Songs:**\n{upcoming_preview}\n"
            + (f"-# ...and {remaining_count} more songs. Use `?queue` to view all pages.\n" if remaining_count > 0 else "")
            + "-# Powered by Kyro Studio"
        )

        if not was_idle and search_msg and isinstance(search_msg, discord.Message):
            try:
                await edit_container_response(search_msg, pl_card)
            except Exception:
                await send_container_response(ctx, pl_card)
        else:
            await send_container_response(ctx, pl_card)

        return

    # 1. Send Searching Track card first
    search_container = KyroContainer(accent_color=None)
    search_container.add_text(f"**Searching track:** `{query}`...")
    search_msg = await send_container_response(ctx, search_container)

    # 2. Extract track in background
    track = await NativeExtractor.extract(query, requester=ctx.author.display_name)
    if track:
        track.requester_id = ctx.author.id

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

    # 3. If nothing is currently playing, start playback
    if not player.is_playing and not player.is_paused:
        await player.play_track(track, message_to_edit=search_msg)
    else:
        # Add to queue
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
        await send_container_response(ctx, queue_container)
