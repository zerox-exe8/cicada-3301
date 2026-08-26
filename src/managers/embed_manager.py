"""
Cicada 3301 Discord Bot - Custom Embed & Container Manager
Manages storing, retrieving, and serializing Components V2 Container templates per guild.
"""

from __future__ import annotations

import json
import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Cicada.EmbedManager")


class EmbedManager:
    """Manages custom server Components V2 Container templates."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db

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
            logger.info(f"Saved custom embed '{clean_name}' for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save custom embed template '{clean_name}': {e}")
            return False

    async def get_template(self, guild_id: int, name: str) -> dict[str, Any] | None:
        """Retrieve a saved container embed payload by name."""
        clean_name = name.strip().lower()
        query = "SELECT container_payload FROM server_embeds WHERE guild_id = ? AND embed_name = ?;"
        row = await self.db.fetch_one(query, guild_id, clean_name)
        if row and row.get("container_payload"):
            try:
                data = row["container_payload"]
                return json.loads(data) if isinstance(data, str) else data
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
            logger.info(f"Deleted custom embed '{clean_name}' for guild {guild_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete custom embed template '{clean_name}': {e}")
            return False
