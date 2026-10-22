"""
Kyro Discord Bot - Hardened Lavalink Node Factory
==================================================

Two problems are solved here.

**1. Unbounded HTTP calls.** Wavelink creates its own ``aiohttp.ClientSession``
with the library default timeout of **300 seconds**. Kyro awaits several
Lavalink REST calls directly (``skip``, ``play``, ``stop``, ``move_to``), so a
single slow or unreachable node used to freeze the whole music subsystem: the
awaiting command never returned and the per-guild locks stayed held for the
entire duration, making every later command wait behind it.

Every node Kyro creates goes through this module, so the transport always fails
fast instead of hanging.

**2. No failover.** A Lavalink node is a single point of failure: when it dies
the bot simply cannot play music. ``connect_lavalink_node`` therefore tries the
primary URI first and then any configured fallbacks.

Also note that ``wavelink.Pool.nodes`` returns a **copy** of the pool's internal
mapping, so ``Pool.nodes.clear()`` is a no-op and dead nodes would pile up in
the pool forever. ``discard_node`` removes them properly.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Optional

import aiohttp
import wavelink

if TYPE_CHECKING:
    import discord

logger = logging.getLogger("Kyro.Lavalink")

# Total request budget, TCP connect budget and socket-read budget for every
# call made against the Lavalink REST API.
LAVALINK_HTTP_TIMEOUT = aiohttp.ClientTimeout(
    total=12.0,
    connect=5.0,
    sock_read=8.0,
)

# Budget for a single player operation (skip / stop / move / close).
LAVALINK_OP_TIMEOUT = 8.0

# Budget for starting a track (play does a bit more work than skip).
LAVALINK_PLAY_TIMEOUT = 12.0

# Budget for the node websocket handshake (it shares the same session).
LAVALINK_CONNECT_TIMEOUT = 10.0

# Overall budget for resolving a playable (search cascade across several
# strategies). Without this a single unresolvable track could keep the caller
# waiting for well over a minute.
LAVALINK_RESOLVE_TIMEOUT = 25.0


class LavalinkUnavailable(RuntimeError):
    """Raised when no Lavalink node could be reached."""


def err_text(exc: BaseException) -> str:
    """
    Render an exception with a guaranteed non-empty description.

    Many transport exceptions carry an empty message (``TimeoutError``,
    ``ClientOSError``, ``KeyError`` ...), so ``str(exc)`` alone produces a
    completely useless incident report.
    """
    name = type(exc).__name__
    text = str(exc).strip()
    return f"{name}: {text}" if text else name


def candidates() -> list[tuple[str, str]]:
    """Return the primary Lavalink URI first, then any configured fallbacks."""
    from src.core.config import Config

    result: list[tuple[str, str]] = []
    primary = (Config.LAVALINK_URI or "").strip()
    if primary:
        result.append((primary, Config.LAVALINK_PASSWORD))

    for raw in (Config.LAVALINK_FALLBACK_URIS or "").split(","):
        uri = raw.strip()
        if uri and all(uri != known for known, _ in result):
            result.append((uri, Config.LAVALINK_PASSWORD))

    return result


def create_lavalink_node(
    uri: str,
    password: str,
    *,
    inactive_player_timeout: int = 300,
) -> wavelink.Node:
    """Create a Wavelink node whose HTTP transport can never block for minutes."""
    session = aiohttp.ClientSession(timeout=LAVALINK_HTTP_TIMEOUT)
    return wavelink.Node(
        uri=uri,
        password=password,
        session=session,
        inactive_player_timeout=inactive_player_timeout,
    )


def _pool_nodes_dict() -> Optional[dict]:
    """Return the wavelink pool's real internal node mapping (if it can be found).

    ``Pool.nodes`` returns a *copy*, so ``Pool.nodes.clear()`` is a no-op and dead
    nodes would accumulate in the pool forever.
    """
    pool = wavelink.Pool
    for name in dir(pool):
        if name.endswith("__nodes"):
            value = getattr(pool, name, None)
            if isinstance(value, dict):
                return value
    return None


def discard_node(node: Any) -> None:
    """Remove a node from the wavelink pool (safety net for a failed close)."""
    pool_nodes = _pool_nodes_dict()
    if pool_nodes is not None:
        identifier = getattr(node, "identifier", None)
        if identifier is not None:
            pool_nodes.pop(identifier, None)


async def close_node(node: Any) -> None:
    """Close a node, drop it from the pool and release its HTTP session."""
    try:
        # `eject=True` makes wavelink remove the node from its pool itself.
        await asyncio.wait_for(node.close(eject=True), timeout=LAVALINK_OP_TIMEOUT)
    except Exception:
        pass

    # Wavelink only closes the aiohttp session when a websocket was created, so a
    # connection attempt that failed before the handshake would leak its session.
    session = getattr(node, "_session", None)
    if session is not None and not getattr(session, "closed", False):
        try:
            await session.close()
        except Exception:
            pass

    discard_node(node)


async def close_pool_nodes() -> None:
    """Close every node in the pool and drop it from the pool."""
    for node in list(wavelink.Pool.nodes.values()):
        await close_node(node)


async def probe_node(node: Any, timeout: float = 6.0) -> bool:
    """
    Verify that a node's REST API actually answers.

    A node can report ``CONNECTED`` (its websocket is still alive) while its REST
    API is completely hung - and every player operation (skip, play, stop) goes
    through the REST API. Treating such a node as healthy is exactly what makes
    the music commands time out while everything else looks fine.
    """
    session = getattr(node, "_session", None)
    if session is None or getattr(session, "closed", False):
        return False

    uri = f"{node.uri}/v4/version"

    # `Node.headers` asserts that a client is attached, which is not the case for
    # a node that never finished connecting. Fall back to an empty header set:
    # the node then answers 401 instead of 200, which still proves the REST API
    # is responsive.
    try:
        headers = node.headers
    except Exception:
        headers = {}

    async def _probe() -> None:
        async with session.get(uri, headers=headers) as resp:
            await resp.read()

    try:
        await asyncio.wait_for(_probe(), timeout=timeout)
        return True
    except Exception:
        return False


async def connect_lavalink_node(
    bot: Optional["discord.Client"] = None,
    *,
    inactive_player_timeout: int = 300,
) -> wavelink.Node:
    """
    Connect to the first reachable Lavalink node.

    The primary URI is tried first, then any configured fallbacks. Wavelink's
    ``Pool.connect`` swallows connection errors and only registers the node on
    success, so the real connection state is verified explicitly afterwards.

    A node is only accepted when its REST API answers as well - a node whose
    websocket is up but whose REST is hung cannot play music.
    """
    failures: list[str] = []

    for uri, password in candidates():
        node = create_lavalink_node(
            uri,
            password,
            inactive_player_timeout=inactive_player_timeout,
        )
        try:
            await asyncio.wait_for(
                wavelink.Pool.connect(nodes=[node], client=bot),
                timeout=LAVALINK_CONNECT_TIMEOUT,
            )
        except Exception as e:
            failures.append(f"{uri} -> {err_text(e)}")
            logger.warning(f"Lavalink node {uri} unreachable: {err_text(e)}")
            await close_node(node)
            continue

        # Pool.connect logs connection errors instead of raising them.
        for _ in range(10):
            if node.status == wavelink.NodeStatus.CONNECTED:
                break
            await asyncio.sleep(0.5)

        if node.status != wavelink.NodeStatus.CONNECTED:
            failures.append(f"{uri} -> status={getattr(node.status, 'name', node.status)}")
            logger.warning(f"Lavalink node {uri} did not reach CONNECTED state.")
            await close_node(node)
            continue

        if not await probe_node(node):
            failures.append(f"{uri} -> REST API unresponsive")
            logger.warning(f"Lavalink node {uri} connected but its REST API does not answer.")
            await close_node(node)
            continue

        logger.info(f"Connected to Lavalink node {uri}")
        return node

    detail = "; ".join(failures) if failures else "no URI configured"
    raise LavalinkUnavailable(f"No reachable Lavalink node ({detail})")
