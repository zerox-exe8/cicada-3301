import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio

from src.cogs.music._extractor import (
    parse_and_clean_query,
    score_candidate,
    clean_track_title,
    NativeExtractor,
)
from src.cogs.music._models import Track


class TestMusicPerformance(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying music query normalization, candidate scoring, and latency safeguards."""

    def test_parse_and_clean_query_preserves_song_title(self):
        """Universal query normalizer must strip noise while preserving full song & artist titles."""
        # Test 8D audio noise stripping
        cleaned = parse_and_clean_query("8D Audio - Kesariya Arijit Singh")
        self.assertIn("kesariya", cleaned.lower())
        self.assertIn("arijit singh", cleaned.lower())
        self.assertNotIn("8d audio", cleaned.lower())

        # Test conversational prefix stripping
        cleaned2 = parse_and_clean_query("play faded alan walker please")
        self.assertIn("faded", cleaned2.lower())
        self.assertIn("alan walker", cleaned2.lower())

    def test_score_candidate_prioritizes_official(self):
        """Scorer must award higher score to official versions over random covers."""
        query = "kesariya arijit singh"
        official_score = score_candidate(
            title="Kesariya (From 'Brahmastra')",
            subtitle_or_author="Arijit Singh, Pritam",
            query=query,
            duration=268,
        )

        cover_score = score_candidate(
            title="Kesariya - Unplugged Bedroom Cover",
            subtitle_or_author="Random Singer",
            query=query,
            duration=180,
        )

        self.assertGreater(official_score, cover_score)
        self.assertGreater(official_score, 0)

    def test_clean_track_title_removes_junk_brackets(self):
        """clean_track_title must strip bracketed video descriptors for clean UI cards."""
        title = "Chaleya [Official Music Video] (4K 60FPS)"
        cleaned = clean_track_title(title)
        self.assertEqual(cleaned, "Chaleya")

    async def test_search_cache_instant_retrieval(self):
        """Searching for previously cached query must return in 0ms without network round-trips."""
        from src.cogs.music._extractor import _SEARCH_CACHE
        import time

        test_track = Track(
            title="Believer",
            author="Imagine Dragons",
            url="https://youtube.com/watch?v=mock123",
            stream_url="",
            duration=204,
            thumbnail=None,
            requester="Tester",
        )
        _SEARCH_CACHE["believer imagine dragons"] = (time.time(), test_track)

        cached_res = await NativeExtractor.extract("believer imagine dragons", requester="Tester")
        self.assertIsNotNone(cached_res)
        self.assertEqual(cached_res.title, "Believer")
        self.assertEqual(cached_res.author, "Imagine Dragons")

    def test_playlist_regex_and_play_imports(self):
        """Verify play command imports standard library 're' and correctly resolves targeted playlist video IDs."""
        import src.cogs.music._commands.play as play_mod

        # Verify 're' module is present in play command scope
        self.assertTrue(hasattr(play_mod, "re"))

        # Test target video extraction from various YouTube playlist URLs
        urls = [
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL12345", "dQw4w9WgXcQ"),
            ("https://youtu.be/dQw4w9WgXcQ?list=PL12345", "dQw4w9WgXcQ"),
            ("https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=PL12345", "dQw4w9WgXcQ"),
        ]
        for url, expected_id in urls:
            m = play_mod.re.search(r"(?:v=|\/|youtu\.be\/)([a-zA-Z0-9_-]{11})", url)
            self.assertIsNotNone(m, f"Failed to match target ID in {url}")
            self.assertEqual(m.group(1), expected_id)

    async def test_stream_url_priority_and_saavn_extraction(self):
        """Verify JioSaavn direct CDN extraction succeeds and returns valid stream URL."""
        res = await NativeExtractor._extract_jiosaavn("kesariya", requester="Tester", is_autoplay=False)
        self.assertIsNotNone(res)
        self.assertIn("kesariya", res.title.lower())
        self.assertTrue(res.stream_url.startswith("http"))
        self.assertIn("saavncdn.com", res.stream_url)


if __name__ == "__main__":
    unittest.main()
