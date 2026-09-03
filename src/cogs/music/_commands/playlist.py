"""
Kyro Discord Bot - User Saved Playlists & Like System (Native Engine)
Instant playback, zero premature skips via dynamic query re-resolution,
and full playlist management (add, removetrack, view, list, delete).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional, List
import discord

from src.core.context import CustomContext
from src.cogs.music._player import GuildPlayer, shorten_artist
from src.cogs.music._extractor import NativeExtractor, clean_track_title
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music

logger = logging.getLogger("Kyro.Music.Cmd.Playlist")


def resolve_playlist_track_query(row: dict) -> str:
    """
    Safely resolve query for playlist track playback.
    Avoids passing stale, expired CDN streaming links which cause premature 403 skips.
    """
    url = (row.get("url") or "").strip()
    title = (row.get("title") or "").strip()
    author = (row.get("author") or "").strip()

    # Permanent web links are safe to re-extract
    if url.startswith("http") and any(d in url for d in ("youtube.com/watch", "youtu.be/", "soundcloud.com/", "open.spotify.com/track")):
        return url

    # Otherwise, search fresh by title + author for guaranteed fresh 320kbps stream
    clean_auth = author if author and author != "Official Artist" else ""
    return f"{title} {clean_auth}".strip() if clean_auth else title


async def handle_like(ctx: CustomContext, cog: Music) -> None:
    """Save the currently playing track to the user's personal Favorites playlist."""
    if not ctx.guild:
        return

    player = cog.controller.get_player(ctx.guild.id)
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

    # 2. Add track to playlist (store permanent web URL if available, else track URI)
    track_web_url = current.uri or current.url
    await db.execute(
        "INSERT INTO user_playlist_tracks (playlist_id, title, author, duration, url) VALUES ($1, $2, $3, $4, $5);",
        playlist_id,
        current.title,
        current.author or "Official Artist",
        current.duration,
        track_web_url,
    )

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**Added to Favorites**\n"
            f"> **Track:** [{current.title}]({track_web_url}) by `{current.author}`\n"
            f"> **Playlist:** `Favorites`"
        ),
        accessory={"type": 11, "media": {"url": current.thumbnail}} if current.thumbnail else None,
    )
    container.add_separator(divider=True)
    container.add_text("-# Powered by Kyro Studio")
    await send_container_response(ctx, container)


async def handle_playlist(
    ctx: CustomContext,
    cog: Music,
    action: Optional[str] = None,
    name: Optional[str] = None,
    *,
    query: Optional[str] = None,
) -> None:
    """Manage custom user playlists: add, removetrack, play, list, view, delete."""
    if not action or action.lower() in ("help", "guide"):
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Music Playlist Operations**\n"
                "> **list** • `?playlist list`\n"
                "> **play** • `?playlist play <name>`\n"
                "> **view** • `?playlist view <name>`\n"
                "> **add** • `?playlist add <name> [song title]`\n"
                "> **removetrack** • `?playlist removetrack <name> <track # | song title>`\n"
                "> **delete** • `?playlist delete <name>`"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Powered by Kyro Studio")
        await send_container_response(ctx, container)
        return

    act = action.lower().strip()
    db = ctx.bot.db
    user_id = ctx.author.id

    # 1. LIST PLAYLISTS
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

        lines = [f"> `{i}.` **{pl['playlist_name']}** • `{pl['track_count']} songs`" for i, pl in enumerate(playlists, 1)]
        container = KyroContainer(accent_color=None)
        container.add_section(content=f"**Your Saved Playlists ({len(playlists)})**\n" + "\n".join(lines))
        container.add_separator(divider=True)
        container.add_text("-# Powered by Kyro Studio")
        await send_container_response(ctx, container)

    # 2. ADD TRACK
    elif act == "add":
        if not name:
            await ctx.send_warning("Please specify a playlist name. Usage: `?playlist add <name> [song title]`")
            return

        clean_pl_name = name.strip()
        player = cog.controller.get_player(ctx.guild.id) if ctx.guild else None
        current = player.current if (player and player.current) else None

        title_to_save = None
        author_to_save = "Official Artist"
        duration_to_save = 0
        url_to_save = None

        if query:
            extracted = await NativeExtractor.extract(query)
            if extracted:
                title_to_save = extracted.title
                author_to_save = extracted.author
                duration_to_save = extracted.duration
                url_to_save = extracted.uri or extracted.url
        elif current:
            title_to_save = current.title
            author_to_save = current.author
            duration_to_save = current.duration
            url_to_save = current.uri or current.url

        if not title_to_save or not url_to_save:
            await ctx.send_warning("No song specified or currently playing. Usage: `?playlist add <name> <song title>`")
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
            await ctx.send_error("Failed to access playlist.")
            return

        await db.execute(
            "INSERT INTO user_playlist_tracks (playlist_id, title, author, duration, url) VALUES ($1, $2, $3, $4, $5);",
            pl_row["id"],
            title_to_save,
            author_to_save,
            duration_to_save,
            url_to_save,
        )

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Added to Playlist**\n"
                f"> **Track:** [{title_to_save}]({url_to_save}) by `{author_to_save}`\n"
                f"> **Playlist:** `{clean_pl_name}`"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Powered by Kyro Studio")
        await send_container_response(ctx, container)

    # 3. REMOVE TRACK FROM PLAYLIST
    elif act in ("removetrack", "rmtrack", "deltrack", "removesong", "delsong") or (act == "remove" and query):
        if not name:
            await ctx.send_warning("Usage: `?playlist removetrack <name> <track # | song title>`")
            return

        clean_pl_name = name.strip()
        target_param = (query or "").strip()

        if not target_param:
            await ctx.send_warning("Please specify which song to remove. Usage: `?playlist removetrack <name> <track # | song title>`")
            return

        pl_row = await db.fetch_one(
            "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
            user_id,
            clean_pl_name,
        )
        if not pl_row:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` not found.")
            return

        pl_id = pl_row["id"]
        tracks = await db.fetch_all(
            "SELECT id, title, author, url FROM user_playlist_tracks WHERE playlist_id = $1 ORDER BY id ASC;",
            pl_id,
        )
        if not tracks:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` is empty.")
            return

        removed_track = None

        # Case A: Track number passed (e.g. "3" or "#3")
        clean_num = target_param.lstrip("#")
        if clean_num.isdigit():
            idx = int(clean_num)
            if 1 <= idx <= len(tracks):
                removed_track = tracks[idx - 1]
                await db.execute("DELETE FROM user_playlist_tracks WHERE id = $1;", removed_track["id"])
            else:
                await ctx.send_warning(f"Invalid song number. Playlist `{clean_pl_name}` has {len(tracks)} song(s).")
                return
        else:
            # Case B: Search track by title
            matched = await db.fetch_one(
                "SELECT id, title, author FROM user_playlist_tracks WHERE playlist_id = $1 AND LOWER(title) LIKE '%' || LOWER($2) || '%' ORDER BY id ASC LIMIT 1;",
                pl_id,
                target_param,
            )
            if matched:
                removed_track = matched
                await db.execute("DELETE FROM user_playlist_tracks WHERE id = $1;", matched["id"])
            else:
                await ctx.send_warning(f"No song matching `{target_param}` found in `{clean_pl_name}`.")
                return

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Removed from Playlist**\n"
                f"> **Track:** `{removed_track['title']}`\n"
                f"> **Playlist:** `{clean_pl_name}`"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Powered by Kyro Studio")
        await send_container_response(ctx, container)

    # 4. PLAY PLAYLIST
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

        tracks = await db.fetch_all(
            "SELECT title, author, duration, url FROM user_playlist_tracks WHERE playlist_id = $1 ORDER BY id ASC;",
            pl_row["id"],
        )
        if not tracks:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` is empty.")
            return

        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send_warning("You must be in a voice channel to play music.")
            return

        player = cog.controller.get_or_create_player(ctx.guild)
        player.home_channel = ctx.channel
        await player.connect_voice(ctx.author.voice.channel)

        # 1. Resolve first track with fresh query (never uses expired CDN link)
        first_row = tracks[0]
        first_query = resolve_playlist_track_query(first_row)
        first_track = await NativeExtractor.extract(
            first_query,
            requester=ctx.author.display_name,
        )

        if not first_track:
            await ctx.send_error(f"Failed to load first track `{first_row['title']}`.")
            return

        # Start playback
        if not player.is_playing and not player.is_paused:
            await player.play_track(first_track)
        else:
            player.queue.append(first_track)

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Playing Playlist: `{clean_pl_name}`**\n"
                f"> **Queued:** `{len(tracks)}` songs\n"
                f"> **Starting Track:** [{first_track.title}]({first_track.url}) by `{first_track.author}`"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Powered by Kyro Studio")
        await send_container_response(ctx, container)

        # 2. Queue remaining tracks in background safely
        if len(tracks) > 1:
            async def _bg_load_playlist(remaining_tracks):
                for row in remaining_tracks:
                    try:
                        q = resolve_playlist_track_query(row)
                        t = await NativeExtractor.extract(
                            q,
                            requester=ctx.author.display_name,
                        )
                        if t:
                            player.queue.append(t)
                    except Exception as e:
                        logger.warning(f"Failed to load playlist track '{row.get('title')}': {e}")

            asyncio.create_task(_bg_load_playlist(tracks[1:]))

    # 5. VIEW PLAYLIST
    elif act == "view":
        if not name:
            await ctx.send_warning("Usage: `?playlist view <name>`")
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
            "SELECT title, author, duration, url FROM user_playlist_tracks WHERE playlist_id = $1 ORDER BY id ASC;",
            pl_row["id"],
        )
        if not tracks:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` is empty.")
            return

        lines = []
        for i, t in enumerate(tracks[:15], 1):
            dur_m = (t["duration"] or 0) // 60
            dur_s = (t["duration"] or 0) % 60
            dur_str = f"[{dur_m:02d}:{dur_s:02d}]"
            t_url = t.get("url")
            link = f"[{t['title']}]({t_url})" if t_url and t_url.startswith("http") else f"`{t['title']}`"
            author = f" by `{t['author']}`" if t.get("author") else ""
            lines.append(f"> `{i}.` {link}{author} • `{dur_str}`")

        if len(tracks) > 15:
            lines.append(f"> -# ...and {len(tracks) - 15} more tracks")

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"**Playlist: `{clean_pl_name}` ({len(tracks)} songs)**\n" + "\n".join(lines))
        container.add_separator(divider=True)
        container.add_text("-# Powered by Kyro Studio")
        await send_container_response(ctx, container)

    # 6. DELETE PLAYLIST
    elif act in ("delete", "remove"):
        if not name:
            await ctx.send_warning("Usage: `?playlist delete <name>`")
            return

        clean_pl_name = name.strip()
        deleted = await db.execute(
            "DELETE FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
            user_id,
            clean_pl_name,
        )
        if deleted > 0:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Playlist Deleted**\n> Playlist `{clean_pl_name}` has been completely removed.")
            container.add_separator(divider=True)
            container.add_text("-# Powered by Kyro Studio")
            await send_container_response(ctx, container)
        else:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` not found.")
