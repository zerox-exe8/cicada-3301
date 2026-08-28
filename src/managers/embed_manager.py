"""
Cicada 3301 Discord Bot - Custom Embed & Container Manager
Manages storing, retrieving, and serializing Components V2 Container templates per guild,
along with live persistent interactive card state for dropdown page switchers.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Cicada.EmbedManager")


class EmbedManager:
    """Manages custom server Components V2 Container templates and interactive cards."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        # In-memory LRU cache: (guild_id, message_id) -> payload dict
        self._card_cache: dict[tuple[int, int], dict[str, Any]] = {}
        # In-memory template cache: (guild_id, name) -> payload dict
        self._template_cache: dict[tuple[int, str], dict[str, Any]] = {}

    async def save_template(
        self,
        guild_id: int,
        name: str,
        payload: dict[str, Any],
        created_by: int,
    ) -> bool:
        """Save or update a container embed template in database."""
        clean_name = name.strip().lower()
        payload_str = json.dumps(payload)

        query = """
        INSERT INTO server_embeds (guild_id, embed_name, container_payload, created_by)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (guild_id, embed_name)
        DO UPDATE SET
            container_payload = EXCLUDED.container_payload,
            created_by = EXCLUDED.created_by,
            created_at = CURRENT_TIMESTAMP;
        """
        try:
            await self.db.execute(query, guild_id, clean_name, payload_str, created_by)
            self._template_cache[(guild_id, clean_name)] = payload
            logger.info(f"Saved custom embed '{clean_name}' for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save custom embed template '{clean_name}': {e}")
            return False

    async def get_template(self, guild_id: int, name: str, force_refresh: bool = False) -> dict[str, Any] | None:
        """Retrieve a saved container embed payload by name with optional cache refresh."""
        clean_name = name.strip().lower()
        cache_key = (guild_id, clean_name)
        if not force_refresh and cache_key in self._template_cache:
            return self._template_cache[cache_key]

        query = "SELECT container_payload FROM server_embeds WHERE guild_id = ? AND embed_name = ?;"
        row = await self.db.fetch_one(query, guild_id, clean_name)
        if row and row.get("container_payload"):
            try:
                data = row["container_payload"]
                parsed = json.loads(data) if isinstance(data, str) else data
                self._template_cache[cache_key] = parsed
                return parsed
            except Exception as e:
                logger.error(f"Failed to parse container payload for '{clean_name}': {e}")
                return None
        return None

    async def list_templates(self, guild_id: int) -> list[dict[str, Any]]:
        """List all saved templates for a guild."""
        query = """
        SELECT embed_name, created_by, created_at
        FROM server_embeds
        WHERE guild_id = ?
        ORDER BY created_at DESC;
        """
        return await self.db.fetch_all(query, guild_id)

    async def delete_template(self, guild_id: int, name: str) -> bool:
        """Delete a saved container template."""
        clean_name = name.strip().lower()
        query = "DELETE FROM server_embeds WHERE guild_id = ? AND embed_name = ?;"
        try:
            await self.db.execute(query, guild_id, clean_name)
            self._template_cache.pop((guild_id, clean_name), None)
            logger.info(f"Deleted custom embed '{clean_name}' for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete custom embed template '{clean_name}': {e}")
            return False

    # ─── Live Interactive Cards (Dropdown Page Switchers) ────────────────────

    async def record_interactive_card(
        self,
        guild_id: int,
        message_id: int,
        template_name: str | None,
        payload: dict[str, Any],
    ) -> bool:
        """Store posted interactive card data for persistent dropdown page switching."""
        payload_str = json.dumps(payload)
        self._card_cache[(guild_id, message_id)] = payload

        # Keep in-memory cache bounded
        if len(self._card_cache) > 2000:
            oldest_key = next(iter(self._card_cache))
            self._card_cache.pop(oldest_key, None)

        query = """
        INSERT INTO interactive_cards (guild_id, message_id, template_name, card_payload)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (guild_id, message_id)
        DO UPDATE SET
            template_name = EXCLUDED.template_name,
            card_payload = EXCLUDED.card_payload,
            created_at = CURRENT_TIMESTAMP;
        """
        try:
            await self.db.execute(query, guild_id, message_id, template_name, payload_str)
            return True
        except Exception as e:
            logger.warning(f"Failed to persist interactive card state: {e}")
            return False

    async def get_interactive_card(
        self,
        guild_id: int,
        message_id: int,
    ) -> dict[str, Any] | None:
        """Fetch interactive card payload for a message (from RAM cache or DB)."""
        cache_key = (guild_id, message_id)
        if cache_key in self._card_cache:
            return self._card_cache[cache_key]

        query = "SELECT card_payload FROM interactive_cards WHERE guild_id = ? AND message_id = ?;"
        row = await self.db.fetch_one(query, guild_id, message_id)
        if row and row.get("card_payload"):
            try:
                data = row["card_payload"]
                parsed = json.loads(data) if isinstance(data, str) else data
                self._card_cache[cache_key] = parsed
                return parsed
            except Exception as e:
                logger.error(f"Failed to parse interactive card payload: {e}")
                return None
        return None
