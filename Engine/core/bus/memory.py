import asyncio
import logging
from collections import defaultdict
from typing import Dict, List
from core.bus.base import AbstractEventBus, EventHandler
from schemas.events import BaseEvent

logger = logging.getLogger("kyro.engine.bus.memory")

class MemoryEventBus(AbstractEventBus):
    """High-throughput In-Memory Event Bus with prioritized task dispatch."""

    def __init__(self, max_queue_size: int = 50_000) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_queue_size)
        self._workers: List[asyncio.Task] = []
        self._running: bool = False
        self._worker_count: int = 8  # Parallel dispatch workers

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self._worker_count):
            task = asyncio.create_task(self._dispatch_worker(i), name=f"bus-worker-{i}")
            self._workers.append(task)
        logger.info("MemoryEventBus started with %d workers", self._worker_count)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("MemoryEventBus stopped cleanly")

    async def publish(self, topic: str, event: BaseEvent) -> None:
        # Invert priority so higher integer (CRITICAL=30) gets popped first: -event.priority
        priority_tuple = (-int(event.priority), event.timestamp, topic, event)
        await self._queue.put(priority_tuple)

    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        self._subscribers[topic].append(handler)
        logger.debug("Subscribed %s to topic %s", handler.__name__, topic)

    async def _dispatch_worker(self, worker_id: int) -> None:
        while self._running:
            try:
                _, _, topic, event = await self._queue.get()
                handlers = self._subscribers.get(topic, [])
                # Also support wildcard pattern e.g. "event.*"
                if "." in topic:
                    root_topic = topic.split(".")[0] + ".*"
                    handlers.extend(self._subscribers.get(root_topic, []))

                if handlers:
                    # Execute all subscribed handlers concurrently
                    await asyncio.gather(
                        *(handler(event) for handler in handlers),
                        return_exceptions=True
                    )
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in bus worker %d: %s", worker_id, e, exc_info=True)
