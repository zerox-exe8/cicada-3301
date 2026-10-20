import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, Awaitable
from schemas.events import BaseEvent

logger = logging.getLogger("kyro.engine.actor")

class GuildActor:
    """Virtual Actor representing an isolated Guild/Tenant state and event queue.
    Ensures serialized FIFO event processing to eliminate race conditions.
    """

    def __init__(self, guild_id: str, handler: Callable[[BaseEvent], Awaitable[None]]) -> None:
        self.guild_id = guild_id
        self.handler = handler
        self.queue: asyncio.Queue[BaseEvent] = asyncio.Queue(maxsize=1000)
        self.last_active: float = time.time()
        self.is_running: bool = False
        self._worker_task: Optional[asyncio.Task] = None
        self.state: Dict[str, Any] = {}

    def start(self) -> None:
        if not self.is_running:
            self.is_running = True
            self._worker_task = asyncio.create_task(
                self._run(), name=f"guild-actor-{self.guild_id}"
            )

    async def stop(self) -> None:
        self.is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def enqueue(self, event: BaseEvent) -> bool:
        """Enqueue an event into this actor's serial processing queue."""
        self.last_active = time.time()
        try:
            self.queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            logger.warning("Actor queue full for guild %s! Event %s dropped", self.guild_id, event.event_id)
            return False

    async def _run(self) -> None:
        while self.is_running:
            try:
                event = await self.queue.get()
                self.last_active = time.time()
                try:
                    await self.handler(event)
                except Exception as e:
                    logger.error("Error processing event %s in guild actor %s: %s", event.event_id, self.guild_id, e, exc_info=True)
                finally:
                    self.queue.task_done()
            except asyncio.CancelledError:
                break


class ActorRegistry:
    """Manages active GuildActors and evicts idle actors to conserve RAM."""

    def __init__(self, event_handler: Callable[[BaseEvent], Awaitable[None]], idle_timeout: float = 300.0) -> None:
        self._actors: Dict[str, GuildActor] = {}
        self._handler = event_handler
        self._idle_timeout = idle_timeout
        self._reaper_task: Optional[asyncio.Task] = None
        self._running: bool = False

    def start(self) -> None:
        self._running = True
        self._reaper_task = asyncio.create_task(self._reap_idle_actors(), name="actor-reaper")

    async def stop(self) -> None:
        self._running = False
        if self._reaper_task:
            self._reaper_task.cancel()
        for actor in list(self._actors.values()):
            await actor.stop()
        self._actors.clear()

    def get_or_create(self, guild_id: str) -> GuildActor:
        actor = self._actors.get(guild_id)
        if actor is None:
            actor = GuildActor(guild_id, self._handler)
            actor.start()
            self._actors[guild_id] = actor
        return actor

    async def dispatch_to_guild(self, event: BaseEvent) -> bool:
        actor = self.get_or_create(event.guild_id)
        return await actor.enqueue(event)

    async def _reap_idle_actors(self) -> None:
        """Periodic garbage collector for idle actors."""
        while self._running:
            try:
                await asyncio.sleep(60.0)
                now = time.time()
                idle_guilds = [
                    gid for gid, actor in self._actors.items()
                    if now - actor.last_active > self._idle_timeout and actor.queue.empty()
                ]
                for gid in idle_guilds:
                    actor = self._actors.pop(gid, None)
                    if actor:
                        await actor.stop()
                        logger.debug("Reaped idle actor for guild %s", gid)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in actor reaper: %s", e)
