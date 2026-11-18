import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from src.managers.giveaway_manager import GiveawayManager
from src.managers.ticket_manager import TicketManager
from src.repositories.ticket_repo import TicketRepository


class TestConcurrencySafety(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying race-condition resilience in Tickets and Giveaways."""

    async def test_ticket_claim_atomic_concurrency(self):
        """Concurrent claim attempts on the same ticket must grant claim to only one caller."""
        db = MagicMock()
        # Mock database atomic update: returns dict on first call, None on second
        call_count = 0

        async def mock_fetch_one(query, *args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"id": 1}
            return None

        db.fetch_one = AsyncMock(side_effect=mock_fetch_one)
        db.execute = AsyncMock()

        mgr = TicketManager(db)
        mgr._active_tickets_cache[123] = {"channel_id": 123, "status": "open", "claimed_by": None}

        # Simulate two concurrent claim calls from Staff A and Staff B
        res_a, res_b = await asyncio.gather(
            mgr.claim_ticket(123, 11111),
            mgr.claim_ticket(123, 22222),
        )

        # One must succeed, one must fail
        self.assertTrue(res_a != res_b)
        self.assertTrue(res_a is True or res_b is True)
        self.assertTrue(res_a is False or res_b is False)

    async def test_giveaway_end_atomic_concurrency(self):
        """Concurrent calls to end_giveaway must only finalize the giveaway once."""
        db = MagicMock()
        db.fetch_all = AsyncMock(return_value=[])
        # Return participant user IDs
        db.fetch_all = AsyncMock(side_effect=lambda q, *args: [{"user_id": 101}, {"user_id": 102}] if "giveaway_participants" in q else [])

        call_count = 0

        async def mock_fetch_one(query, *args):
            nonlocal call_count
            if "UPDATE giveaways SET is_ended" in query:
                call_count += 1
                if call_count == 1:
                    return {"id": 99}
                return None
            return {
                "id": 99,
                "guild_id": 1234,
                "channel_id": 5678,
                "message_id": 8888,
                "host_id": 9999,
                "prize": "Discord Nitro",
                "winner_count": 1,
                "ends_at": MagicMock(tzinfo=None, replace=lambda **kwargs: MagicMock()),
                "is_ended": False,
            }

        db.fetch_one = AsyncMock(side_effect=mock_fetch_one)
        db.execute = AsyncMock()

        gw_mgr = GiveawayManager(db)
        gw_mgr._active_giveaways[8888] = {
            "id": 99,
            "guild_id": 1234,
            "channel_id": 5678,
            "message_id": 8888,
            "host_id": 9999,
            "prize": "Discord Nitro",
            "winner_count": 1,
            "ends_at": MagicMock(tzinfo=None, replace=lambda **kwargs: MagicMock()),
            "is_ended": False,
        }

        # Run two concurrent finalize requests
        res1, res2 = await asyncio.gather(
            gw_mgr.end_giveaway(8888),
            gw_mgr.end_giveaway(8888),
        )

        # Exactly one must return the finalized dict, and the other must return None
        results = [res1, res2]
        self.assertEqual(sum(1 for r in results if r is not None), 1)
        self.assertEqual(sum(1 for r in results if r is None), 1)


if __name__ == "__main__":
    unittest.main()
