from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.cogs.music._extractor import NativeExtractor, is_playlist_url, UNWANTED_VERSION_KEYWORDS
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

    # ── Step 0: Clean query & prepare execution wrapper ──
    clean_q = query.strip()
    if clean_q.startswith("<") and clean_q.endswith(">"):
        clean_q = clean_q[1:-1].strip()

    try:
        # Check if Playlist URL (Spotify, SoundCloud, etc.)
        is_yt_query = any(yt in clean_q.lower() for yt in ("youtube.com/", "youtu.be/", "music.youtube.com/"))
        if is_playlist_url(clean_q) and not is_yt_query:
            try:
                pl = await asyncio.wait_for(
                    NativeExtractor.extract_playlist(clean_q, requester=ctx.author.display_name),
                    timeout=10.0
                )
            except Exception:
                pl = None

            if pl and pl.tracks:
                was_idle = (player.current is None) or (not player.is_playing and not player.is_paused)
                first_item = pl.tracks[0]
                first_track = Track(
                    title=first_item.title,
                    author=first_item.author,
                    url=first_item.url or clean_q,
                    stream_url="",
                    duration=first_item.duration,
                    thumbnail=pl.thumbnail,
                    requester=ctx.author.display_name,
                    requester_id=ctx.author.id,
                    query=first_item.query or f"{first_item.title} {first_item.author}",
                )
                for it in pl.tracks[1:]:
                    t = Track(
                        title=it.title,
                        author=it.author,
                        url=it.url or clean_q,
                        stream_url="",
                        duration=it.duration,
                        thumbnail=pl.thumbnail,
                        requester=ctx.author.display_name,
                        requester_id=ctx.author.id,
                        query=it.query or f"{it.title} {it.author}",
                    )
                    player.queue.append(t)
                if was_idle:
                    await player.play_track(first_track, message_to_edit=search_msg)
                else:
                    player.queue.append(first_track)
                pl_card = KyroContainer(accent_color=None)
                pl_card.add_section(
                    content=(
                        f"**Queued Playlist: [{pl.title}]({clean_q})**\n"
                        f"> **Total Tracks:** `{len(pl.tracks)} songs`\n"
                        f"> **Now Playing:** [{first_track.title}]({first_track.url}) by `{first_track.author}`\n"
                        f"> **Requested By:** `{ctx.author.display_name}`"
                    ) if was_idle else (
                        f"**Queued Playlist: [{pl.title}]({clean_q})**\n"
                        f"> **Total Tracks Added:** `{len(pl.tracks)} songs`\n"
                        f"> **Requested By:** `{ctx.author.display_name}`"
                    )
                )
                await send_container_response(ctx, pl_card)
                return
            elif "spotify.com" in clean_q:
                err_c = KyroContainer(accent_color=None)
                err_c.add_section(
                    content=(
                        "**Spotify Playlist Unavailable / Private**\n"
                        "> Kyro could not load this Spotify playlist.\n"
                        "> If this is a personal playlist, please open **Spotify** -> click **3 dots (`...`)** -> **Make Public** so Kyro can load the songs!"
                    )
                )
                if search_msg and isinstance(search_msg, discord.Message):
                    try:
                        await edit_container_response(search_msg, err_c)
                        return
                    except Exception:
                        pass
                await send_container_response(ctx, err_c)
                return

        # ── Step 1: Track Search & Resolution ──
        track: Optional[Track] = None
        lookup_target = clean_q

        # If single Spotify track URL, resolve metadata title first
        if any(sp in lookup_target for sp in ("spotify.com/track/", "spotify.link/", "spotify:track:")):
            try:
                sp_title = await asyncio.wait_for(
                    NativeExtractor._fetch_spotify_title(lookup_target),
                    timeout=5.0
                )
                if sp_title:
                    lookup_target = sp_title
            except Exception as e:
                logger.debug(f"Spotify track title fetch notice: {e}")

        is_direct_url = lookup_target.startswith(("http://", "https://"))

        # Case A: Direct URL -> Resolve via Lavalink directly
        if is_direct_url:
            try:
                results = await asyncio.wait_for(wavelink.Playable.search(lookup_target), timeout=6.0)
                if isinstance(results, wavelink.Playlist) and results.tracks:
                    pl = results
                    was_idle = (player.current is None) or (not player.is_playing and not player.is_paused)
                    first_p = pl.tracks[0]
                    first_thumb = first_p.artwork or (f"https://i.ytimg.com/vi/{first_p.identifier}/hqdefault.jpg" if getattr(first_p, "identifier", None) else None)
                    first_track = Track(
                        title=first_p.title or "Unknown Track",
                        author=first_p.author or "Unknown Artist",
                        url=first_p.uri or query,
                        stream_url="",
                        duration=int((first_p.length or 0) / 1000),
                        thumbnail=first_thumb,
                        requester=ctx.author.display_name,
                        requester_id=ctx.author.id,
                        query=query,
                    )
                    first_track._playable = first_p
                    for p in pl.tracks[1:]:
                        p_thumb = p.artwork or (f"https://i.ytimg.com/vi/{p.identifier}/hqdefault.jpg" if getattr(p, "identifier", None) else None)
                        t = Track(
                            title=p.title or "Unknown Track",
                            author=p.author or "Unknown Artist",
                            url=p.uri or query,
                            stream_url="",
                            duration=int((p.length or 0) / 1000),
                            thumbnail=p_thumb,
                            requester=ctx.author.display_name,
                            requester_id=ctx.author.id,
                            query=query,
                        )
                        t._playable = p
                        player.queue.append(t)
                    if was_idle:
                        await player.play_track(first_track, message_to_edit=search_msg)
                    else:
                        player.queue.append(first_track)
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
                    top_thumb = top_p.artwork or (f"https://i.ytimg.com/vi/{top_p.identifier}/hqdefault.jpg" if getattr(top_p, "identifier", None) else None)
                    track = Track(
                        title=top_p.title or "Unknown Track",
                        author=top_p.author or "Unknown Artist",
                        url=top_p.uri or query,
                        stream_url="",
                        duration=int((top_p.length or 0) / 1000),
                        thumbnail=top_thumb,
                        requester=ctx.author.display_name,
                        requester_id=ctx.author.id,
                        query=query,
                    )
                    track._playable = top_p
            except Exception as e:
                logger.debug(f"Direct URL search notice: {e}")

        # Case B: Plain text query -> High-speed Lavalink YouTube Music Search FIRST (0.3s, 100% accurate)
        if not track and not is_direct_url:
            try:
                results = await asyncio.wait_for(
                    wavelink.Playable.search(lookup_target, source=wavelink.TrackSource.YouTubeMusic),
                    timeout=5.0
                )
                if results and not isinstance(results, wavelink.Playlist):
                    chosen = results[0]
                    target_low = lookup_target.lower()
                    for cand in results[:5]:
                        c_t = (cand.title or "").lower()
                        c_a = (cand.author or "").lower()
                        has_unwanted = any(
                            kw in c_t or kw in c_a
                            for kw in UNWANTED_VERSION_KEYWORDS
                            if kw not in target_low
                        )
                        if not has_unwanted:
                            chosen = cand
                            break
                    top_p = chosen
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
                logger.debug(f"YouTube Music search notice: {e}")

        # Fallback 1: YouTube Search via Lavalink
        if not track and not is_direct_url:
            try:
                results = await asyncio.wait_for(
                    wavelink.Playable.search(lookup_target, source=wavelink.TrackSource.YouTube),
                    timeout=5.0
                )
                if results and not isinstance(results, wavelink.Playlist):
                    chosen = results[0]
                    target_low = lookup_target.lower()
                    for cand in results[:5]:
                        c_t = (cand.title or "").lower()
                        c_a = (cand.author or "").lower()
                        has_unwanted = any(
                            kw in c_t or kw in c_a
                            for kw in UNWANTED_VERSION_KEYWORDS
                            if kw not in target_low
                        )
                        if not has_unwanted:
                            chosen = cand
                            break
                    top_p = chosen
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
                logger.debug(f"YouTube fallback search notice: {e}")

        # Fallback 2: NativeExtractor (Unblocked JioSaavn CDN search)
        if not track:
            try:
                track = await asyncio.wait_for(
                    NativeExtractor.extract(lookup_target, requester=ctx.author.display_name),
                    timeout=6.0
                )
                if track and track.stream_url and ("saavncdn.com" in track.stream_url.lower() or ".mp4" in track.stream_url.lower()):
                    try:
                        direct_results = await asyncio.wait_for(wavelink.Playable.search(track.stream_url), timeout=4.0)
                        if direct_results:
                            track._playable = direct_results[0] if isinstance(direct_results, list) else direct_results.tracks[0]
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"NativeExtractor fallback search notice: {e}")

        # If still no track found, edit the searching message to inform user
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

        # ── Step 2: Dispatch Playback or Enqueue ──
        is_idle = (player.current is None) or (not player.is_playing and not player.is_paused)
        if is_idle:
            player._was_paused_for_empty_vc = False
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

    except Exception as e:
        logger.error(f"Guild {ctx.guild.id}: Uncaught error in execute_play for '{query}': {e}", exc_info=True)
        err_card = KyroContainer(accent_color=None)
        err_card.add_text(f"**Playback Error:** `{e}`")
        if search_msg and isinstance(search_msg, discord.Message):
            try:
                await edit_container_response(search_msg, err_card)
                return
            except Exception:
                pass
        await send_container_response(ctx, err_card)
        return

