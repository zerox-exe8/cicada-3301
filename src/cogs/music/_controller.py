"""
Kyro Discord Bot - Music Controller
High-Performance Lavalink V4 Audio Controller with Components V2 Player Cards & Analytics.
"""

from __future__ import annotations

import html
import logging
import re
from typing import TYPE_CHECKING, Optional

import discord
import wavelink

from src.cogs.music._analytics import MusicAnalytics
from src.cogs.music._player import KyroPlayer, shorten_artist
from src.utils.containers import KyroContainer

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Music.Controller")


class MusicController:
    """Controller bridging KyroBot, KyroPlayer, and Music Analytics."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.analytics = MusicAnalytics(bot)

    def get_player(self, guild: Optional[discord.Guild]) -> Optional[KyroPlayer]:
        """Fetch active KyroPlayer for a guild."""
        if not guild:
            return None
        if isinstance(guild.voice_client, wavelink.Player):
            return guild.voice_client  # type: ignore
        return None

    def build_now_playing_container(
        self,
        track: wavelink.Playable,
        guild_id: int,
        channel_name: Optional[str] = None,
        requester: Optional[str] = None,
    ) -> KyroContainer:
        """Create a compact, signature Components V2 Type 17 Container card."""
        guild = self.bot.get_guild(guild_id)
        player = self.get_player(guild)
        if player:
            return player.build_now_playing_container(track, requester=requester)

        # Fallback if player not found
        e_reg = self.bot.custom_emojis
        music_playing = e_reg.get("music_playing", "")
        play_prefix = f"{music_playing} " if music_playing else ""
        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))

        duration_ms = track.length if track.length else 0
        dur_s = duration_ms // 1000
        dur_str = f"{dur_s // 60:02d}:{dur_s % 60:02d}" if dur_s > 0 else "Live"
        short_artist_name = shorten_artist(track.author or "Official Artist")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{play_prefix}Now Playing Studio Master**\n"
                f"> **Title:** [{track.title}]({track.uri})\n"
                f"> **Artist:** `{short_artist_name}`\n"
                f"> **Duration:** `{dur_str}`"
            ),
            accessory={"type": 11, "media": {"url": track.artwork}} if track.artwork else None,
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Channel:** `{channel_name or 'Voice'}` • **Bitrate:** `320kbps CD Master`\n"
            f"{dot} **Requested By:** {requester or 'User'}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Kyro Studio Engine • Lavalink V4 Zero-Lag Stream")
        return container
