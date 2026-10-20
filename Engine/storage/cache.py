import time
import json
import logging
from typing import Any, Optional, Dict
from config.settings import settings

logger = logging.getLogger("kyro.engine.storage.cache")

class CacheManager:
    """Two-tier High Performance Cache:
    L1: Local In-Memory Dict with Microsecond TTL (always available).
    L2: DragonflyDB / Redis Cluster (async, distributed).
    """

    def __init__(self) -> None:
        self._l1_store: Dict[str, tuple[Any, float]] = {}  # key -> (value, expire_at)
        self._redis_client: Optional[Any] = None
        self._is_redis_connected: bool = False

    async def initialize(self) -> None:
        """Attempt to connect to L2 Redis/DragonflyDB cluster."""
        try:
            import redis.asyncio as aioredis
            self._redis_client = aioredis.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=True
            )
            await self._redis_client.ping()
            self._is_redis_connected = True
            logger.info("⚡ L2 Redis/Dragonfly cache connected successfully.")
        except Exception as e:
            self._is_redis_connected = False
            logger.info("ℹ️ L2 Redis offline (%s) — Engine running on ultra-fast L1 In-Memory Cache.", e)

    async def close(self) -> None:
        if self._redis_client and self._is_redis_connected:
            await self._redis_client.close()
            self._is_redis_connected = False

    async def get(self, key: str) -> Optional[Any]:
        """Fetch from L1 first (<1us). If missing, fetch from L2 and populate L1."""
        now = time.time()

        # 1. Check L1 Cache
        if key in self._l1_store:
            val, expire_at = self._l1_store[key]
            if expire_at > now:
                return val
            else:
                del self._l1_store[key]

        # 2. Check L2 Redis
        if self._is_redis_connected and self._redis_client:
            try:
                raw_val = await self._redis_client.get(key)
                if raw_val is not None:
                    try:
                        val = json.loads(raw_val)
                    except (json.JSONDecodeError, TypeError):
                        val = raw_val
                    # Populate L1 for 30s to avoid repeated network hops
                    self._l1_store[key] = (val, now + 30.0)
                    return val
            except Exception as e:
                logger.debug("L2 cache read error for key %s: %s", key, e)

        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set key in both L1 and L2."""
        now = time.time()
        self._l1_store[key] = (value, now + ttl_seconds)

        if self._is_redis_connected and self._redis_client:
            try:
                payload = json.dumps(value) if not isinstance(value, (str, int, float, bool)) else value
                await self._redis_client.set(key, payload, ex=ttl_seconds)
            except Exception as e:
                logger.debug("L2 cache write error for key %s: %s", key, e)

    async def delete(self, key: str) -> None:
        self._l1_store.pop(key, None)
        if self._is_redis_connected and self._redis_client:
            try:
                await self._redis_client.delete(key)
            except Exception as e:
                logger.debug("L2 cache delete error for key %s: %s", key, e)

    async def increment(self, key: str, amount: int = 1, ttl_seconds: int = 60) -> int:
        """Atomic rate-limit increment."""
        if self._is_redis_connected and self._redis_client:
            try:
                val = await self._redis_client.incrby(key, amount)
                if val == amount:
                    await self._redis_client.expire(key, ttl_seconds)
                return val
            except Exception as e:
                logger.debug("L2 increment failed, falling back to L1: %s", e)

        # L1 Fallback
        now = time.time()
        current_val, exp = self._l1_store.get(key, (0, now + ttl_seconds))
        if exp <= now:
            current_val = 0
            exp = now + ttl_seconds
        new_val = current_val + amount
        self._l1_store[key] = (new_val, exp)
        return new_val
