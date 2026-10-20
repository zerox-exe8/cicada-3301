import logging
from typing import Any, Optional, List, Dict
import asyncpg
from config.settings import settings

logger = logging.getLogger("kyro.engine.storage.db")

class DatabaseManager:
    """PostgreSQL Connection Pool Manager designed for PgBouncer / Direct scale."""

    def __init__(self) -> None:
        self._pool: Optional[asyncpg.Pool] = None
        self._is_connected: bool = False

    async def connect(self) -> bool:
        """Establish asyncpg connection pool."""
        try:
            self._pool = await asyncpg.create_pool(
                dsn=settings.POSTGRES_DSN,
                min_size=settings.DB_POOL_MIN_SIZE,
                max_size=settings.DB_POOL_MAX_SIZE,
                command_timeout=10.0
            )
            self._is_connected = True
            logger.info("⚡ PostgreSQL connection pool established successfully.")
            return True
        except Exception as e:
            self._is_connected = False
            logger.info("ℹ️ PostgreSQL offline (%s) — Engine running in memory-only mode.", e)
            return False

    async def disconnect(self) -> None:
        if self._pool and self._is_connected:
            await self._pool.close()
            self._is_connected = False
            logger.info("PostgreSQL connection pool closed.")

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    async def execute(self, query: str, *args: Any) -> Optional[str]:
        if not self._is_connected or not self._pool:
            logger.debug("Database not connected; skipping query: %s", query[:50])
            return None
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch_one(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        if not self._is_connected or not self._pool:
            return None
        async with self._pool.acquire() as conn:
            record = await conn.fetchrow(query, *args)
            return dict(record) if record else None

    async def fetch_all(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        if not self._is_connected or not self._pool:
            return []
        async with self._pool.acquire() as conn:
            records = await conn.fetch(query, *args)
            return [dict(r) for r in records]
