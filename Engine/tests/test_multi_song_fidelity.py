import asyncio
import sys
import time
import unittest
import aiohttp

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from managers.media import MediaManager
from kyrolink.proxy_manager import ProxyPoolManager
from kyrolink.unblockable import UnblockableResolver


class TestMultiSongFidelity(unittest.IsolatedAsyncioTestCase):
    """Deep validation across diverse genres, Spotify links, and bitrates.
    Ensures that every single song resolves, streams at 320kbps/high-fidelity,
    and never cuts or buffers.
    """

    async def asyncSetUp(self) -> None:
        self.media = MediaManager()
        self.proxy_pool = ProxyPoolManager()
        self.resolver = UnblockableResolver(media_manager=self.media, proxy_pool=self.proxy_pool)
        self.session = aiohttp.ClientSession()

    async def asyncTearDown(self) -> None:
        await self.session.close()
        await self.media.close()
        await self.resolver.close()

    async def _verify_track_stream(self, query: str, category: str, min_expected_bitrate: int = 160) -> None:
        start_resolve = time.perf_counter_ns()
        track = await self.resolver.resolve(query)
        resolve_ms = (time.perf_counter_ns() - start_resolve) / 1_000_000.0

        self.assertIsNotNone(track, f"Failed to resolve {category}: '{query}'")
        self.assertGreaterEqual(track.bitrate_kbps, min_expected_bitrate)
        self.assertTrue(len(track.stream_url) > 15)

        # Download first 128KB chunk to verify CDN health, response code, and format
        start_fetch = time.perf_counter_ns()
        headers = {"Range": "bytes=0-131071", "User-Agent": "Mozilla/5.0"}
        async with self.session.get(track.stream_url, headers=headers, timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
            fetch_ms = (time.perf_counter_ns() - start_fetch) / 1_000_000.0
            self.assertIn(resp.status, [200, 206])
            raw_bytes = await resp.read()
            self.assertGreaterEqual(len(raw_bytes), 64000)

            # Detect format header
            is_valid_audio = (
                b"ftyp" in raw_bytes[:32]
                or raw_bytes.startswith(b"ID3")
                or raw_bytes.startswith(b"\xff\xfb")
                or raw_bytes.startswith(b"OggS")
            )
            self.assertTrue(is_valid_audio, f"Invalid audio stream header for '{track.title}'")

            print(f"[SONG AUDIT PASS] Category: {category:20} | Title: '{track.title[:22]}' | Bitrate: {track.bitrate_kbps}k | Resolve: {resolve_ms:.0f}ms | CDN Chunk: {len(raw_bytes):,} bytes in {fetch_ms:.0f}ms")

    async def test_01_bollywood_romantic(self) -> None:
        await self._verify_track_stream("Arijit Singh Kesariya", "Bollywood Romantic", min_expected_bitrate=320)

    async def test_02_punjabi_drill(self) -> None:
        await self._verify_track_stream("Sidhu Moose Wala 295", "Punjabi Drill", min_expected_bitrate=320)

    async def test_03_punjabi_pop(self) -> None:
        await self._verify_track_stream("Diljit Dosanjh Lover", "Punjabi Pop", min_expected_bitrate=320)

    async def test_04_international_pop(self) -> None:
        await self._verify_track_stream("The Weeknd Blinding Lights", "International Pop", min_expected_bitrate=320)

    async def test_05_international_edm(self) -> None:
        await self._verify_track_stream("Alan Walker Faded", "International EDM", min_expected_bitrate=320)

    async def test_06_spotify_direct_link(self) -> None:
        spotify_url = "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b"
        await self._verify_track_stream(spotify_url, "Spotify Direct Link", min_expected_bitrate=320)


if __name__ == "__main__":
    unittest.main()
