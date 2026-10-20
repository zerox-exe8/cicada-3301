import asyncio
import time
import unittest
from config.constants import EventPriority, OpCode
from schemas.entities import PlatformSource, UserEntity
from schemas.events import MessageEvent, AuditEvent, ActionRequest
from core.bus.memory import MemoryEventBus
from core.actors.guild_actor import ActorRegistry
from agents.reflex.interceptor import ReflexInterceptor

class TestEngineCore(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.bus = MemoryEventBus()
        await self.bus.start()
        self.received_events = []

        async def handler(event):
            self.received_events.append(event)

        self.actor_registry = ActorRegistry(event_handler=handler)
        self.actor_registry.start()

    async def asyncTearDown(self):
        await self.actor_registry.stop()
        await self.bus.stop()

    async def test_bus_pub_sub(self):
        received = []
        async def on_event(ev):
            received.append(ev)

        await self.bus.subscribe("test.topic", on_event)
        event = MessageEvent(
            guild_id="guild_123",
            channel_id="chan_456",
            content="Hello World",
            source=PlatformSource.DISCORD
        )
        await self.bus.publish("test.topic", event)
        await asyncio.sleep(0.05)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].content, "Hello World")

    async def test_guild_actor_isolation(self):
        event1 = MessageEvent(
            guild_id="guild_A",
            channel_id="chan_1",
            content="Msg 1",
            source=PlatformSource.WEB
        )
        event2 = MessageEvent(
            guild_id="guild_A",
            channel_id="chan_1",
            content="Msg 2",
            source=PlatformSource.WEB
        )
        await self.actor_registry.dispatch_to_guild(event1)
        await self.actor_registry.dispatch_to_guild(event2)
        await asyncio.sleep(0.05)
        self.assertEqual(len(self.received_events), 2)
        self.assertEqual(self.received_events[0].content, "Msg 1")
        self.assertEqual(self.received_events[1].content, "Msg 2")

    def test_reflex_interceptor_performance(self):
        interceptor = ReflexInterceptor()
        user = UserEntity(id="spammer_99", username="evil", source=PlatformSource.DISCORD)

        # 1. Normal message test
        normal_ev = MessageEvent(
            guild_id="guild_1",
            channel_id="c1",
            content="Just a friendly hello!",
            actor=user,
            source=PlatformSource.DISCORD
        )
        verdict = interceptor.inspect_message(normal_ev)
        self.assertFalse(verdict.is_threat)
        self.assertLess(verdict.execution_time_us, 1000.0)  # Must be under 1ms (1000us)

        # 2. Phishing domain test
        phish_ev = MessageEvent(
            guild_id="guild_1",
            channel_id="c1",
            content="Free Nitro here: https://free-nitro.xyz/gift",
            actor=user,
            source=PlatformSource.DISCORD
        )
        verdict2 = interceptor.inspect_message(phish_ev)
        self.assertTrue(verdict2.is_threat)
        self.assertEqual(verdict2.reason, "PHISHING_DOMAIN_DETECTED")
        self.assertLess(verdict2.execution_time_us, 1000.0)

if __name__ == "__main__":
    unittest.main()
