from __future__ import annotations

import logging
import time
from typing import Any, Optional
import aiohttp

logger = logging.getLogger("Kyro.EngineClient")

class EngineClient:
    """Resilient, non-blocking HTTP/gRPC bridge between Kyro Discord Bot and Kyro Engine."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        self._is_online: bool = False
        self._last_health_check: float = 0.0

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def check_health(self) -> bool:
        """Ping the standalone engine to verify connectivity."""
        try:
            session = await self.get_session()
            async with session.get(f"{self.base_url}/health") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._is_online = data.get("success", False)
                    self._last_health_check = time.time()
                    return self._is_online
        except Exception as e:
            self._is_online = False
            logger.debug("Kyro Engine is unreachable: %s", e)
        return False

    @property
    def is_connected(self) -> bool:
        return self._is_online

    async def dispatch_message_event(
        self,
        guild_id: int,
        channel_id: int,
        author_id: int,
        author_name: str,
        content: str,
        is_bot: bool = False
    ) -> Optional[dict[str, Any]]:
        """Asynchronously dispatch a message to the Engine without blocking Discord bot execution."""
        payload = {
            "source": "discord",
            "guild_id": str(guild_id),
            "channel_id": str(channel_id),
            "content": content,
            "actor": {
                "id": str(author_id),
                "source": "discord",
                "username": author_name,
                "is_bot": is_bot
            }
        }
        try:
            session = await self.get_session()
            async with session.post(f"{self.base_url}/v1/events/dispatch", json=payload) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.warning("Engine dispatch returned status %d", resp.status)
        except Exception as e:
            logger.debug("Failed to dispatch event to Engine: %s", e)
        return None

    async def execute_action(
        self,
        guild_id: int,
        action_name: str,
        target_id: Optional[int] = None,
        params: Optional[dict[str, Any]] = None
    ) -> Optional[dict[str, Any]]:
        """Queue an action execution in the Engine's guild actor."""
        payload = {
            "source": "discord",
            "guild_id": str(guild_id),
            "action_name": action_name,
            "target_id": str(target_id) if target_id else None,
            "params": params or {}
        }
        try:
            session = await self.get_session()
            async with session.post(f"{self.base_url}/v1/actions/execute", json=payload) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.debug("Failed to execute action on Engine: %s", e)
        return None

    async def resolve_track(self, query: str) -> Optional[dict[str, Any]]:
        """Resolve a track (Spotify, YouTube, Song name) via Engine's unblockable KyroLink."""
        try:
            import urllib.parse
            session = await self.get_session()
            enc_q = urllib.parse.quote(query.strip())
            async with session.get(f"{self.base_url}/v1/kyrolink/loadtracks?identifier={enc_q}") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("loadType") == "track":
                        return data.get("data")
        except Exception as e:
            logger.debug("Failed to resolve track via Engine KyroLink: %s", e)
        return None

    def get_relay_stream_url(self, raw_stream_url: str) -> str:
        """Get an unblockable relay stream URL that bypasses Google Video IP-affinity blocks."""
        import urllib.parse
        return f"{self.base_url}/v1/kyrolink/stream?url={urllib.parse.quote(raw_stream_url)}"

