from __future__ import annotations

import logging
from typing import Any, Optional
from src.database.base import BaseDatabase

logger = logging.getLogger("Kyro.Repositories.Base")


class BaseRepository:
    """Enterprise-grade Base Repository encapsulating database queries."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db

    async def execute(self, query: str, *args: Any) -> None:
        """Execute a write/update command with self-healing error logging."""
        try:
            await self.db.execute(query, *args)
        except Exception as e:
            logger.error(f"Repository write error: {e} | Query: {query}", exc_info=e)
            raise

    async def fetch_one(self, query: str, *args: Any) -> Optional[dict[str, Any]]:
        """Fetch a single record as a dict."""
        try:
            return await self.db.fetch_one(query, *args)
        except Exception as e:
            logger.error(f"Repository fetch_one error: {e} | Query: {query}", exc_info=e)
            raise

    async def fetch_all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Fetch all matching records as a list of dicts."""
        try:
            return await self.db.fetch_all(query, *args)
        except Exception as e:
            logger.error(f"Repository fetch_all error: {e} | Query: {query}", exc_info=e)
            raise

    async def fetch_val(self, query: str, *args: Any) -> Any:
        """Fetch a single scalar value from the first column of the first row."""
        try:
            row = await self.db.fetch_one(query, *args)
            if row:
                return next(iter(row.values()))
            return None
        except Exception as e:
            logger.error(f"Repository fetch_val error: {e} | Query: {query}", exc_info=e)
            raise
