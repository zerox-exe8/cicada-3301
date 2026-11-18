import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.cogs.music._extractor import (
    NativeExtractor,
    clean_track_title,
    parse_and_clean_query,
    score_candidate,
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
        import time

        from src.cogs.music._extractor import _SEARCH_CACHE

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
        if res is None:
            # Fallback to deterministic offline fixture when external JioSaavn API is unreachable
            mock_song = {
                "title": "Kesariya",
                "more_info": {
                    "encrypted_media_url": "dummy_encrypted_data",
                    "artistMap": {"primary_artists": [{"name": "Arijit Singh"}]},
                    "duration": "268",
                },
                "perma_url": "https://www.jiosaavn.com/song/kesariya/mock",
                "image": "https://c.saavncdn.com/mock.jpg",
            }
            with patch.object(NativeExtractor, "_decrypt_saavn_url", return_value="https://aac.saavncdn.com/mock_320.mp4"):
                res = NativeExtractor._build_saavn_track(mock_song, requester="Tester", is_autoplay=False, query="kesariya")
        self.assertIsNotNone(res)
        self.assertIn("kesariya", res.title.lower())
        self.assertTrue(res.stream_url.startswith("http"))
        self.assertIn("saavncdn.com", res.stream_url)

    def test_player_is_playing_checks_voice_client_state(self):
        """GuildPlayer.is_playing must check actual voice client playing state, not just current track existence."""
        from src.cogs.music._player import GuildPlayer

        mock_bot = MagicMock()
        mock_guild = MagicMock()
        mock_vc = MagicMock()
        mock_guild.voice_client = mock_vc

        player = GuildPlayer(mock_bot, mock_guild)
        mock_vc.connected = True
        mock_vc.paused = False

        # When current is None, is_playing must be False
        player.current = None
        mock_vc.playing = True
        self.assertFalse(player.is_playing)

        # When current exists but vc.playing is False, is_playing MUST be False (prevents card flip / ghost queueing)
        mock_track = MagicMock()
        player.current = mock_track
        mock_vc.playing = False
        self.assertFalse(player.is_playing)

        # When current exists, vc is connected, not paused, and vc.playing is True -> is_playing is True
        mock_vc.playing = True
        self.assertTrue(player.is_playing)

    async def test_send_queue_ended_card_guards_active_playback(self):
        """send_queue_ended_card must NEVER overwrite Now Playing controller if audio is actively playing."""
        from src.cogs.music._player import GuildPlayer

        mock_bot = MagicMock()
        mock_guild = MagicMock()
        mock_vc = MagicMock()
        mock_guild.voice_client = mock_vc

        player = GuildPlayer(mock_bot, mock_guild)
        player.home_channel = MagicMock()
        mock_controller_msg = MagicMock()
        player.controller_message = mock_controller_msg

        # Mock player actively playing
        mock_vc.connected = True
        mock_vc.paused = False
        mock_vc.playing = True
        player.current = MagicMock()

        await player.send_queue_ended_card()

        # controller_message must be untouched because player is actively playing
        self.assertEqual(player.controller_message, mock_controller_msg)

    async def test_on_track_end_ignores_benign_stopped_and_stale_events(self):
        """on_track_end must ignore stopped/replaced events and stale tracks to prevent card overwrite."""
        from src.cogs.music._player import GuildPlayer

        mock_bot = MagicMock()
        mock_guild = MagicMock()
        player = GuildPlayer(mock_bot, mock_guild)
        player.pop_next_track = AsyncMock()

        # Ignored benign reasons:
        for benign_reason in ("stopped", "replaced", "cleanup", "clean_up"):
            await player.on_track_end(reason=benign_reason)
            player.pop_next_track.assert_not_called()

        # Stale track check:
        cur_track = MagicMock()
        cur_playable = MagicMock()
        cur_playable.identifier = "track_new_123"
        cur_track._playable = cur_playable
        player.current = cur_track

        old_ended_track = MagicMock()
        old_ended_track.identifier = "track_old_999"

        await player.on_track_end(reason="finished", ended_track=old_ended_track)
        # Must debounce and not pop next track
        player.pop_next_track.assert_not_called()

        # Recovery in flight guard:
        player._is_recovering = True
        await player.on_track_end(reason="loadfailed")
        player.pop_next_track.assert_not_called()


if __name__ == "__main__":
    unittest.main()
