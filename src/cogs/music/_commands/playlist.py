"""
Cicada 3301 Discord Bot - User Saved Playlists & Like System
Allows users to save currently playing songs, manage custom playlists, and load them seamlessly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, List

import discord

from src.core.context import CustomContext
from src.utils.containers import CicadaContainer, send_container_response
from src.cogs.music._types import TrackItem
from src.cogs.music._resolver import MusicResolver, clean_track_title

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController


async def handle_like(ctx: CustomContext, controller: MusicController) -> None:
    """Save the currently playing track to the user's personal Favorites playlist."""
    if not ctx.guild:
        return

    current = controller.get_current(ctx.guild.id)
    if not current:
        await ctx.send_warning("No track is currently playing to add to your Favorites.")
        return

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

    # 2. Add track to playlist
    await db.execute(
        "INSERT INTO user_playlist_tracks (playlist_id, title, author, duration, url) VALUES ($1, $2, $3, $4, $5);",
        playlist_id,
        current.title,
        current.author,
        current.duration,
        current.url,
    )

    container = CicadaContainer(accent_color=None)
    container.add_section(
        content=(
            f"**Added to Favorites**\n"
            f"> **Title:** [{current.title}]({current.url})\n"
            f"> **Artist:** `{current.author}`"
        ),
        accessory={"type": 11, "media": {"url": current.thumbnail}} if current.thumbnail else None,
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
        container = CicadaContainer(accent_color=None)
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
        container.add_text("-# Kyro Music Engine")
        await send_container_response(ctx, container)
        return

    act = action.lower()
    db = ctx.bot.db
    user_id = ctx.author.id

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

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Your Saved Playlists ({len(playlists)})**\n"
                + "\n".join(lines)
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"Use `?playlist play <name>` to start listening.")
        await send_container_response(ctx, container)

    elif act == "add":
        if not name:
            await ctx.send_warning("Please specify a playlist name. Usage: `?playlist add <name>`")
            return

        clean_pl_name = name.strip()
        current = controller.get_current(ctx.guild.id) if ctx.guild else None
        target_track: Optional[TrackItem] = None

        if query:
            target_track = await MusicResolver.resolve(query)
        elif current:
            target_track = current

        if not target_track:
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
            target_track.title,
            target_track.author,
            target_track.duration,
            target_track.url,
        )

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Added to Playlist**\n"
                f"> **Track:** [{target_track.title}]({target_track.url})\n"
                f"> **Playlist:** `{clean_pl_name}`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"Use `?playlist play {clean_pl_name}` to play this playlist.")
        await send_container_response(ctx, container)

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
        voice_client: discord.VoiceClient = ctx.guild.voice_client

        if not voice_client:
            try:
                voice_client = await user_channel.connect(timeout=10.0, reconnect=True)
            except Exception as e:
                await ctx.send_error(f"Failed to connect to voice channel: `{e}`")
                return
        elif voice_client.channel != user_channel:
            await voice_client.move_to(user_channel)

        queue = controller.get_queue(ctx.guild.id)
        controller.active_contexts[ctx.guild.id] = ctx

        first_resolved = False
        loaded_count = 0

        for t_info in tracks:
            track = await MusicResolver.resolve(t_info["url"])
            if track:
                track.requester = ctx.author.display_name
                if not first_resolved and not voice_client.is_playing() and not voice_client.is_paused():
                    controller.current_tracks[ctx.guild.id] = track
                    controller._play_stream(ctx, track)
                    first_resolved = True
                else:
                    queue.append(track)
                loaded_count += 1

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Loaded Playlist: {clean_pl_name}**\n"
                f"> Successfully queued **{loaded_count}** tracks into the server player."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"**Channel:** `#{user_channel.name}` | **Requested By:** `{ctx.author.display_name}`"
        )
        await send_container_response(ctx, container)

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

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Playlist: {clean_pl_name}**\n"
                + "\n".join(lines)
            )
        )
        await send_container_response(ctx, container)

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
