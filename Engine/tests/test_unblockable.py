import asyncio
import unittest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from kyrolink.proxy_manager import ProxyPoolManager
from kyrolink.unblockable import UnblockableResolver
from managers.media import MediaManager
from schemas.media import MediaTrack


class TestKyroLinkUnblockable(unittest.IsolatedAsyncioTestCase):
    """Deep verification of the Anti-Ban, Unblockable, and Multi-Tier Audio Streaming Architecture."""

    async def asyncSetUp(self) -> None:
        self.media = MediaManager()
        self.proxy_pool = ProxyPoolManager()
        self.resolver = UnblockableResolver(
            media_manager=self.media,
            proxy_pool=self.proxy_pool
        )
        self.client = TestClient(app)

    async def asyncTearDown(self) -> None:
        await self.media.close()
        await self.resolver.close()

    def test_proxy_pool_rotation_and_quarantine(self) -> None:
        pool = ProxyPoolManager()
        csv_proxies = "http://user:pass@1.1.1.1:8080, http://user:pass@2.2.2.2:8080\nhttp://user:pass@3.3.3.3:8080"
        pool.load_from_csv(csv_proxies)

        self.assertEqual(pool.total_proxies, 3)

        # Round robin rotation
        p1 = pool.get_proxy()
        p2 = pool.get_proxy()
        p3 = pool.get_proxy()
        p4 = pool.get_proxy()
        self.assertIn("1.1.1.1", p1)
        self.assertIn("2.2.2.2", p2)
        self.assertIn("3.3.3.3", p3)
        self.assertIn("1.1.1.1", p4)

        # Report 429 block on 1.1.1.1
        pool.report_failure(p1, is_ban=True)
        stats = pool.stats()
        self.assertEqual(stats["quarantined"], 1)
        self.assertEqual(stats["active"], 2)

        # Next fetched proxy should not be the quarantined one
        p_next = pool.get_proxy()
        self.assertNotIn("1.1.1.1", p_next)

    async def test_tier1_saavn_resolution(self) -> None:
        """Verify Tier 1 Akamai 320kbps CDN resolution (0% cloud block rate)."""
        track = await self.resolver.resolve("Arijit Singh Kesariya")
        self.assertIsNotNone(track)
        self.assertIn("saavn", track.stream_url.lower())
        self.assertIn(track.bitrate_kbps, [160, 320])
        print(f"\n[TEST TIER 1 AKAMAI] Title: '{track.title}' | Stream: {track.stream_url[:55]}... | Bitrate: {track.bitrate_kbps}kbps")

    async def test_tier2_spotify_url_bridging(self) -> None:
        """Verify Spotify track URL is parsed and seamlessly bridged to unblocked studio stream."""
        spotify_url = "https://open.spotify.com/track/0VjIjW4GlUZAMYd2vXMi3b"
        track = await self.resolver.resolve(spotify_url)
        self.assertIsNotNone(track)
        self.assertTrue(len(track.stream_url) > 10)
        print(f"\n[TEST TIER 2 SPOTIFY BRIDGED] Title: '{track.title}' | Source: {track.source} | Stream: {track.stream_url[:55]}...")

    async def test_kyrolink_health_endpoint(self) -> None:
        """Verify KyroLink health endpoint returns unblockable tiers and proxy telemetry."""
        resp = self.client.get("/v1/kyrolink/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["engine"], "KyroLink Unblockable Native Audio Node")
        self.assertEqual(data["status"], "OPERATIONAL")
        self.assertIn("unblockable_tiers", data)
        self.assertEqual(len(data["unblockable_tiers"]), 4)

    async def test_kyrolink_loadtracks_endpoint(self) -> None:
        """Verify /v1/kyrolink/loadtracks drop-in Lavalink v4 replacement."""
        resp = self.client.get("/v1/kyrolink/loadtracks?identifier=Tum+Hi+Ho")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["loadType"], "track")
        info = data["data"]["info"]
        self.assertIn("Tum Hi Ho", info["title"])
        self.assertTrue(data["data"]["encoded"].startswith("https://"))
        print(f"\n[TEST LOADTRACKS] Lavalink Drop-In Result: '{info['title']}' resolved in {data['execution_ms']:.2f}ms")

    async def test_proxy_management_api(self) -> None:
        """Verify dynamic proxy addition and telemetry via HTTP API."""
        resp = self.client.post("/v1/kyrolink/proxies/add", json={
            "proxies": ["http://user:pass@10.0.0.1:8080", "socks5://10.0.0.2:1080"]
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertGreaterEqual(data["total_proxies"], 2)

        # Query stats
        stat_resp = self.client.get("/v1/kyrolink/proxies")
        self.assertEqual(stat_resp.status_code, 200)
        stat_data = stat_resp.json()
        self.assertGreaterEqual(stat_data["total"], 2)

    async def test_audio_stream_relay_for_discord(self) -> None:
        """Verify high-speed Audio Stream Relay pipes raw CDN chunks without IP-binding blocks."""
        track = await self.resolver.resolve("Tum Hi Ho")
        self.assertIsNotNone(track)
        
        # Test relaying first 64KB chunk through KyroLink
        import urllib.parse
        encoded_url = urllib.parse.quote(track.stream_url)
        resp = self.client.get(
            f"/v1/kyrolink/stream?url={encoded_url}",
            headers={"Range": "bytes=0-65535"}
        )
        self.assertIn(resp.status_code, [200, 206])
        self.assertGreaterEqual(len(resp.content), 60000)
        print(f"\n[TEST AUDIO RELAY] Relayed {len(resp.content)} bytes from CDN to Discord Voice via Engine")

    async def test_lavalink_v4_compatibility_routes(self) -> None:
        """Verify direct drop-in Lavalink v4 endpoints for Wavelink."""
        # /version
        ver_resp = self.client.get("/version")
        self.assertEqual(ver_resp.status_code, 200)
        self.assertEqual(ver_resp.text, "4.0.8")

        # /v4/info
        info_resp = self.client.get("/v4/info")
        self.assertEqual(info_resp.status_code, 200)
        info_data = info_resp.json()
        self.assertEqual(info_data["version"]["semver"], "4.0.8")
        self.assertIn("jiosaavn", info_data["sourceManagers"])

        # /v4/loadtracks
        load_resp = self.client.get("/v4/loadtracks?identifier=Kesariya")
        self.assertEqual(load_resp.status_code, 200)
        load_data = load_resp.json()
        self.assertEqual(load_data["loadType"], "track")
        self.assertIn("Kesariya", load_data["data"]["info"]["title"])


if __name__ == "__main__":
    unittest.main()
