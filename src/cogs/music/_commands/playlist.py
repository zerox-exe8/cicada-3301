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
from src.cogs.music._extractor import NativeExtractor, clean_track_title, is_playlist_url
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
        "SELECT id FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = 'favorites';",
        user_id,
    )
    if not pl_row:
        await db.execute(
            "INSERT INTO user_playlists (user_id, playlist_name) VALUES ($1, 'Favorites') ON CONFLICT DO NOTHING;",
            user_id,
        )
        pl_row = await db.fetch_one(
            "SELECT id FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = 'favorites';",
            user_id,
        )

    if not pl_row:
        await ctx.send_error("Failed to access your Favorites playlist.")
        return

    playlist_id = pl_row["id"]
    save_title = (current.title or "Unknown Track")[:250]
    save_author = (current.author or "Official Artist")[:250]

    # 2. Check for duplicate track in Favorites
    existing = await db.fetch_one(
        "SELECT id FROM user_playlist_tracks WHERE playlist_id = $1 AND LOWER(title) = LOWER($2);",
        playlist_id,
        save_title,
    )
    if existing:
        await ctx.send_warning(f"`{save_title}` is already saved in your Favorites playlist.")
        return

    # 3. Add track to playlist (safely access URL)
    track_web_url = getattr(current, "url", None) or getattr(current, "stream_url", "")
    await db.execute(
        "INSERT INTO user_playlist_tracks (playlist_id, title, author, duration, url) VALUES ($1, $2, $3, $4, $5);",
        playlist_id,
        save_title,
        save_author,
        current.duration,
        track_web_url,
    )

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**Added to Favorites**\n"
            f"> **Track:** [{save_title}]({track_web_url}) by `{save_author}`\n"
            f"> **Playlist:** `Favorites`"
        ),
        accessory={"type": 11, "media": {"url": current.thumbnail}} if current.thumbnail else None,
    )
    container.add_separator(divider=True)
    container.add_text("-# Powered by Kyro Studio")
    await send_container_response(ctx, container)


async def handle_unlike(ctx: CustomContext, cog: Music, *, query: Optional[str] = None) -> None:
    """Remove a song from Favorites or specified playlist by title, index, or currently playing track."""
    db = ctx.bot.db
    user_id = ctx.author.id

    target_playlist_name = "Favorites"
    clean_q = query.strip() if query else ""

    # Support 'in <playlist>' syntax: e.g. ?unlike Faded in Gym
    if " in " in clean_q.lower():
        q_part, pl_part = clean_q.rsplit(" in ", 1)
        check_pl = await db.fetch_one(
            "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
            user_id,
            pl_part.strip(),
        )
        if check_pl:
            target_playlist_name = check_pl["playlist_name"]
            clean_q = q_part.strip()

    pl_row = await db.fetch_one(
        "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
        user_id,
        target_playlist_name,
    )
    if not pl_row:
        await ctx.send_warning(f"Playlist `{target_playlist_name}` not found. Use `?playlist` to view your playlists.")
        return

    playlist_id = pl_row["id"]
    display_pl_name = pl_row["playlist_name"]
    tracks = await db.fetch_all(
        "SELECT id, title, author, url FROM user_playlist_tracks WHERE playlist_id = $1 ORDER BY id ASC;",
        playlist_id,
    )
    if not tracks:
        await ctx.send_warning(f"Your `{display_pl_name}` playlist is currently empty.")
        return

    target_track = None

    # Case 1: Song title or track number provided
    if clean_q:
        clean_num = clean_q.lstrip("#")
        if clean_num.isdigit():
            idx = int(clean_num)
            if 1 <= idx <= len(tracks):
                target_track = tracks[idx - 1]
            else:
                await ctx.send_warning(f"Invalid song number. Your Favorites has `{len(tracks)}` song(s).")
                return
        else:
            # Substring match on title
            matched = await db.fetch_one(
                "SELECT id, title, author FROM user_playlist_tracks WHERE playlist_id = $1 AND LOWER(title) LIKE '%' || LOWER($2) || '%' ORDER BY id ASC LIMIT 1;",
                playlist_id,
                clean_q,
            )
            if matched:
                target_track = matched
            else:
                await ctx.send_warning(f"No song matching `{clean_q}` found in `{display_pl_name}`.")
                return

    # Case 2: No query provided, resolve currently playing song in voice
    else:
        player = cog.controller.get_player(ctx.guild.id) if ctx.guild else None
        if player and player.current:
            cur_title = player.current.title
            matched = await db.fetch_one(
                "SELECT id, title, author FROM user_playlist_tracks WHERE playlist_id = $1 AND LOWER(title) = LOWER($2) LIMIT 1;",
                playlist_id,
                cur_title,
            )
            if not matched:
                matched = await db.fetch_one(
                    "SELECT id, title, author FROM user_playlist_tracks WHERE playlist_id = $1 AND LOWER(title) LIKE '%' || LOWER($2) || '%' LIMIT 1;",
                    playlist_id,
                    cur_title[:20],
                )
            if matched:
                target_track = matched
            else:
                await ctx.send_warning(f"Currently playing song `{cur_title}` is not in `{display_pl_name}`.\n> Specify a title: `?unlike <song title>`")
                return
        else:
            await ctx.send_warning("Specify which song to remove. Usage: `?unlike <song title | #number>`")
            return

    # Delete track from playlist
    await db.execute("DELETE FROM user_playlist_tracks WHERE id = $1;", target_track["id"])

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**Removed from Playlist**\n"
            f"> **Track:** `{target_track['title']}`\n"
            f"> **Playlist:** `{display_pl_name}`"
        )
    )
    container.add_separator(divider=True)
    container.add_text("-# Powered by Kyro Studio")
    await send_container_response(ctx, container)


def format_duration(seconds: int) -> str:
    """Format seconds into MM:SS or HH:MM:SS."""
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m:02d}:{s:02d}"


async def handle_playlist(
    ctx: CustomContext,
    cog: Music,
    action: Optional[str] = None,
    name: Optional[str] = None,
    *,
    query: Optional[str] = None,
) -> None:
    """Manage custom user playlists: add, removetrack, play, list, view, delete."""
    db = ctx.bot.db
    user_id = ctx.author.id
    act = (action or "").lower().strip()

    # If action is None or 'list' or 'help', display the comprehensive Playlist Hub
    if not act or act in ("help", "guide", "list"):
        # Fetch all user's playlists with track counts and total durations
        playlists = await db.fetch_all(
            """
            SELECT p.id, p.playlist_name, COUNT(t.id) as track_count, COALESCE(SUM(t.duration), 0) as total_duration
            FROM user_playlists p
            LEFT JOIN user_playlist_tracks t ON p.id = t.playlist_id
            WHERE p.user_id = $1
            GROUP BY p.id, p.playlist_name
            ORDER BY p.created_at DESC;
            """,
            user_id,
        )

        pl_lines = []
        if playlists:
            for i, pl in enumerate(playlists, 1):
                dur_str = format_duration(int(pl["total_duration"]))
                pl_lines.append(f"> • **{pl['playlist_name']}** • `{pl['track_count']} songs` • `{dur_str}`")
        else:
            pl_lines = [
                "> • None saved yet\n"
                ">   Use `?like` while listening to music or `?playlist add <name>` to create one."
            ]

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "### Music Playlist Hub\n"
                "> Personalized high-fidelity collections & lossless audio streaming."
            )
        )
        container.add_separator(divider=True)

        container.add_section(
            content=(
                f"**Your Saved Playlists ({len(playlists)})**\n"
                + "\n".join(pl_lines)
            )
        )
        container.add_separator(divider=True)

        current_prefix = ctx.prefix or "?"

        container.add_section(
            content=(
                "**Command Quick Guide**\n"
                f"> • **Play** • `{current_prefix}playlist play <name>`\n"
                f"> • **View** • `{current_prefix}playlist view <name>`\n"
                f"> • **Add Track** • `{current_prefix}playlist add <name> [song title]`\n"
                f"> • **Remove Track** • `{current_prefix}playlist removetrack <name> <# | title>`\n"
                f"> • **Like / Unlike** • `{current_prefix}like` • `{current_prefix}unlike [title | #]`\n"
                f"> • **Delete** • `{current_prefix}playlist delete <name>`"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Powered by Kyro Studio")
        await send_container_response(ctx, container)
        return

    # 2. ADD / IMPORT TRACK OR PLAYLIST
    elif act in ("add", "import"):
        if not name:
            await ctx.send_warning("Please specify a playlist name.\n> Example: `?playlist add Gym Starboy` or `?playlist import Gym <url>`")
            return

        clean_pl_name = name.strip()

        # Handle external playlist URL import: ?playlist add <name> <playlist_url>
        if query and is_playlist_url(query):
            wait_c = KyroContainer(accent_color=None)
            wait_c.add_text(f"**Importing playlist:** `{query}`...")
            await send_container_response(ctx, wait_c)

            pl_result = await NativeExtractor.extract_playlist(query, requester=ctx.author.display_name)
            if not pl_result or not pl_result.tracks:
                await ctx.send_warning(f"Could not load playlist from `{query}`.")
                return

            await db.execute(
                "INSERT INTO user_playlists (user_id, playlist_name) VALUES ($1, $2) ON CONFLICT DO NOTHING;",
                user_id,
                clean_pl_name,
            )
            pl_row = await db.fetch_one(
                "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
                user_id,
                clean_pl_name,
            )
            if not pl_row:
                await ctx.send_error("Failed to access playlist.")
                return

            added_count = 0
            for it in pl_result.tracks:
                t_title = (it.title or "Unknown Track")[:250]
                t_author = (it.author or "Official Artist")[:250]
                t_dur = it.duration
                t_url = it.url or it.query
                try:
                    await db.execute(
                        "INSERT INTO user_playlist_tracks (playlist_id, title, author, duration, url) VALUES ($1, $2, $3, $4, $5);",
                        pl_row["id"],
                        t_title,
                        t_author,
                        t_dur,
                        t_url,
                    )
                    added_count += 1
                except Exception:
                    pass

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Imported Playlist to `{pl_row['playlist_name']}`**\n"
                    f"> **Source:** [{pl_result.title}]({pl_result.url})\n"
                    f"> **Imported Songs:** `{added_count}` / `{pl_result.track_count}` songs\n"
                    f"> **Curator:** `{pl_result.author}`"
                )
            )
            container.add_separator(divider=True)
            container.add_text("-# Powered by Kyro Studio")
            await send_container_response(ctx, container)
            return

        player = cog.controller.get_player(ctx.guild.id) if ctx.guild else None
        current = player.current if (player and player.current) else None

        title_to_save = None
        author_to_save = "Official Artist"
        duration_to_save = 0
        url_to_save = None

        if query:
            extracted = await NativeExtractor.extract(query)
            if extracted:
                title_to_save = (extracted.title or "Unknown Track")[:250]
                author_to_save = (extracted.author or "Official Artist")[:250]
                duration_to_save = extracted.duration
                url_to_save = extracted.url
            else:
                await ctx.send_warning(f"Could not find any song matching `{query}`.\n> Try searching with full title or artist name.")
                return
        elif current:
            title_to_save = (current.title or "Unknown Track")[:250]
            author_to_save = (current.author or "Official Artist")[:250]
            duration_to_save = current.duration
            url_to_save = current.url
        else:
            await ctx.send_warning(f"No song specified or currently playing.\n> Example: `?playlist add {clean_pl_name} Starboy`")
            return

        # Ensure playlist exists
        await db.execute(
            "INSERT INTO user_playlists (user_id, playlist_name) VALUES ($1, $2) ON CONFLICT DO NOTHING;",
            user_id,
            clean_pl_name,
        )
        pl_row = await db.fetch_one(
            "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
            user_id,
            clean_pl_name,
        )
        if not pl_row:
            await ctx.send_error("Failed to access playlist.")
            return

        # Check duplicate track in playlist
        existing_track = await db.fetch_one(
            "SELECT id FROM user_playlist_tracks WHERE playlist_id = $1 AND LOWER(title) = LOWER($2);",
            pl_row["id"],
            title_to_save,
        )
        if existing_track:
            await ctx.send_warning(f"`{title_to_save}` is already saved in playlist `{pl_row['playlist_name']}`.")
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
                f"> **Playlist:** `{pl_row['playlist_name']}`"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Powered by Kyro Studio")
        await send_container_response(ctx, container)

    # 3. REMOVE TRACK FROM PLAYLIST
    elif act in ("removetrack", "rmtrack", "deltrack", "removesong", "delsong", "remove"):
        if not name:
            await ctx.send_warning("Specify which playlist and song to remove.\n> Example: `?playlist removetrack Gym 2` or `?playlist removetrack Gym Starboy`")
            return

        clean_pl_name = name.strip()
        target_param = (query or "").strip()

        if not target_param:
            await ctx.send_warning(
                f"Specify which song to remove from `{clean_pl_name}`.\n"
                f"> Example: `?playlist removetrack {clean_pl_name} 2` or `?playlist removetrack {clean_pl_name} Starboy`\n"
                f"> To delete the entire playlist, use `?playlist delete {clean_pl_name}`."
            )
            return

        pl_row = await db.fetch_one(
            "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
            user_id,
            clean_pl_name,
        )
        if not pl_row:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` not found. Use `?playlist` to see your playlists.")
            return

        pl_id = pl_row["id"]
        tracks = await db.fetch_all(
            "SELECT id, title, author, url FROM user_playlist_tracks WHERE playlist_id = $1 ORDER BY id ASC;",
            pl_id,
        )
        if not tracks:
            await ctx.send_warning(f"Playlist `{pl_row['playlist_name']}` is empty.")
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
                await ctx.send_warning(f"Invalid song number. Playlist `{pl_row['playlist_name']}` has {len(tracks)} song(s).\n> Example: `?playlist removetrack {pl_row['playlist_name']} 1`")
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
                await ctx.send_warning(f"No song matching `{target_param}` found in `{pl_row['playlist_name']}`.\n> Tip: View song list via `?playlist view {pl_row['playlist_name']}`")
                return

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Removed from Playlist**\n"
                f"> **Track:** `{removed_track['title']}`\n"
                f"> **Playlist:** `{pl_row['playlist_name']}`"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Powered by Kyro Studio")
        await send_container_response(ctx, container)

    # 4. PLAY PLAYLIST
    elif act in ("play", "start", "load"):
        if not name:
            await ctx.send_warning("Please specify which playlist to play.\n> Example: `?playlist play Gym`")
            return

        # Check if user passed an external playlist URL (e.g. ?playlist play https://open.spotify.com/playlist/...)
        target_candidate = f"{name} {query}".strip() if query else (name or "").strip()
        if is_playlist_url(target_candidate) or (name and is_playlist_url(name)):
            from src.cogs.music._commands.play import execute_play
            await execute_play(cog, ctx, target_candidate if is_playlist_url(target_candidate) else name)
            return

        # Support multi-word playlist names without quotes (e.g. ?playlist play Chill Vibes)
        clean_pl_name = f"{name} {query}".strip() if query else name.strip()
        pl_row = await db.fetch_one(
            "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
            user_id,
            clean_pl_name,
        )
        if not pl_row and query:
            pl_row = await db.fetch_one(
                "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
                user_id,
                name.strip(),
            )

        if not pl_row:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` not found. Use `?playlist list` to see your playlists.")
            return

        clean_pl_name = pl_row["playlist_name"]
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
        try:
            await player.connect_voice(ctx.author.voice.channel)
        except Exception as e:
            await ctx.send_error(f"Failed to connect to voice channel: `{e}`")
            return

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

        # 2. Queue remaining tracks in background safely (bound to current generation)
        if len(tracks) > 1:
            load_gen = player._current_gen

            async def _bg_load_playlist(remaining_tracks: list, target_gen: int) -> None:
                for row in remaining_tracks:
                    # Abort background enqueue if player was stopped, cleared, or disconnected
                    if player._current_gen != target_gen or not player.is_connected:
                        break
                    try:
                        q = resolve_playlist_track_query(row)
                        t = await NativeExtractor.extract(
                            q,
                            requester=ctx.author.display_name,
                        )
                        if player._current_gen != target_gen or not player.is_connected:
                            break
                        if t:
                            player.queue.append(t)
                    except Exception as e:
                        logger.warning(f"Failed to load playlist track '{row.get('title')}': {e}")

            asyncio.create_task(_bg_load_playlist(tracks[1:], load_gen))

    # 5. VIEW PLAYLIST
    elif act in ("view", "show", "info"):
        if not name:
            await ctx.send_warning("Please specify which playlist to view.\n> Example: `?playlist view Gym`")
            return

        # Support multi-word playlist names and optional page number (e.g. ?playlist view Chill Vibes or ?playlist view Gym 2)
        has_trailing_page = query and query.strip().isdigit()
        page_num = int(query.strip()) if has_trailing_page else 1
        clean_pl_name = name.strip() if has_trailing_page else (f"{name} {query}".strip() if query else name.strip())

        pl_row = await db.fetch_one(
            "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
            user_id,
            clean_pl_name,
        )
        if not pl_row and query and not has_trailing_page:
            pl_row = await db.fetch_one(
                "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
                user_id,
                name.strip(),
            )

        if not pl_row:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` not found. Use `?playlist` to see your playlists.")
            return

        display_name = pl_row["playlist_name"]
        tracks = await db.fetch_all(
            "SELECT id, title, author, duration, url FROM user_playlist_tracks WHERE playlist_id = $1 ORDER BY id ASC;",
            pl_row["id"],
        )
        if not tracks:
            await ctx.send_warning(f"Playlist `{display_name}` is empty. Add songs using `?playlist add {display_name} [song]`.")
            return

        per_page = 15
        total_pages = max(1, (len(tracks) + per_page - 1) // per_page)
        page_num = max(1, min(page_num, total_pages))
        start_idx = (page_num - 1) * per_page
        page_tracks = tracks[start_idx : start_idx + per_page]

        total_sec = sum(t["duration"] or 0 for t in tracks)
        total_dur_str = format_duration(total_sec)

        lines = []
        for i, t in enumerate(page_tracks, start=start_idx + 1):
            dur_str = format_duration(t["duration"] or 0)
            t_url = t.get("url")
            link = f"[{t['title']}]({t_url})" if t_url and t_url.startswith("http") else f"`{t['title']}`"
            author = f" • {t['author']}" if t.get("author") and t.get("author") != "Official Artist" else ""
            lines.append(f"> `{i}.` {link}{author} • `{dur_str}`")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Playlist: {display_name}\n"
                f"> **Total Songs:** `{len(tracks)}` • **Duration:** `{total_dur_str}`\n"
                f"> **Page:** `{page_num} of {total_pages}` • **Curator:** {ctx.author.display_name}"
            )
        )
        container.add_separator(divider=True)
        container.add_section(content="\n".join(lines))
        container.add_separator(divider=True)
        footer_page_hint = f"> • **Next Page:** `?playlist view {display_name} {page_num + 1}`\n" if page_num < total_pages else ""
        container.add_text(
            f"> • **Play Collection:** `?playlist play {display_name}`\n"
            f"> • **Remove Song:** `?playlist removetrack {display_name} <#>`\n"
            f"{footer_page_hint}\n"
            f"-# Powered by Kyro Studio"
        )
        await send_container_response(ctx, container)

    # 6. DELETE PLAYLIST (Strictly explicit deletion keywords)
    elif act in ("delete", "del", "drop"):
        if not name:
            await ctx.send_warning("Please specify which playlist to delete.\n> Example: `?playlist delete Gym`")
            return

        clean_pl_name = f"{name} {query}".strip() if query else name.strip()
        pl_row = await db.fetch_one(
            "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
            user_id,
            clean_pl_name,
        )
        if not pl_row and query:
            pl_row = await db.fetch_one(
                "SELECT id, playlist_name FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = LOWER($2);",
                user_id,
                name.strip(),
            )

        if not pl_row:
            await ctx.send_warning(f"Playlist `{clean_pl_name}` not found.\n> Use `?playlist` to see your existing playlists.")
            return

        await db.execute(
            "DELETE FROM user_playlists WHERE id = $1;",
            pl_row["id"],
        )
        container = KyroContainer(accent_color=None)
        container.add_section(content=f"**Playlist Deleted**\n> Playlist `{pl_row['playlist_name']}` has been completely removed.")
        container.add_separator(divider=True)
        container.add_text("-# Powered by Kyro Studio")
        await send_container_response(ctx, container)

    else:
        current_prefix = ctx.prefix or "?"
        await ctx.send_warning(
            f"Unknown playlist action `{action}`.\n"
            f"> Available actions: `{current_prefix}playlist play`, `view`, `add`, `removetrack`, `list`, `delete`"
        )
