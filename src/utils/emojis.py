"""
Cicada 3301 Discord Bot - Dynamic Application Emoji Registry
Automatically caches all uploaded Discord Application Emojis and provides
easy resolution for in-text mentions and Discord UI dropdown options.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
import discord

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("Cicada.Emojis")


class EmojiRegistry:
    """Central registry mapping emoji names to discord.Emoji objects."""

    def __init__(self, bot: CicadaBot) -> None:
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

    async def sync_from_assets(self) -> tuple[int, int]:
        """
        Scan assets/emoji and assets/emoji2 and upload any missing application emojis to Discord.
        Returns (uploaded_count, total_cached).
        """
        from pathlib import Path
        import re

        await self.load()
        uploaded = 0

        asset_dirs = [
            Path(__file__).resolve().parent.parent.parent / "assets" / "emoji",
            Path(__file__).resolve().parent.parent.parent / "assets" / "emoji2",
        ]

        for adir in asset_dirs:
            if not adir.exists():
                continue
            for img_file in adir.glob("*.png"):
                # Clean name: alphanumeric + underscores only, 2-32 chars
                raw_name = img_file.stem.lower()
                clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", raw_name)
                clean_name = clean_name.strip("_")[:32]
                if len(clean_name) < 2:
                    continue

                if clean_name not in self._emojis and raw_name not in self._emojis:
                    try:
                        with open(img_file, "rb") as f:
                            img_data = f.read()
                        new_emoji = await self.bot.create_application_emoji(
                            name=clean_name,
                            image=img_data,
                        )
                        self._emojis[clean_name] = new_emoji
                        self._emojis[raw_name] = new_emoji
                        uploaded += 1
                        logger.info(f"Uploaded application emoji: {clean_name}")
                    except Exception as e:
                        logger.debug(f"Could not upload emoji {clean_name}: {e}")

        return uploaded, len(self._emojis)

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
        Custom emoji requires {'id': str, 'name': str}.
        """
        emoji = self._emojis.get(name.lower())
        if emoji:
            return {
                "id": str(emoji.id),
                "name": emoji.name,
                "animated": emoji.animated,
            }
        return {"name": fallback_unicode}

