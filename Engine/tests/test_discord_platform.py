import asyncio
import time
import unittest
from core.bus.memory import MemoryEventBus
from core.actors.guild_actor import ActorRegistry
from storage.cache import CacheManager
from platforms.discord.translator import DiscordTranslator
from platforms.discord.actions import DiscordActionExecutor, DiscordActionType
from platforms.discord.service import DiscordPlatformService

class TestDiscordPlatformAdapter(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.bus = MemoryEventBus()
        await self.bus.start()
        self.cache = CacheManager()
        await self.cache.initialize()

        self.actor_events = []
        async def dummy_handler(ev):
            self.actor_events.append(ev)

        self.actors = ActorRegistry(event_handler=dummy_handler)
        self.actors.start()

        self.service = DiscordPlatformService(
            event_bus=self.bus,
            actor_registry=self.actors,
            cache=self.cache
        )

    async def asyncTearDown(self):
        await self.actors.stop()
        await self.bus.stop()
        await self.cache.close()

    def test_translator_mappings(self):
        """Test conversion of Discord API JSON into Engine Universal Schemas."""
        raw_msg = {
            "guild_id": "999888777",
            "channel_id": "111222333",
            "content": "Testing Discord Translator",
            "actor": {
                "id": "444555666",
                "username": "TestUser",
                "global_name": "Test User Global",
                "bot": False
            }
        }
        event = DiscordTranslator.to_message_event(raw_msg)
        self.assertEqual(event.guild_id, "999888777")
        self.assertEqual(event.actor.username, "TestUser")
        self.assertEqual(event.source, "discord")

    def test_action_executor_sanctions(self):
        """Test Discord specific action creation (timeout, ban, channel lock)."""
        # 1. Timeout Action
        timeout_res = DiscordActionExecutor.execute(
            action_name="TIMEOUT_MEMBER",
            guild_id="999888777",
            target_id="444555666",
            params={"duration_seconds": 600, "reason": "Spamming"}
        )
        self.assertTrue(timeout_res.success)
        self.assertEqual(timeout_res.action, DiscordActionType.TIMEOUT_MEMBER)
        self.assertIn("communication_disabled_until", timeout_res.discord_payload)

        # 2. Ban Action
        ban_res = DiscordActionExecutor.execute(
            action_name="BAN_MEMBER",
            guild_id="999888777",
            target_id="444555666",
            params={"delete_message_days": 1}
        )
        self.assertTrue(ban_res.success)
        self.assertEqual(ban_res.discord_payload["delete_message_days"], 1)

    async def test_platform_service_ingest(self):
        """Test ingesting a message through the DiscordPlatformService."""
        raw_msg = {
            "guild_id": "guild_test_01",
            "channel_id": "chan_test_01",
            "content": "Hello via Discord Adapter",
            "actor": {"id": "user_01", "username": "Member1"}
        }
        res = await self.service.ingest_message(raw_msg)
        self.assertEqual(res["status"], "QUEUED")
        await asyncio.sleep(0.05)

        # Verify routed to guild actor
        self.assertEqual(len(self.actor_events), 1)
        self.assertEqual(self.actor_events[0].content, "Hello via Discord Adapter")

        # Verify guild stats incremented in cache
        cached_count = await self.cache.get("discord:guild:guild_test_01:msg_count")
        self.assertEqual(int(cached_count), 1)

if __name__ == "__main__":
    unittest.main()
