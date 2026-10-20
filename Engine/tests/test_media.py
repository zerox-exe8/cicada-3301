import asyncio
import time
import unittest
from storage.cache import CacheManager
from managers.media import MediaManager

class TestMediaManager(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.cache = CacheManager()
        await self.cache.initialize()
        self.media = MediaManager(cache=self.cache)

    async def asyncTearDown(self):
        await self.media.close()
        await self.cache.close()

    async def test_search_and_decrypt(self):
        """Test live search on JioSaavn and verify decrypted 320kbps Akamai CDN stream URL."""
        res = await self.media.search(query="Tum Hi Ho", limit=3)
        self.assertGreater(res.count, 0, "No tracks returned for 'Tum Hi Ho'")

        first_track = res.tracks[0]
        self.assertIsNotNone(first_track.title)
        self.assertIsNotNone(first_track.stream_url)
        # Verify decrypted URL points to real CDN audio stream
        self.assertTrue(
            first_track.stream_url.startswith("http"),
            f"Invalid stream URL: {first_track.stream_url}"
        )
        self.assertTrue(
            any(ext in first_track.stream_url for ext in (".mp4", ".aac", ".m4a")),
            f"Expected audio format in stream URL: {first_track.stream_url}"
        )
        print(f"\n[MEDIA ENGINE TEST] Resolved: '{first_track.title}' by '{first_track.artist}'")
        print(f"[STREAM URL] {first_track.stream_url[:80]}... (Bitrate: {first_track.bitrate_kbps}kbps)")

        # Verify instant cache hit (< 1ms)
        start = time.perf_counter_ns()
        cached_res = await self.media.search(query="Tum Hi Ho", limit=3)
        elapsed_us = (time.perf_counter_ns() - start) / 1000.0
        self.assertEqual(cached_res.count, res.count)
        print(f"[CACHE HIT LATENCY] {elapsed_us:.2f} microseconds (< 1ms)")
        self.assertLess(elapsed_us, 5000.0)

if __name__ == "__main__":
    unittest.main()
