"""
Kyro Discord Bot - User Saved Playlists & Like System (Lavalink V4)
Enterprise-grade playlist manager with instant first-track playback and async background queueing.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional, List
import discord
import wavelink

from src.core.context import CustomContext
from src.cogs.music._player import KyroPlayer, shorten_artist
from src.cogs.music._resolver import MusicResolver, clean_track_title
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController

logger = logging.getLogger("Kyro.Music.Cmd.Playlist")


async def handle_like(ctx: CustomContext, controller: MusicController) -> None:
    """Save the currently playing track to the user's personal Favorites playlist."""
    if not ctx.guild:
        return

    player: KyroPlayer = ctx.guild.voice_client  # type: ignore
    if not player or not player.current:
        await ctx.send_warning("No track is currently playing to add to your Favorites.")
        return

    current = player.current
    db = ctx.bot.db
    user_id = ctx.author.id

    # 1. Ensure 'Favorites' playlist exists
    pl_row = await db.fetch_one(
        "SELECT id FROM user_playlists WHERE user_id = $1 AND playlist_name = 'Favorites';",
        user_id,
    )
    if not pl_row:
        await db.execute(
            "INSERT INTO user_playlists (user_id, playlist_name) VALUES ($1, 'Favorites') ON CONFLICT DO NOTHING;",
            user_id,
        )
        pl_row = await db.fetch_one(
            "SELECT id FROM user_playlists WHERE user_id = $1 AND playlist_name = 'Favorites';",
            user_id,
        )

    if not pl_row:
        await ctx.send_error("Failed to access your Favorites playlist.")
        return

    playlist_id = pl_row["id"]
    duration_sec = (current.length // 1000) if current.length else 0

    # 2. Add track to playlist
    await db.execute(
        "INSERT INTO user_playlist_tracks (playlist_id, title, author, duration, url) VALUES ($1, $2, $3, $4, $5);",
        playlist_id,
        current.title,
        current.author or "Official Artist",
        duration_sec,
        current.uri or "https://discord.com",
    )

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**Added to Favorites**\n"
            f"> **Title:** [{current.title}]({current.uri})\n"
            f"> **Artist:** `{current.author}`"
        ),
        accessory={"type": 11, "media": {"url": current.artwork}} if current.artwork else None,
    )
    container.add_separator(divider=True)
    container.add_text(
        f"**Playlist:** `Favorites` | **Saved By:** `{ctx.author.display_name}`"
    )
    container.add_separator(divider=True)
    container.add_text("-# Use ?playlist play Favorites to play your liked songs.")
    await send_container_response(ctx, container)


async def handle_playlist(
    ctx: CustomContext,
    controller: MusicController,
    action: Optional[str] = None,
    name: Optional[str] = None,
    *,
    query: Optional[str] = None,
) -> None:
    """Manage custom user playlists: add, play, list, view, delete."""
    if not action or action.lower() in ("help", "guide"):
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Music Playlist Manager**\n"
                "> Save your favorite tracks and play your personal music collections anytime."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            "`?like`, `?playlist add <name>`, `?playlist play <name>`, `?playlist list`, `?playlist view <name>`, `?playlist delete <name>`"
        )
        container.add_separator(divider=True)
        container.add_text("-# Kyro Music Engine • Lavalink V4")
        await send_container_response(ctx, container)
        return

    act = action.lower().strip()
    db = ctx.bot.db
    user_id = ctx.author.id

    # -------------------------------------------------------------
    # 1. LIST PLAYLISTS
    # -------------------------------------------------------------
    if act == "list":
        playlists = await db.fetch_all(
            """
            SELECT p.playlist_name, COUNT(t.id) as track_count
            FROM user_playlists p
            LEFT JOIN user_playlist_tracks t ON p.id = t.playlist_id
            WHERE p.user_id = $1
            GROUP BY p.id, p.playlist_name
            ORDER BY p.created_at DESC;
            """,
            user_id,
        )
        if not playlists:
            await ctx.send_warning("You do not have any saved playlists yet. Use `?like` or `?playlist add <name>` to create one.")
            return

        lines = []
        for i, pl in enumerate(playlists, 1):
            lines.append(f"`{i}.` **{pl['playlist_name']}** ({pl['track_count']} songs)")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Your Saved Playlists ({len(playlists)})**\n"
                + "\n".join(lines)
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"Use `?playlist play <name>` to start listening.")
        await send_container_response(ctx, container)

    # -------------------------------------------------------------
    # 2. ADD TRACK TO PLAYLIST
    # -------------------------------------------------------------
    elif act == "add":
        if not name:
            await ctx.send_warning("Please specify a playlist name. Usage: `?playlist add <name>`")
            return

        clean_pl_name = name.strip()
        player: KyroPlayer = ctx.guild.voice_client if ctx.guild else None  # type: ignore
        current = player.current if (player and player.current) else None

        title_to_save = None
        author_to_save = "Official Artist"
        duration_to_save = 0
        url_to_save = None

        if query:
            res = await MusicResolver.resolve(query)
            if res:
                track = res[0] if isinstance(res, list) else (res.tracks[0] if isinstance(res, wavelink.Playlist) else res)
                title_to_save = track.title
                author_to_save = track.author or "Official Artist"
                duration_to_save = (track.length // 1000) if track.length else 0
                url_to_save = track.uri
        elif current:
            title_to_save = current.title
            author_to_save = current.author or "Official Artist"
            duration_to_save = (current.length // 1000) if current.length else 0
            url_to_save = current.uri

        if not title_to_save or not url_to_save:
            await ctx.send_warning("No song is currently playing. Please specify a song: `?playlist add <name> <song title>`")
            return

        # Ensure playlist exists
        await db.execute(
            "INSERT INTO user_playlists (user_id, playlist_name) VALUES ($1, $2) ON CONFLICT DO NOTHING;",
            user_id,
            clean_pl_name,
        )
        pl_row = await db.fetch_one(
            "SELECT id FROM user_playlists WHERE user_id = $1 AND playlist_name = $2;",
            user_id,
            clean_pl_name,
        )
        if not pl_row:
            await ctx.send_error("Failed to access the playlist.")
            return

        playlist_id = pl_row["id"]
        await db.execute(
            "INSERT INTO user_playlist_tracks (playlist_id, title, author, duration, url) VALUES ($1, $2, $3, $4, $5);",
            playlist_id,
            title_to_save,
            author_to_save,
            duration_to_save,
            url_to_save,
        )

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Added to Playlist**\n"
                f"> **Track:** [{title_to_save}]({url_to_save})\n"
                f"> **Playlist:** `{clean_pl_name}`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"Use `?playlist play {clean_pl_name}` to play this playlist.")
        await send_container_response(ctx, container)

    # -------------------------------------------------------------
    # 3. PLAY PLAYLIST (RACE-CONDITION FREE)
    # -------------------------------------------------------------
    elif act == "play":
        if not name:
            await ctx.send_warning("Please specify which playlist to play. Usage: `?playlist play <name>`")
            return

        clean_pl_name = name.strip()
        pl_row = await db.fetch_one(
            "SELECT id FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
            user_id,
            clean_pl_name,
        )
        if not pl_row:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` not found. Use `?playlist list` to see your playlists.")
            return

        playlist_id = pl_row["id"]
        tracks = await db.fetch_all(
            "SELECT title, author, duration, url FROM user_playlist_tracks WHERE playlist_id = $1 ORDER BY id ASC;",
            playlist_id,
        )
        if not tracks:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` is empty.")
            return

        # Voice validation
        if not ctx.author or not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send_warning("You must be in a Voice Channel to play a playlist.")
            return

        user_channel = ctx.author.voice.channel
        player: KyroPlayer = ctx.guild.voice_client  # type: ignore

        if not player or not player.connected:
            try:
                player = await user_channel.connect(cls=KyroPlayer, self_deaf=True, timeout=10.0, reconnect=True)
            except Exception as e:
                await ctx.send_error(f"Failed to connect to voice channel: `{e}`")
                return
        elif player.channel != user_channel:
            await player.move_to(user_channel)

        player.home_channel = ctx.channel

        # Step 1: Resolve the very first track immediately so playback starts with 0 delay (<0.5s)
        first_track_info = tracks[0]
        first_resolved = await MusicResolver.resolve(first_track_info["url"], requester=ctx.author.display_name)
        if not first_resolved:
            first_resolved = await MusicResolver.resolve(
                f"{first_track_info['title']} {first_track_info['author']}",
                requester=ctx.author.display_name,
            )

        first_track = None
        if first_resolved:
            first_track = first_resolved[0] if isinstance(first_resolved, list) else (
                first_resolved.tracks[0] if isinstance(first_resolved, wavelink.Playlist) else first_resolved
            )

        # If player is idle, start first track immediately
        if first_track:
            if not player.playing:
                await player.play(first_track)
            else:
                player.queue.put(first_track)

        # Step 2: Background loader for remaining tracks into queue (avoids blocking & race condition)
        async def load_remaining_tracks():
            for t_info in tracks[1:]:
                try:
                    res = await MusicResolver.resolve(t_info["url"], requester=ctx.author.display_name)
                    if not res:
                        res = await MusicResolver.resolve(
                            f"{t_info['title']} {t_info['author']}",
                            requester=ctx.author.display_name,
                        )
                    if res:
                        t = res[0] if isinstance(res, list) else (
                            res.tracks[0] if isinstance(res, wavelink.Playlist) else res
                        )
                        player.queue.put(t)
                except Exception as ex:
                    logger.debug(f"Playlist background load notice: {ex}")

        if len(tracks) > 1:
            asyncio.create_task(load_remaining_tracks())

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Playing Playlist: {clean_pl_name}**\n"
                f"> Loaded **{len(tracks)}** songs into the server player queue."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"**Channel:** `#{user_channel.name}` | **Requested By:** `{ctx.author.display_name}`"
        )
        container.add_separator(divider=True)
        container.add_text("-# Kyro Music Engine • Lavalink V4")
        await send_container_response(ctx, container)

    # -------------------------------------------------------------
    # 4. VIEW PLAYLIST
    # -------------------------------------------------------------
    elif act == "view":
        if not name:
            await ctx.send_warning("Please specify a playlist name. Usage: `?playlist view <name>`")
            return

        clean_pl_name = name.strip()
        pl_row = await db.fetch_one(
            "SELECT id FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
            user_id,
            clean_pl_name,
        )
        if not pl_row:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` not found.")
            return

        tracks = await db.fetch_all(
            "SELECT title, author, duration, url FROM user_playlist_tracks WHERE playlist_id = $1 ORDER BY id ASC LIMIT 15;",
            pl_row["id"],
        )
        if not tracks:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` is currently empty.")
            return

        lines = []
        for i, t in enumerate(tracks, 1):
            dm = t["duration"] // 60
            ds = t["duration"] % 60
            lines.append(f"`{i}.` [{t['title']}]({t['url']}) (`{dm:02d}:{ds:02d}`)")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Playlist: {clean_pl_name}**\n"
                + "\n".join(lines)
            )
        )
        await send_container_response(ctx, container)

    # -------------------------------------------------------------
    # 5. DELETE PLAYLIST
    # -------------------------------------------------------------
    elif act == "delete":
        if not name:
            await ctx.send_warning("Please specify a playlist name to delete. Usage: `?playlist delete <name>`")
            return

        clean_pl_name = name.strip()
        pl_row = await db.fetch_one(
            "SELECT id FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
            user_id,
            clean_pl_name,
        )
        if not pl_row:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` not found.")
            return

        await db.execute("DELETE FROM user_playlists WHERE id = $1;", pl_row["id"])
        await ctx.send_success(f"Playlist **{clean_pl_name}** has been deleted successfully.", title="Playlist Deleted")
