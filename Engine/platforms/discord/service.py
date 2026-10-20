import logging
from typing import Dict, Any, Optional
from core.bus.base import AbstractEventBus
from core.actors.guild_actor import ActorRegistry
from storage.cache import CacheManager
from platforms.discord.translator import DiscordTranslator
from platforms.discord.actions import DiscordActionExecutor, DiscordActionResult

logger = logging.getLogger("kyro.engine.platforms.discord.service")

class DiscordPlatformService:
    """Dedicated Discord Platform Orchestrator inside Kyro Engine.
    Handles all Discord-specific translations, guild state caching, and action dispatches.
    """

    def __init__(
        self,
        event_bus: AbstractEventBus,
        actor_registry: ActorRegistry,
        cache: Optional[CacheManager] = None
    ) -> None:
        self.bus = event_bus
        self.actors = actor_registry
        self.cache = cache
        self.translator = DiscordTranslator()
        self.executor = DiscordActionExecutor()

    async def ingest_message(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Convert raw Discord message, route to isolated guild actor, and publish to event bus."""
        event = self.translator.to_message_event(raw_payload)

        # 1. Update guild message activity metric in L1/L2 cache
        if self.cache:
            cache_key = f"discord:guild:{event.guild_id}:msg_count"
            await self.cache.increment(cache_key, amount=1, ttl_seconds=86400)

        # 2. Dispatch to isolated guild actor (FIFO queue)
        await self.actors.dispatch_to_guild(event)

        # 3. Publish to central event bus for cross-platform listeners
        await self.bus.publish("events.discord.message", event)

        return {"event_id": event.event_id, "status": "QUEUED"}

    async def ingest_audit(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Convert Discord audit log entry, route to guild actor, and check security rules."""
        event = self.translator.to_audit_event(raw_payload)
        await self.actors.dispatch_to_guild(event)
        await self.bus.publish("events.discord.audit", event)
        return {"event_id": event.event_id, "action_type": event.action_type, "status": "QUEUED"}

    async def execute_action(
        self,
        action_name: str,
        guild_id: str,
        target_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> DiscordActionResult:
        """Execute a validated Discord action and return the instruction payload."""
        result = self.executor.execute(action_name, guild_id, target_id, params)
        if result.success:
            logger.info("Prepared Discord action %s on guild %s (target: %s)", action_name, guild_id, target_id)
        return result
