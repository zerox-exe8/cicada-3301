"""
Kyro Discord Bot - Interactive Components V2 Playlist Views
Provides interactive Dropdown Select Menu for playlist selection,
quick Play / Shuffle Play buttons, live paginated track browsing, and safe deletion.
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import discord

from src.cogs.music._models import Track
from src.cogs.music._extractor import NativeExtractor
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot
    from src.cogs.music.music import Music
    from src.cogs.music._player import GuildPlayer

logger = logging.getLogger("Kyro.Music.PlaylistViews")


def format_duration(seconds: int) -> str:
    """Format seconds into MM:SS or HH:MM:SS."""
    if not seconds:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m:02d}:{s:02d}"


def resolve_track_query(row: dict) -> str:
    """Resolve query for playlist track without stale CDN links."""
    url = (row.get("url") or "").strip()
    title = (row.get("title") or "").strip()
    author = (row.get("author") or "").strip()

    if url.startswith("http") and any(d in url for d in ("youtube.com/watch", "youtu.be/", "soundcloud.com/", "open.spotify.com/track")):
        return url

    clean_auth = author if author and author != "Official Artist" else ""
    return f"{title} {clean_auth}".strip() if clean_auth else title


async def execute_saved_playlist_playback(
    bot: KyroBot,
    cog: Music,
    guild: discord.Guild,
    user: discord.User | discord.Member,
    channel: discord.abc.Messageable,
    pl_row: dict,
    tracks: list[dict],
    shuffle: bool = False,
    interaction: Optional[discord.Interaction] = None,
) -> None:
    """Execute playback of a saved playlist with immediate full queueing and optional shuffle."""
    if not tracks:
        c = KyroContainer()
        c.add_section(content=f"**Playlist Notice**\n> Playlist `{pl_row['playlist_name']}` is empty.")
        if interaction:
            await send_container_response(interaction, c, ephemeral=True)
        else:
            await send_container_response(channel, c)
        return

    member = guild.get_member(user.id)
    if not member or not member.voice or not member.voice.channel:
        c = KyroContainer()
        c.add_section(content="**Voice Error**\n> You must be connected to a voice channel to play music.")
        if interaction:
            await send_container_response(interaction, c, ephemeral=True)
        else:
            await send_container_response(channel, c)
        return

    if interaction and not interaction.response.is_done():
        await interaction.response.defer()

    player = cog.controller.get_or_create_player(guild)
    player.home_channel = channel

    try:
        await player.connect_voice(member.voice.channel)
    except Exception as e:
        c = KyroContainer()
        c.add_section(content=f"**Connection Error**\n> Failed to connect to voice channel: `{e}`")
        if interaction:
            await interaction.followup.send(embed=c.to_embed(), ephemeral=True)
        else:
            await send_container_response(channel, c)
        return

    # Shuffle track rows if requested
    play_order = list(tracks)
    if shuffle:
        random.shuffle(play_order)

    # 1. Resolve first track immediately for instant start
    first_row = play_order[0]
    first_query = resolve_track_query(first_row)
    first_track = await NativeExtractor.extract(first_query, requester=user.display_name)

    if not first_track:
        # Fallback to secondary search
        alt_q = f"{first_row.get('title', '')} {first_row.get('author', '')}".strip()
        first_track = await NativeExtractor.extract(alt_q, requester=user.display_name)

    if not first_track:
        c = KyroContainer()
        c.add_section(content=f"**Playback Error**\n> Failed to load first track `{first_row.get('title')}`.")
        if interaction:
            await interaction.followup.send(embed=c.to_embed(), ephemeral=True)
        else:
            await send_container_response(channel, c)
        return

    first_track.requester_id = user.id

    # 2. Append all remaining tracks to queue immediately
    was_idle = not player.is_playing and not player.is_paused
    insert_start_idx = len(player.queue)

    for row in play_order[1:]:
        q = resolve_track_query(row)
        t = Track(
            title=row.get("title") or "Unknown Track",
            author=row.get("author") or "Official Artist",
            url=row.get("url") or q,
            stream_url="",
            duration=int(row.get("duration") or 0),
            requester=user.display_name,
            requester_id=user.id,
            query=q,
        )
        player.queue.append(t)

    # Start playback
    if was_idle:
        await player.play_track(first_track)
    else:
        player.queue.insert(insert_start_idx, first_track)

    # 3. Build preview of upcoming tracks
    if was_idle:
        upcoming_items = player.queue[:6]
    else:
        upcoming_items = player.queue[insert_start_idx:insert_start_idx + 6]

    upcoming_lines = []
    for i, it in enumerate(upcoming_items, start=1):
        dur_text = it.formatted_duration
        upcoming_lines.append(f"`{i:02d}.` [{it.title}]({it.url}) `[{dur_text}]` — `{it.author}`")

    upcoming_preview = "\n".join(upcoming_lines) if upcoming_lines else "No upcoming tracks."
    remaining_count = len(play_order) - (1 if was_idle else 0) - len(upcoming_lines)

    mode_label = "Shuffled Playlist" if shuffle else "Playlist"
    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**Playing {mode_label}: `{pl_row['playlist_name']}`**\n"
            f"> **Total Queued:** `{len(play_order)}` songs\n"
            f"> **Now Playing:** [{first_track.title}]({first_track.url}) by `{first_track.author}`\n"
            f"> **Mode:** `{'Shuffle Random' if shuffle else 'Normal Sequential'}`"
        ) if was_idle else (
            f"**Playing {mode_label}: `{pl_row['playlist_name']}`**\n"
            f"> **Total Queued:** `{len(play_order)}` songs\n"
            f"> **Next Track:** [{first_track.title}]({first_track.url}) by `{first_track.author}`\n"
            f"> **Mode:** `{'Shuffle Random' if shuffle else 'Normal Sequential'}`"
        )
    )
    container.add_separator(divider=True)
    container.add_text(
        f"**Upcoming Songs:**\n{upcoming_preview}\n"
        + (f"-# ...and {remaining_count} more songs. Use `?queue` to view all pages.\n" if remaining_count > 0 else "")
        + "-# Powered by Kyro Studio"
    )

    if interaction:
        await send_container_response(interaction, container)
    else:
        await send_container_response(channel, container)


class PlaylistSelectMenu(discord.ui.Select):
    """Dropdown menu listing the user's saved playlists."""

    def __init__(self, playlists: list[dict], current_selection: Optional[int] = None) -> None:
        options = []
        for pl in playlists[:25]:  # Discord allows max 25 options
            dur_str = format_duration(int(pl.get("total_duration") or 0))
            t_count = int(pl.get("track_count") or 0)
            pl_id = int(pl["id"])
            options.append(
                discord.SelectOption(
                    label=pl["playlist_name"][:100],
                    description=f"{t_count} songs • {dur_str}"[:100],
                    value=str(pl_id),
                    default=(pl_id == current_selection),
                )
            )

        super().__init__(
            placeholder="Select a playlist to manage or play...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="kyro:playlist:select",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PlaylistHubView = self.view  # type: ignore
        if interaction.user.id != view.author_id:
            c = KyroContainer()
            c.add_section(content="**Access Denied**\n> This playlist hub belongs to someone else.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        selected_id = int(self.values[0])
        view.selected_playlist_id = selected_id
        await view.update_hub_card(interaction)


class PlaylistHubView(discord.ui.View):
    """Components V2 Interactive Hub View with Select Menu and Action Buttons."""

    def __init__(
        self,
        bot: KyroBot,
        cog: Music,
        author_id: int,
        author_name: str,
        playlists: list[dict],
        prefix: str = "?",
    ) -> None:
        super().__init__(timeout=180.0)
        self.bot = bot
        self.cog = cog
        self.author_id = author_id
        self.author_name = author_name
        self.playlists = playlists
        self.prefix = prefix
        self.selected_playlist_id: Optional[int] = int(playlists[0]["id"]) if playlists else None

        # Build Select Menu
        if playlists:
            self.add_item(PlaylistSelectMenu(playlists, self.selected_playlist_id))

        self._update_button_states()

    def _get_selected_pl(self) -> Optional[dict]:
        if not self.selected_playlist_id:
            return None
        for pl in self.playlists:
            if int(pl["id"]) == self.selected_playlist_id:
                return pl
        return None

    def _update_button_states(self) -> None:
        has_sel = self.selected_playlist_id is not None and len(self.playlists) > 0
        self.btn_play.disabled = not has_sel
        self.btn_shuffle.disabled = not has_sel
        self.btn_view.disabled = not has_sel
        self.btn_delete.disabled = not has_sel

    def build_container(self) -> KyroContainer:
        """Construct the Components V2 card for the Playlist Hub."""
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "### Music Playlist Hub\n"
                f"> Personal collections of `{self.author_name}` • Lossless Native Engine"
            )
        )
        container.add_separator(divider=True)

        if not self.playlists:
            container.add_section(
                content=(
                    "**You have no saved playlists yet.**\n"
                    f"> • Use `{self.prefix}like` while a song is playing to save it to **Favorites**.\n"
                    f"> • Use `{self.prefix}playlist add <name> <song>` to create a custom playlist.\n"
                    f"> • Use `{self.prefix}playlist import <name> <Spotify/YouTube URL>` to import albums."
                )
            )
            container.add_separator(divider=True)
            container.add_text("-# Powered by Kyro Studio")
            return container

        selected_pl = self._get_selected_pl()
        if selected_pl:
            dur_str = format_duration(int(selected_pl.get("total_duration") or 0))
            t_count = int(selected_pl.get("track_count") or 0)
            container.add_section(
                content=(
                    f"**Selected Playlist: `{selected_pl['playlist_name']}`**\n"
                    f"> **Total Songs:** `{t_count}` songs\n"
                    f"> **Total Duration:** `{dur_str}`\n"
                    f"> **Curator:** `{self.author_name}`\n\n"
                    f"-# Use the dropdown below to switch playlists, or buttons to play/browse."
                )
            )
        else:
            container.add_section(
                content=(
                    f"**Your Saved Playlists ({len(self.playlists)})**\n"
                    + "\n".join(
                        f"> • **{p['playlist_name']}** (`{p['track_count']} songs` • `{format_duration(int(p['total_duration']))}`)"
                        for p in self.playlists[:8]
                    )
                )
            )

        container.add_separator(divider=True)
        container.add_text(
            f"**Quick Actions:**\n"
            f"> `Play` Start sequential playback • `Shuffle` Randomized queue\n"
            f"> `View Songs` Interactive page browser • `Delete` Remove collection\n"
            f"-# Powered by Kyro Studio"
        )
        return container

    async def update_hub_card(self, interaction: discord.Interaction) -> None:
        """Refresh the container card and dropdown selection on interaction."""
        self._update_button_states()
        # Refresh dropdown default
        for item in self.children:
            if isinstance(item, PlaylistSelectMenu):
                for opt in item.options:
                    opt.default = (opt.value == str(self.selected_playlist_id))

        container = self.build_container()
        await edit_container_response(interaction, container, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            c = KyroContainer()
            c.add_section(content="**Access Denied**\n> This playlist hub belongs to someone else.")
            await send_container_response(interaction, c, ephemeral=True)
            return False
        return True

    @discord.ui.button(
        label="Play",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:playlist:btn_play",
        row=1,
    )
    async def btn_play(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        selected_pl = self._get_selected_pl()
        if not selected_pl or not interaction.guild:
            c = KyroContainer()
            c.add_section(content="**Selection Required**\n> Please select a playlist first.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        db = self.bot.db
        tracks = await db.fetch_all(
            "SELECT title, author, duration, url FROM user_playlist_tracks WHERE playlist_id = $1 ORDER BY id ASC;",
            selected_pl["id"],
        )
        await execute_saved_playlist_playback(
            self.bot,
            self.cog,
            interaction.guild,
            interaction.user,
            interaction.channel,
            selected_pl,
            tracks,
            shuffle=False,
            interaction=interaction,
        )

    @discord.ui.button(
        label="Shuffle Play",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:playlist:btn_shuffle",
        row=1,
    )
    async def btn_shuffle(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        selected_pl = self._get_selected_pl()
        if not selected_pl or not interaction.guild:
            c = KyroContainer()
            c.add_section(content="**Selection Required**\n> Please select a playlist first.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        db = self.bot.db
        tracks = await db.fetch_all(
            "SELECT title, author, duration, url FROM user_playlist_tracks WHERE playlist_id = $1 ORDER BY id ASC;",
            selected_pl["id"],
        )
        await execute_saved_playlist_playback(
            self.bot,
            self.cog,
            interaction.guild,
            interaction.user,
            interaction.channel,
            selected_pl,
            tracks,
            shuffle=True,
            interaction=interaction,
        )

    @discord.ui.button(
        label="View Songs",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:playlist:btn_view",
        row=1,
    )
    async def btn_view(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        selected_pl = self._get_selected_pl()
        if not selected_pl:
            c = KyroContainer()
            c.add_section(content="**Selection Required**\n> Please select a playlist first.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        db = self.bot.db
        tracks = await db.fetch_all(
            "SELECT id, title, author, duration, url FROM user_playlist_tracks WHERE playlist_id = $1 ORDER BY id ASC;",
            selected_pl["id"],
        )

        browse_view = PlaylistBrowseView(
            bot=self.bot,
            cog=self.cog,
            author_id=self.author_id,
            author_name=self.author_name,
            playlist=selected_pl,
            tracks=tracks,
            hub_view=self,
            prefix=self.prefix,
        )
        container = browse_view.build_container()
        await edit_container_response(interaction, container, view=browse_view)

    @discord.ui.button(
        label="Delete",
        style=discord.ButtonStyle.danger,
        custom_id="kyro:playlist:btn_delete",
        row=1,
    )
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        selected_pl = self._get_selected_pl()
        if not selected_pl:
            c = KyroContainer()
            c.add_section(content="**Selection Required**\n> Please select a playlist first.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        confirm_view = PlaylistDeleteConfirmView(
            bot=self.bot,
            cog=self.cog,
            author_id=self.author_id,
            playlist=selected_pl,
            hub_view=self,
        )
        c = KyroContainer(accent_color=None)
        c.add_section(
            content=(
                f"**Confirm Deletion**\n"
                f"> Are you sure you want to delete playlist **`{selected_pl['playlist_name']}`**?\n"
                f"> This will permanently remove all `{selected_pl['track_count']}` saved songs."
            )
        )
        c.add_separator(divider=True)
        c.add_text("-# This action cannot be undone.")
        await edit_container_response(interaction, c, view=confirm_view)


class PlaylistBrowseView(discord.ui.View):
    """Live Paginated Browser for viewing all songs in a playlist with Prev / Next buttons."""

    def __init__(
        self,
        bot: KyroBot,
        cog: Music,
        author_id: int,
        author_name: str,
        playlist: dict,
        tracks: list[dict],
        hub_view: PlaylistHubView,
        prefix: str = "?",
        per_page: int = 15,
    ) -> None:
        super().__init__(timeout=180.0)
        self.bot = bot
        self.cog = cog
        self.author_id = author_id
        self.author_name = author_name
        self.playlist = playlist
        self.tracks = tracks
        self.hub_view = hub_view
        self.prefix = prefix
        self.per_page = per_page
        self.current_page = 1
        self.total_pages = max(1, (len(tracks) + per_page - 1) // per_page)

        self._update_buttons()

    def _update_buttons(self) -> None:
        self.btn_prev.disabled = (self.current_page <= 1)
        self.btn_next.disabled = (self.current_page >= self.total_pages)

    def build_container(self) -> KyroContainer:
        container = KyroContainer(accent_color=None)
        display_name = self.playlist["playlist_name"]
        total_sec = sum(t["duration"] or 0 for t in self.tracks)
        total_dur = format_duration(total_sec)

        start_idx = (self.current_page - 1) * self.per_page
        page_tracks = self.tracks[start_idx : start_idx + self.per_page]

        lines = []
        for i, t in enumerate(page_tracks, start=start_idx + 1):
            dur_str = format_duration(t["duration"] or 0)
            t_url = t.get("url")
            link = f"[{t['title']}]({t_url})" if t_url and str(t_url).startswith("http") else f"`{t['title']}`"
            author = f" • {t['author']}" if t.get("author") and t.get("author") != "Official Artist" else ""
            lines.append(f"> `{i}.` {link}{author} • `{dur_str}`")

        if not lines:
            lines = ["> • This playlist has no songs yet."]

        container.add_section(
            content=(
                f"### Playlist: {display_name}\n"
                f"> **Total Songs:** `{len(self.tracks)}` • **Duration:** `{total_dur}`\n"
                f"> **Page:** `{self.current_page} of {self.total_pages}` • **Curator:** `{self.author_name}`"
            )
        )
        container.add_separator(divider=True)
        container.add_section(content="\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(
            f"> • **Play Collection:** `{self.prefix}playlist play {display_name}`\n"
            f"> • **Remove Song:** `{self.prefix}playlist removetrack {display_name} <#>`\n"
            f"-# Powered by Kyro Studio"
        )
        return container

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            c = KyroContainer()
            c.add_section(content="**Access Denied**\n> This browser belongs to someone else.")
            await send_container_response(interaction, c, ephemeral=True)
            return False
        return True

    @discord.ui.button(
        label="Previous",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:playlist:browse_prev",
    )
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self._update_buttons()
            container = self.build_container()
            await edit_container_response(interaction, container, view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(
        label="Next",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:playlist:browse_next",
    )
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._update_buttons()
            container = self.build_container()
            await edit_container_response(interaction, container, view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(
        label="Back to Hub",
        style=discord.ButtonStyle.primary,
        custom_id="kyro:playlist:browse_back",
    )
    async def btn_back(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        container = self.hub_view.build_container()
        await edit_container_response(interaction, container, view=self.hub_view)


class PlaylistDeleteConfirmView(discord.ui.View):
    """Confirmation View for deleting a user playlist."""

    def __init__(
        self,
        bot: KyroBot,
        cog: Music,
        author_id: int,
        playlist: dict,
        hub_view: PlaylistHubView,
    ) -> None:
        super().__init__(timeout=60.0)
        self.bot = bot
        self.cog = cog
        self.author_id = author_id
        self.playlist = playlist
        self.hub_view = hub_view

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            c = KyroContainer()
            c.add_section(content="**Access Denied**\n> This prompt belongs to someone else.")
            await send_container_response(interaction, c, ephemeral=True)
            return False
        return True

    @discord.ui.button(
        label="Confirm Delete",
        style=discord.ButtonStyle.danger,
        custom_id="kyro:playlist:confirm_delete",
    )
    async def btn_confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        db = self.bot.db
        pl_id = self.playlist["id"]
        pl_name = self.playlist["playlist_name"]

        await db.execute("DELETE FROM user_playlists WHERE id = $1;", pl_id)

        # Refresh user playlists for hub view
        updated_playlists = await db.fetch_all(
            """
            SELECT p.id, p.playlist_name, COUNT(t.id) as track_count, COALESCE(SUM(t.duration), 0) as total_duration
            FROM user_playlists p
            LEFT JOIN user_playlist_tracks t ON p.id = t.playlist_id
            WHERE p.user_id = $1
            GROUP BY p.id, p.playlist_name
            ORDER BY p.created_at DESC;
            """,
            self.author_id,
        )

        self.hub_view.playlists = updated_playlists
        self.hub_view.selected_playlist_id = int(updated_playlists[0]["id"]) if updated_playlists else None

        # Rebuild Hub View children
        self.hub_view.clear_items()
        if updated_playlists:
            self.hub_view.add_item(PlaylistSelectMenu(updated_playlists, self.hub_view.selected_playlist_id))
        self.hub_view.add_item(self.hub_view.btn_play)
        self.hub_view.add_item(self.hub_view.btn_shuffle)
        self.hub_view.add_item(self.hub_view.btn_view)
        self.hub_view.add_item(self.hub_view.btn_delete)
        self.hub_view._update_button_states()

        c = KyroContainer(accent_color=None)
        c.add_section(
            content=(
                f"**Playlist Deleted**\n"
                f"> Playlist **`{pl_name}`** has been permanently removed.\n"
                f"> Returning you to your updated Playlist Hub."
            )
        )
        c.add_separator(divider=True)
        c.add_text("-# Powered by Kyro Studio")
        await edit_container_response(interaction, c, view=self.hub_view)

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:playlist:cancel_delete",
    )
    async def btn_cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        c = self.hub_view.build_container()
        await edit_container_response(interaction, c, view=self.hub_view)
