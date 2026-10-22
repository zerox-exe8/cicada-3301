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
import json
import logging
import time
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

    The function is idempotent: an exception whose message already starts with
    its own class name is not prefixed a second time.
    """
    name = type(exc).__name__
    text = str(exc).strip()
    if not text:
        return name
    if text.startswith(name):
        return text
    return f"{name}: {text}"


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


# ── Public node discovery ──
#
# Community Lavalink nodes come and go, and most of them have a broken
# websocket (the handshake is rejected with HTTP 400 by a proxy, or the node
# closes the socket before sending its 'ready' op). Because the audio session
# is only created through that websocket, a broken node means the bot cannot
# play anything at all - even though the REST API still answers and song
# searches keep working.
#
# The directory below is refreshed every few minutes by its maintainers and only
# lists nodes that were online at that moment. Kyro probes the entries itself
# and only ever uses a node that passed the full check.

_public_nodes_cache: tuple[float, list[tuple[str, str]]] | None = None
_PUBLIC_NODE_CACHE_TTL = 900.0  # 15 minutes


async def fetch_public_nodes(limit: int = 30) -> list[tuple[str, str]]:
    """
    Fetch the community Lavalink directory and return (uri, password) pairs.

    Results are cached for a while so a failing node does not hammer the
    directory API on every heal attempt.
    """
    global _public_nodes_cache

    from src.core.config import Config

    now = time.time()
    if _public_nodes_cache and now - _public_nodes_cache[0] < _PUBLIC_NODE_CACHE_TTL:
        return _public_nodes_cache[1][:limit]

    url = (Config.LAVALINK_PUBLIC_LIST_URL or "").strip()
    if not url:
        return []

    try:
        timeout_cfg = aiohttp.ClientTimeout(total=15.0, connect=8.0)
        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(f"Lavalink node directory returned HTTP {resp.status}")
                    return []
                raw = await resp.text()
                entries = json.loads(raw)
    except Exception as e:
        logger.warning(f"Could not fetch the Lavalink node directory: {err_text(e)}")
        return []

    nodes: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        version = entry.get("version") or entry.get("restVersion")
        if version not in ("v4", "4"):
            continue
        host = (entry.get("host") or "").strip()
        if not host:
            continue
        port = entry.get("port") or 2333
        secure = bool(entry.get("secure"))
        scheme = "https" if secure else "http"
        uri = f"{scheme}://{host}:{port}"
        if uri in seen:
            continue
        seen.add(uri)
        nodes.append((uri, entry.get("password") or "youshallnotpass"))

    logger.info(f"Lavalink node directory returned {len(nodes)} v4 node(s).")
    _public_nodes_cache = (now, nodes)
    return nodes[:limit]


async def discover_working_node(timeout: float = 20.0) -> Optional[tuple[str, str]]:
    """
    Find a public Lavalink node that actually works right now.

    Every candidate is probed in parallel, so the whole scan costs about as much
    as the slowest single probe instead of the sum of all of them.
    """
    nodes = await fetch_public_nodes()
    if not nodes:
        return None

    async def _probe(uri: str, password: str) -> Optional[str]:
        ok, _ = await probe_candidate_node(uri, password, timeout=min(timeout, 9.0))
        return uri if ok else None

    results = await asyncio.gather(
        *[_probe(uri, pw) for uri, pw in nodes],
        return_exceptions=True,
    )

    for (uri, _), result in zip(nodes, results):
        if isinstance(result, str):
            logger.info(f"Discovered a working public Lavalink node: {uri}")
            return uri, dict(nodes)[uri]

    logger.warning("No public Lavalink node passed the full health check.")
    return None


async def probe_node(
    target: Any,
    password_or_timeout: Any = None,
    timeout: float = 6.0,
    user_id: str = "100000000000000001",
) -> bool:
    """
    Verify that a node's REST API actually answers.

    Accepts either an active ``wavelink.Node`` instance (or any object exposing
    ``uri`` and ``_session``), or a ``(uri, password)`` string pair.
    Returns True if the node is healthy and responsive, False otherwise.
    """
    if isinstance(target, str):
        password = str(password_or_timeout) if password_or_timeout is not None else ""
        ok, _ = await probe_candidate_node(target, password, timeout=timeout, user_id=user_id)
        return ok

    if isinstance(password_or_timeout, (int, float)):
        timeout = float(password_or_timeout)

    session = getattr(target, "_session", None)
    if session is None or getattr(session, "closed", False):
        return False

    # `/v4/info` is the Lavalink v4 information endpoint (`/v4/version` does not
    # exist in v4 and answers 404).
    uri = f"{getattr(target, 'uri', '')}/v4/info"

    # `Node.headers` asserts that a client is attached, which is not the case for
    # a node that never finished connecting. Fall back to an empty header set:
    # the node then answers 401 instead of 200, which still proves the REST API
    # is responsive.
    try:
        headers = target.headers
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


def _ws_url(uri: str) -> str:
    """Build the websocket URL for a Lavalink node URI."""
    url = uri.rstrip("/")
    if url.startswith("https://"):
        url = "wss://" + url[len("https://"):]
    elif url.startswith("http://"):
        url = "ws://" + url[len("http://"):]
    return url + "/v4/websocket"


async def check_websocket(
    uri: str,
    password: str,
    timeout: float = 8.0,
    user_id: str = "100000000000000001",
) -> tuple[bool, str]:
    """
    Verify that a node accepts a WebSocket upgrade before we rely on it.

    Wavelink swallows the handshake error and leaves the node in CONNECTING
    forever, so without this pre-flight the only symptom is a vague timeout.
    A reverse proxy that does not forward the Upgrade headers answers with
    HTTP 400, a wrong password with 401/403 - both are actionable.

    The ``User-Id`` header is mandatory: some nodes reject the handshake with
    401 when it is missing, even though the password is correct.
    """
    headers = {
        "Authorization": password,
        "User-Id": str(user_id),
        "Client-Name": "Wavelink/3.5.2",
    }
    try:
        timeout_cfg = aiohttp.ClientTimeout(total=timeout, connect=timeout)
        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
            async with session.ws_connect(
                _ws_url(uri),
                headers=headers,
            ):
                return True, "websocket handshake ok"
    except aiohttp.WSServerHandshakeError as e:
        return False, f"websocket rejected with HTTP {e.status}"
    except asyncio.TimeoutError:
        return False, "websocket handshake timed out"
    except Exception as e:
        return False, err_text(e)


async def probe_candidate_node(
    uri: str,
    password: str,
    timeout: float = 8.0,
    user_id: str = "100000000000000001",
) -> tuple[bool, str]:
    """
    Fully verify a Lavalink node: websocket 'ready' + REST + YouTube source.

    The handshake alone is not enough. A Lavalink node closes the connection
    right after the upgrade unless the ``User-Id`` header is present, and the
    session (which holds the players) is only created when the node sends its
    ``ready`` op. A node that answers the handshake but never sends ``ready``
    cannot play anything.
    """
    headers = {
        "Authorization": password,
        # Lavalink closes the socket without this header, and it also rejects
        # non-snowflake values, so a realistic id is used for the probe.
        "User-Id": str(user_id),
        "Client-Name": "Wavelink/3.5.2",
    }
    try:
        timeout_cfg = aiohttp.ClientTimeout(total=timeout, connect=timeout)
        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
            try:
                async with session.ws_connect(_ws_url(uri), headers=headers) as ws:
                    msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
                    if msg.type is not aiohttp.WSMsgType.TEXT:
                        return False, "websocket closed before the 'ready' op"
                    try:
                        payload = json.loads(msg.data)
                    except Exception:
                        return False, "websocket sent an invalid payload"
                    if payload.get("op") != "ready":
                        return False, f"websocket sent '{payload.get('op')}' instead of 'ready'"
            except aiohttp.WSServerHandshakeError as e:
                return False, f"websocket rejected with HTTP {e.status}"
            except asyncio.TimeoutError:
                return False, "websocket handshake timed out"
            except Exception as e:
                return False, err_text(e)

            # The REST API must answer too and expose the YouTube source.
            try:
                async with session.get(
                    f"{uri.rstrip('/')}/v4/info", headers=headers, timeout=timeout
                ) as resp:
                    if resp.status != 200:
                        return False, f"REST /v4/info returned HTTP {resp.status}"
                    info = json.loads(await resp.text())
            except asyncio.TimeoutError:
                return False, "REST API timed out"
            except Exception as e:
                return False, f"REST {err_text(e)}"

            sources = info.get("sourceManagers") or []
            plugins = [p.get("name") for p in (info.get("plugins") or []) if isinstance(p, dict)]
            has_youtube = "youtube" in sources or any("youtube" in str(p).lower() for p in plugins)
            if not has_youtube:
                return False, "node has no YouTube source"

            return True, "node is fully operational"

    except Exception as e:
        return False, err_text(e)


async def connect_lavalink_node(
    bot: Optional["discord.Client"] = None,
    *,
    inactive_player_timeout: int = 300,
    allow_discovery: bool = True,
) -> wavelink.Node:
    """
    Connect to the first reachable Lavalink node.

    Order:
      1. the configured primary node
      2. the configured fallback nodes (LAVALINK_FALLBACK_URIS)
      3. a working node discovered from the community directory

    Wavelink's ``Pool.connect`` swallows connection errors and only registers
    the node on success, so the real connection state is verified explicitly
    afterwards. A node is only accepted when its websocket delivers the 'ready'
    op AND its REST API answers - a node whose REST is hung cannot play music.
    """
    from src.core.config import Config

    failures: list[str] = []
    tried: set[str] = set()

    async def _try(uri: str, password: str) -> Optional[wavelink.Node]:
        if uri in tried:
            return None
        tried.add(uri)

        # Fast pre-flight. A node whose websocket is rejected answers in a
        # fraction of a second, while a full connect attempt would burn the
        # whole connect timeout before failing.
        ws_ok, ws_reason = await check_websocket(uri, password)
        if not ws_ok:
            failures.append(f"{uri} -> {ws_reason}")
            logger.warning(f"Lavalink node {uri} unusable: {ws_reason}")
            return None

        node = create_lavalink_node(
            uri,
            password,
            inactive_player_timeout=inactive_player_timeout,
        )
        reason: Optional[str] = None
        try:
            await asyncio.wait_for(
                wavelink.Pool.connect(nodes=[node], client=bot),
                timeout=LAVALINK_CONNECT_TIMEOUT,
            )
        except Exception as e:
            reason = err_text(e)
        else:
            # Pool.connect logs connection errors instead of raising them, so the
            # real state has to be verified explicitly.
            for _ in range(10):
                if node.status == wavelink.NodeStatus.CONNECTED:
                    break
                await asyncio.sleep(0.5)

            if node.status == wavelink.NodeStatus.CONNECTED:
                if await probe_node(node):
                    logger.info(f"Connected to Lavalink node {uri}")
                    return node
                reason = "REST API unresponsive"
            else:
                reason = f"status={getattr(node.status, 'name', node.status)}"

        await close_node(node)
        failures.append(f"{uri} -> {reason}")
        logger.warning(f"Lavalink node {uri} could not be used: {reason}")
        return None

    # 1 + 2: configured nodes
    for uri, password in candidates():
        node = await _try(uri, password)
        if node is not None:
            return node

    # 3: community directory - only when it is enabled and no configured node worked
    if allow_discovery and Config.LAVALINK_AUTO_DISCOVER:
        discovered = await discover_working_node()
        if discovered is not None:
            node = await _try(*discovered)
            if node is not None:
                return node

    detail = "; ".join(failures) if failures else "no URI configured"
    raise LavalinkUnavailable(f"No reachable Lavalink node ({detail})")
