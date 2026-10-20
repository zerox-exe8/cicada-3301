import asyncio
import time
import unittest
from storage.cache import CacheManager
from storage.db import DatabaseManager

class TestStorage(unittest.IsolatedAsyncioTestCase):

    async def test_cache_l1_operations(self):
        cache = CacheManager()
        await cache.initialize()

        # Set and Get
        await cache.set("user:123:session", {"role": "admin"}, ttl_seconds=2)
        val = await cache.get("user:123:session")
        self.assertIsNotNone(val)
        self.assertEqual(val["role"], "admin")

        # Rate Limit / Increment
        count1 = await cache.increment("ratelimit:ip_1.2.3.4", amount=1)
        count2 = await cache.increment("ratelimit:ip_1.2.3.4", amount=1)
        self.assertEqual(count1, 1)
        self.assertEqual(count2, 2)

        # Delete
        await cache.delete("user:123:session")
        self.assertIsNone(await cache.get("user:123:session"))

        await cache.close()

    async def test_db_offline_safety(self):
        """Verify DB manager gracefully handles connection attempts without crashing."""
        db = DatabaseManager()
        # Connect will log info and return False when local postgres is not running
        is_connected = await db.connect()
        self.assertIsInstance(is_connected, bool)
        # Execute query gracefully returns None
        result = await db.execute("SELECT 1;")
        self.assertIsNone(result)
        await db.disconnect()

if __name__ == "__main__":
    unittest.main()
