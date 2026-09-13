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
        if not first_track:
            for item in pl_result.tracks[1:4]:
                first_track = await NativeExtractor.extract(item.query, requester=ctx.author.display_name)
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

        # 2. Start playback if idle, or append to queue
        was_idle = not player.is_playing and not player.is_paused
        if was_idle:
            await player.play_track(first_track, message_to_edit=search_msg)
        else:
            player.queue.append(first_track)

        # 3. Send rich playlist announcement card
        pl_card = KyroContainer(accent_color=None)
        pl_card.add_section(
            content=(
                f"**Queued Playlist: [{pl_result.title}]({pl_result.url})**\n"
                f"> **Curator / Author:** `{pl_result.author}`\n"
                f"> **Total Tracks:** `{pl_result.track_count} songs`\n"
                f"> **First Track:** [{first_track.title}]({first_track.url}) by `{first_track.author}`\n"
                f"> **Requested By:** `{ctx.author.display_name}`"
            ),
            accessory={"type": 11, "media": {"url": pl_result.thumbnail}} if pl_result.thumbnail else None,
        )
        pl_card.add_separator(divider=True)
        pl_card.add_text("-# Powered by Kyro Studio")

        if not was_idle and search_msg and isinstance(search_msg, discord.Message):
            try:
                await edit_container_response(search_msg, pl_card)
            except Exception:
                await send_container_response(ctx, pl_card)
        else:
            await send_container_response(ctx, pl_card)

        # 4. Background queue remaining tracks safely
        if len(pl_result.tracks) > 1:
            load_gen = player._current_gen
            requester_name = ctx.author.display_name
            requester_id = ctx.author.id

            async def _bg_load_external_playlist(remaining_items: list, target_gen: int) -> None:
                for it in remaining_items:
                    if player._current_gen != target_gen or not player.is_connected:
                        break
                    try:
                        t = await NativeExtractor.extract(it.query, requester=requester_name)
                        if player._current_gen != target_gen or not player.is_connected:
                            break
                        if t:
                            t.requester_id = requester_id
                            player.queue.append(t)
                        await asyncio.sleep(0.15)
                    except Exception as e:
                        logger.debug(f"Background playlist load item error: {e}")

            asyncio.create_task(_bg_load_external_playlist(pl_result.tracks[1:], load_gen))

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
