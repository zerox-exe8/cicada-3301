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
            if not self.bot.application_id:
                try:
                    app_info = await self.bot.application_info()
                    self.bot.application_id = app_info.id
                except Exception:
                    pass
            if self.bot.application_id:
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

        try:
            if not self.bot.application_id:
                app_info = await self.bot.application_info()
                self.bot.application_id = app_info.id
        except Exception as e:
            logger.debug(f"Could not resolve application info: {e}")

        await self.load()
        uploaded = 0

        asset_dirs = [
            Path(__file__).resolve().parent.parent.parent / "assets" / "music",
            Path(__file__).resolve().parent.parent.parent / "assets" / "emoji",
            Path(__file__).resolve().parent.parent.parent / "assets" / "emoji2",
        ]

        for adir in asset_dirs:
            if not adir.exists():
                continue
            for pattern in ("*.png", "*.gif"):
                for img_file in sorted(adir.glob(pattern)):
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
        name_clean = name.lower().strip(":")
        emoji = self._emojis.get(name_clean)
        if not emoji and hasattr(self.bot, "emojis"):
            emoji = discord.utils.get(self.bot.emojis, name=name_clean)

        # Smart alias fallbacks for arrow, music, and common icons
        if not emoji:
            alias_map = {
                "icons_arrow": ["icons_rightarrow", "heart_dot", "icon_arrow_left"],
                "icons_rightarrow": ["icons_arrow", "heart_dot"],
                "icon_arrow_left": ["icons_leftarrow"],
                "icons_leftarrow": ["icon_arrow_left"],
                "heart_dot": ["icons_rightarrow", "icons_arrow"],
                "ticket_nox": ["icon_ticket", "ticket_support"],
                "icon_ticket": ["ticket_nox", "ticket_support"],
                "icons_locked": ["icon_lock", "icon_locked"],
                "icon_lock": ["icons_locked", "icon_locked"],
                "icons_staff": ["icon_mod", "icon_support", "icons_supportteam"],
                "icons_file": ["icons_files", "icons_todolist", "icon_logging"],
                # Music Emojis
                "music_playing": ["music_music", "lbop_music", "icon_music", "a_musical_notes"],
                "a_musical_notes": ["music_playing", "music_music", "lbop_music", "icon_music"],
                "paused": ["icons_pause", "icon_clear"],
                "icons_pause": ["paused"],
                "skip": ["icons_rightarrow", "icon_arrow_left", "icons_arrow"],
                "queue": ["icons_list", "icon_playlist", "icons_todolist"],
                "icons_stop_button": ["icon_delete", "icon_x", "icons_wrong"],
                "icons_loop": ["ub_refresh_icon", "icons_update"],
                "icons_shuffle": ["icons_magicwand", "icons_splash"],
                "volume_up": ["volume_down", "icon_music"],
                "volume_down": ["room_icon_mute", "volume_up"],
                "room_icon_mute": ["volume_down", "icons_micmute"],
            }
            for alias in alias_map.get(name_clean, []):
                emoji = self._emojis.get(alias)
                if not emoji and hasattr(self.bot, "emojis"):
                    emoji = discord.utils.get(self.bot.emojis, name=alias)
                if emoji:
                    break

        if emoji:
            return str(emoji)
        return fallback

    def get_emoji_obj(self, name: str) -> discord.Emoji | discord.PartialEmoji | str | None:
        """
        Get a discord.Emoji or discord.PartialEmoji object for UI buttons or components.
        """
        name_clean = name.lower().strip(":")
        emoji = self._emojis.get(name_clean)
        if not emoji and hasattr(self.bot, "emojis"):
            emoji = discord.utils.get(self.bot.emojis, name=name_clean)

        if not emoji:
            alias_map = {
                "icons_arrow": ["icons_rightarrow", "heart_dot"],
                "icons_rightarrow": ["icons_arrow", "heart_dot"],
                "icon_arrow_left": ["icons_leftarrow"],
                "icons_leftarrow": ["icon_arrow_left"],
                "heart_dot": ["icons_rightarrow", "icons_arrow"],
                "ticket_nox": ["icon_ticket", "ticket_support"],
                "icon_ticket": ["ticket_nox", "ticket_support"],
                "icons_locked": ["icon_lock", "icon_locked"],
                "icon_lock": ["icons_locked", "icon_locked"],
                "icons_staff": ["icon_mod", "icon_support", "icons_supportteam"],
                "icons_file": ["icons_files", "icons_todolist", "icon_logging"],
                # Music Emojis
                "music_playing": ["music_music", "lbop_music", "icon_music", "a_musical_notes"],
                "a_musical_notes": ["music_playing", "music_music", "lbop_music", "icon_music"],
                "paused": ["icons_pause", "icon_clear"],
                "icons_pause": ["paused"],
                "skip": ["icons_rightarrow", "icon_arrow_left", "icons_arrow"],
                "queue": ["icons_list", "icon_playlist", "icons_todolist"],
                "icons_stop_button": ["icon_delete", "icon_x", "icons_wrong"],
                "icons_loop": ["ub_refresh_icon", "icons_update"],
                "icons_shuffle": ["icons_magicwand", "icons_splash"],
                "volume_up": ["volume_down", "icon_music"],
                "volume_down": ["room_icon_mute", "volume_up"],
                "room_icon_mute": ["volume_down", "icons_micmute"],
            }
            for alias in alias_map.get(name_clean, []):
                emoji = self._emojis.get(alias)
                if not emoji and hasattr(self.bot, "emojis"):
                    emoji = discord.utils.get(self.bot.emojis, name=alias)
                if emoji:
                    break

        return emoji

    def get_select_emoji(self, name: str, fallback_unicode: str | None = None) -> dict[str, Any] | None:
        """
        Get emoji dictionary structure suitable for Discord Select Menu options and components.
        Custom emoji requires {'id': str, 'name': str}.
        """
        name_clean = name.lower().strip(":")
        emoji = self._emojis.get(name_clean)
        if not emoji and hasattr(self.bot, "emojis"):
            emoji = discord.utils.get(self.bot.emojis, name=name_clean)

        if not emoji:
            alias_map = {
                "ticket_nox": ["icon_ticket", "ticket_support"],
                "icon_ticket": ["ticket_nox", "ticket_support"],
                "icons_locked": ["icon_lock", "icon_locked"],
                "icon_lock": ["icons_locked", "icon_locked"],
                "icons_staff": ["icon_mod", "icon_support", "icons_supportteam"],
                "icons_file": ["icons_files", "icons_todolist", "icon_logging"],
            }
            for alias in alias_map.get(name_clean, []):
                emoji = self._emojis.get(alias)
                if not emoji and hasattr(self.bot, "emojis"):
                    emoji = discord.utils.get(self.bot.emojis, name=alias)
                if emoji:
                    break

        if emoji:
            return {
                "id": str(emoji.id),
                "name": emoji.name,
                "animated": emoji.animated,
            }
        if fallback_unicode:
            return {"name": fallback_unicode}
        return None


