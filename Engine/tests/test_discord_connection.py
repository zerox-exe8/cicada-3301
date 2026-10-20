import asyncio
import sys
import os
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../Kyro")))

import uvicorn
from main import app
from src.core.engine_client import EngineClient

class TestDiscordEngineBridge(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.config = uvicorn.Config(app=app, host="127.0.0.1", port=8005, log_level="error")
        self.server = uvicorn.Server(self.config)
        self.server_task = asyncio.create_task(self.server.serve())

        for _ in range(50):
            if self.server.started:
                break
            await asyncio.sleep(0.05)

        self.client = EngineClient(base_url="http://127.0.0.1:8005")
        await self.client.check_health()

    async def asyncTearDown(self):
        await self.client.close()
        self.server.should_exit = True
        await asyncio.sleep(0.05)
        if not self.server_task.done():
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass

    async def test_end_to_end_flow(self):
        """Full end-to-end flow: Health, Benchmark Latency, Action Execution, Offline Safety."""
        # 1. Health check
        is_healthy = await self.client.check_health()
        self.assertTrue(is_healthy, "Engine health check failed")

        # 2. Performance benchmark on persistent connection (Average of 5 dispatches)
        latencies = []
        for i in range(5):
            start = time.perf_counter_ns()
            res = await self.client.dispatch_message_event(
                guild_id=123456789,
                channel_id=987654321,
                author_id=555666777,
                author_name="DiscordTester",
                content=f"Hello event {i} from Kyro Discord Bot!"
            )
            elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
            latencies.append(elapsed_ms)
            self.assertIsNotNone(res)
            self.assertTrue(res.get("success"))

        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        print(f"\n[BENCHMARK] Discord -> Engine Dispatch: Avg={avg_latency:.2f}ms | Min={min_latency:.2f}ms")
        self.assertLess(avg_latency, 100.0, f"Average latency too high: {avg_latency}ms")

        # 3. Action Execution through Guild Actor
        action_res = await self.client.execute_action(
            guild_id=123456789,
            action_name="LOCK_CHANNEL",
            params={"channel_id": "987654321", "reason": "Security Alert"}
        )
        self.assertIsNotNone(action_res)
        self.assertTrue(action_res.get("success"))
        self.assertEqual(action_res["data"]["status"], "QUEUED")

        # 4. Resilience check (offline server)
        offline_client = EngineClient(base_url="http://127.0.0.1:9998", timeout=0.2)
        self.assertFalse(await offline_client.check_health())
        offline_event = await offline_client.dispatch_message_event(
            guild_id=1, channel_id=2, author_id=3, author_name="U", content="X"
        )
        self.assertIsNone(offline_event)
        await offline_client.close()

if __name__ == "__main__":
    unittest.main()
