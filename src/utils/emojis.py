"""
Hertz Discord Bot - Dynamic Application Emoji Registry
Automatically caches all uploaded Discord Application Emojis and provides
easy resolution for in-text mentions and Discord UI dropdown options.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
import discord

if TYPE_CHECKING:
    from src.core.bot import HertzBot

logger = logging.getLogger("Hertz.Emojis")


class EmojiRegistry:
    """Central registry mapping emoji names to discord.Emoji objects."""

    def __init__(self, bot: HertzBot) -> None:
        self.bot = bot
        self._emojis: dict[str, discord.Emoji] = {}

    async def load(self) -> None:
        """Fetch all application emojis from Discord API and cache them."""
        try:
            emojis = await self.bot.fetch_application_emojis()
            self._emojis = {e.name.lower(): e for e in emojis}
            logger.info(f"Successfully cached {len(self._emojis)} custom Application Emoji(s).")
        except Exception as e:
            logger.warning(f"Failed to fetch application emojis: {e}")

    def get(self, name: str, fallback: str = "") -> str:
        """
        Get custom emoji string (e.g. '<:icon_bot:123456789>') by name.
        If not found, returns the provided fallback.
        """
        emoji = self._emojis.get(name.lower())
        if emoji:
            return str(emoji)
        return fallback

    def get_select_emoji(self, name: str, fallback_unicode: str = "📁") -> dict[str, Any]:
        """
        Get emoji dictionary structure suitable for Discord Select Menu options.
        Custom emoji requires {'id': int, 'name': str}.
        """
        emoji = self._emojis.get(name.lower())
        if emoji:
            return {
                "id": str(emoji.id),
                "name": emoji.name,
                "animated": emoji.animated,
            }
        return {"name": fallback_unicode}
