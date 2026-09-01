"""
Kyro Discord Bot - Native Music Controller Manager
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Optional
import discord

from src.cogs.music._player import GuildPlayer

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Music.Controller")


class MusicController:
    """Manages active GuildPlayer instances across all Discord servers."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.players: Dict[int, GuildPlayer] = {}

    def get_player(self, guild_id: int) -> Optional[GuildPlayer]:
        return self.players.get(guild_id)

    def get_or_create_player(self, guild: discord.Guild) -> GuildPlayer:
        if guild.id not in self.players:
            self.players[guild.id] = GuildPlayer(self.bot, guild)
        return self.players[guild.id]

    async def remove_player(self, guild_id: int) -> None:
        if guild_id in self.players:
            player = self.players.pop(guild_id)
            await player.stop()
