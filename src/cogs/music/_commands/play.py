"""
Kyro Discord Bot - Play Command Handler (Lavalink V4)
Clean single-message dispatcher with zero webhook spam and instant playback.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
import wavelink

from src.cogs.music._player import KyroPlayer, shorten_artist
from src.cogs.music._resolver import MusicResolver
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext

logger = logging.getLogger("Kyro.Music.Cmd.Play")


async def handle_play(ctx: CustomContext, controller: MusicController, query: str) -> None:
    """Execute the play command cleanly without duplicate embeds or webhooks."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send_warning("You must be connected to a Voice Channel to play music.")
        return

    e_reg = ctx.bot.custom_emojis
    user_channel = ctx.author.voice.channel
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore

    # 1. Connect or Move Voice Client via KyroPlayer
    if not player or not player.connected:
        try:
            player = await user_channel.connect(cls=KyroPlayer, self_deaf=True, timeout=20.0, reconnect=True)
        except Exception as e:
            await ctx.send_error(f"Could not connect to voice channel: `{e}`")
            return
    elif player.channel != user_channel:
        await player.move_to(user_channel)

    player.home_channel = ctx.channel

    # 2. Resolve Track with Multi-Tier Anti-Block Fallback (using discord typing instead of extra message)
    async with ctx.typing():
        try:
            result = await MusicResolver.resolve(query, requester=ctx.author.display_name)
        except Exception as ex:
            logger.error(f"Resolver error for '{query}': {ex}", exc_info=ex)
            await ctx.send_error(f"Failed to search for **{query}**: `{ex}`")
            return

    if not result:
        await ctx.send_warning(f"No results found for `{query}`.")
        return

    # 3. Handle Playlist vs Single Track
    if isinstance(result, wavelink.Playlist):
        added_count = 0
        for track in result.tracks:
            track.extras = wavelink.ExtrasNamespace(requester=ctx.author.display_name)
            player.queue.put(track)
            added_count += 1

        if not player.playing and not player.queue.is_empty:
            await player.play(player.queue.get())

        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))
        playlist_container = KyroContainer(accent_color=None)
        playlist_container.add_section(
            content=(
                f"**Queued Playlist: {result.name or 'Collection'}**\n"
                f"> **Tracks Loaded:** `{added_count}`\n"
                f"> **Requested By:** `{ctx.author.display_name}`"
            )
        )
        playlist_container.add_separator(divider=True)
        playlist_container.add_text(f"{dot} **Queue Status:** `{len(player.queue)}` tracks waiting.")
        playlist_container.add_separator(divider=True)
        playlist_container.add_text("-# Kyro Music Engine • Lavalink V4")
        await send_container_response(ctx, playlist_container)
        return

    track: wavelink.Playable = result

    # 4. Play or Queue Track
    if not player.playing:
        # Playing track triggers on_wavelink_track_start, which renders the single Now Playing card
        await player.play(track)
    else:
        player.queue.put(track)
        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))
        queued_icon = e_reg.get("queue", "")
        queued_prefix = f"{queued_icon} " if queued_icon else ""

        dur_s = (track.length // 1000) if track.length else 0
        dur_str = f"{dur_s // 60:02d}:{dur_s % 60:02d}" if dur_s > 0 else "Live"
        short_artist_name = shorten_artist(track.author or "Official Artist")

        queued_container = KyroContainer(accent_color=None)
        queued_container.add_section(
            content=(
                f"**{queued_prefix}Track Queued**\n"
                f"> **Title:** [{track.title}]({track.uri})\n"
                f"> **Artist:** `{short_artist_name}`\n"
                f"> **Duration:** `{dur_str}`"
            ),
            accessory={"type": 11, "media": {"url": track.artwork}} if track.artwork else None,
        )
        queued_container.add_separator(divider=True)
        queued_container.add_text(
            f"{dot} **Position in Queue:** `#{len(player.queue)}`\n"
            f"{dot} **Requested By:** {ctx.author.display_name}"
        )
        queued_container.add_separator(divider=True)
        queued_container.add_text(f"-# Kyro Music Engine • Lavalink V4")
        await send_container_response(ctx, queued_container)
