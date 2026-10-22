"""
Kyro Discord Bot - Hardened Lavalink Node Factory
==================================================

Wavelink creates its own ``aiohttp.ClientSession`` with the library default
timeout of **300 seconds**. When the Lavalink node is slow or unreachable,
every REST call then blocks for five minutes.

Kyro awaits several of those calls directly (``skip``, ``play``, ``stop``,
``move_to``), so a single unresponsive node used to freeze the whole music
subsystem: the command that triggered it never returned and the per-guild
``_advance_lock`` / ``_connect_lock`` stayed held for the entire duration,
making every later ``?skip``, ``?jump`` and ``?play`` wait behind it.

Every node Kyro creates goes through this factory so the transport always
fails fast instead of hanging, and the failure surfaces as a normal, handled
exception that the MusicAgent can heal.
"""

from __future__ import annotations

import aiohttp
import wavelink

# Total request budget, TCP connect budget and socket-read budget for every
# call made against the Lavalink REST API.
LAVALINK_HTTP_TIMEOUT = aiohttp.ClientTimeout(
    total=12.0,
    connect=5.0,
    sock_read=8.0,
)

# Budget for a single player operation (skip / play / stop / move).
LAVALINK_OP_TIMEOUT = 8.0

# Budget for starting a track (play does a bit more work than skip).
LAVALINK_PLAY_TIMEOUT = 12.0

# Budget for the node websocket handshake (it shares the same session).
LAVALINK_CONNECT_TIMEOUT = 10.0

# Overall budget for resolving a playable (search cascade across several
# strategies). Without this a single unresolvable track could keep the caller
# waiting for well over a minute.
LAVALINK_RESOLVE_TIMEOUT = 25.0


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
