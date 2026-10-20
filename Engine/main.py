import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException, Request
from config.settings import settings
from config.constants import EventPriority, OpCode
from schemas.entities import PlatformSource, UserEntity
from schemas.events import BaseEvent, MessageEvent, AuditEvent, ActionRequest
from schemas.responses import EngineResponse
from core.bus.memory import MemoryEventBus
from core.actors.guild_actor import ActorRegistry
from agents.reflex.interceptor import ReflexInterceptor
from storage.cache import CacheManager
from storage.db import DatabaseManager
from managers.media import MediaManager
from platforms.discord import discord_router, set_discord_service, DiscordPlatformService
from kyrolink import (
    kyrolink_router,
    lavalink_compat_router,
    set_kyrolink_components,
    ProxyPoolManager,
    UnblockableResolver,
)

logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("kyro.engine")

# Engine Core Singletons
bus = MemoryEventBus()
reflex = ReflexInterceptor()
cache = CacheManager()
db = DatabaseManager()
media = MediaManager(cache=cache)
proxy_pool = ProxyPoolManager()
unblockable = UnblockableResolver(media_manager=media, proxy_pool=proxy_pool, cache=cache)

async def global_event_processor(event: BaseEvent) -> None:
    """Core event processing pipeline executing inside an isolated guild actor."""
    logger.debug("Guild Actor processing event: %s on guild: %s", event.event_id, event.guild_id)

    # Intercept with Reflex Stage 1 if MessageEvent or AuditEvent
    if isinstance(event, MessageEvent):
        verdict = reflex.inspect_message(event)
        if verdict.is_threat:
            logger.warning(
                "[REFLEX THREAT] Guild %s | Reason: %s | Action: %s (Latency: %.2fus)",
                event.guild_id, verdict.reason, verdict.action_suggested, verdict.execution_time_us
            )
            # Emit high-priority alert or action
            alert = ActionRequest(
                guild_id=event.guild_id,
                priority=EventPriority.CRITICAL,
                action_name=verdict.action_suggested or "ALERT",
                target_id=event.actor.id if event.actor else None,
                params={"reason": verdict.reason, "original_event_id": event.event_id}
            )
            await bus.publish("actions.critical", alert)

    elif isinstance(event, AuditEvent):
        verdict = reflex.inspect_audit(event)
        if verdict.is_threat:
            logger.critical(
                "[CRITICAL AUDIT RAID] Guild %s | Action: %s | Latency: %.2fus",
                event.guild_id, verdict.reason, verdict.execution_time_us
            )

actor_registry = ActorRegistry(event_handler=global_event_processor)
discord_service = DiscordPlatformService(event_bus=bus, actor_registry=actor_registry, cache=cache)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Initializing Kyro Core Engine [Worker: %s, Env: %s]...", settings.WORKER_ID, settings.ENV)
    await cache.initialize()
    await db.connect()
    await bus.start()
    actor_registry.start()
    set_discord_service(discord_service)
    set_kyrolink_components(media_mgr=media, unblockable_resolver=unblockable, proxy_pool=proxy_pool)

    # Subscribe actor dispatcher to all incoming events
    async def actor_bridge(event: BaseEvent) -> None:
        await actor_registry.dispatch_to_guild(event)

    await bus.subscribe("events.*", actor_bridge)
    logger.info("Kyro Core Engine initialized and accepting traffic.")
    yield
    logger.info("Gracefully shutting down Kyro Core Engine...")
    await actor_registry.stop()
    await bus.stop()
    await db.disconnect()
    await cache.close()
    await media.close()
    await unblockable.close()
    logger.info("Kyro Core Engine shutdown complete.")


app = FastAPI(
    title="Kyro Core Distributed Engine",
    version="1.0.0",
    description="High-Throughput C100K Event-Driven Engine for Omni-Channel Kyro Ecosystem",
    lifespan=lifespan
)

# Mount Dedicated Platform & Audio Routers
app.include_router(discord_router)
app.include_router(kyrolink_router)
app.include_router(lavalink_compat_router)


@app.get("/health", response_model=EngineResponse)
async def health_check() -> EngineResponse:
    return EngineResponse.ok(
        data={
            "worker_id": settings.WORKER_ID,
            "env": settings.ENV,
            "status": "HEALTHY",
            "uptime": time.time()
        },
        message="Kyro Engine is healthy"
    )


@app.post("/v1/events/dispatch", response_model=EngineResponse)
async def dispatch_event(event: MessageEvent) -> EngineResponse:
    start = time.perf_counter_ns()
    await bus.publish(f"events.{event.source}", event)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
    return EngineResponse.ok(
        data={"event_id": event.event_id, "queued": True},
        message="Event dispatched to bus",
        exec_time=elapsed_ms
    )


@app.post("/v1/actions/execute", response_model=EngineResponse)
async def execute_action(action: ActionRequest) -> EngineResponse:
    start = time.perf_counter_ns()
    dispatched = await actor_registry.dispatch_to_guild(action)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
    if not dispatched:
        raise HTTPException(status_code=429, detail="Guild actor queue full")

    return EngineResponse.ok(
        data={"action_id": action.event_id, "status": "QUEUED"},
        message="Action queued in guild actor",
        exec_time=elapsed_ms
    )


@app.get("/v1/media/search", response_model=EngineResponse)
async def media_search(q: str, limit: int = 5) -> EngineResponse:
    start = time.perf_counter_ns()
    results = await media.search(query=q, limit=limit)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
    return EngineResponse.ok(
        data=results.model_dump(),
        message=f"Found {results.count} track(s)",
        exec_time=elapsed_ms
    )


@app.get("/v1/media/resolve", response_model=EngineResponse)
async def media_resolve(q: str) -> EngineResponse:
    start = time.perf_counter_ns()
    track = await media.resolve(query=q)
    elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000.0
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return EngineResponse.ok(
        data=track.model_dump(),
        message="Track resolved successfully",
        exec_time=elapsed_ms
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
