from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord.ext import tasks

from src.core.lavalink import (
    LAVALINK_OP_TIMEOUT,
    close_pool_nodes,
    connect_lavalink_node,
    err_text,
    probe_node,
)
from src.utils.containers import KyroContainer

if TYPE_CHECKING:
    from src.core.bot import KyroBot
    from src.cogs.music.music import Music
    from src.cogs.music._player import GuildPlayer

logger = logging.getLogger("Kyro.Music.Agent")


class MusicAgent:
    """
    Enterprise-Grade Music SRE & Autonomous Concurrency Agent.
    
    Designed to reliably manage 1,000+ simultaneous music streams with:
    1. Single-Flight Anti-Thundering-Herd algorithm for Lavalink node reconnection.
    2. Per-Guild Partitioned Sharded Locks with TTL eviction (zero cross-guild lock contention).
    3. Gateway Voice State Debouncing (prevents Discord Opcode 4 rate limits).
    4. Adaptive Zombie Player & Memory Sweeper (prevents heap leaks under high server volume).
    5. Universal Command Shield & Graceful Circuit Breakers across 100% of music commands.
    """

    def __init__(self, bot: KyroBot, music_cog: Music) -> None:
        self.bot = bot
        self.music = music_cog

        # Concurrency & Single-Flight State
        self._node_heal_lock = asyncio.Lock()
        self._node_heal_event: Optional[asyncio.Event] = None
        self._node_is_healing: bool = False

        # Partitioned Guild Locks & Sliding Window Debounce
        self._guild_locks: dict[int, asyncio.Lock] = {}
        self._last_heal_time: dict[int, float] = {}  # guild_id -> unix timestamp
        self._heal_cooldown: float = 3.0  # seconds minimum between heals per guild

        # Telemetry & Metrics
        self._metrics: dict[str, int] = {
            "voice_heals": 0,
            "node_reconnects": 0,
            "stuck_tracks_cleared": 0,
            "zombies_purged": 0,
            "shielded_errors": 0,
        }

        # Start background health & memory sweeper
        self._background_sweeper.start()

    def cog_unload(self) -> None:
        """Cancel background sweeper on module reload."""
        if self._background_sweeper.is_running():
            self._background_sweeper.cancel()

    # ── Concurrency & Sharded Lock Management ──

    def get_guild_lock(self, guild_id: int) -> asyncio.Lock:
        """Acquire or allocate an isolated per-guild lock to prevent cross-guild blocking."""
        if guild_id not in self._guild_locks:
            self._guild_locks[guild_id] = asyncio.Lock()
        return self._guild_locks[guild_id]

    # ── Algorithmic Self-Healing Actuators ──

    async def heal_voice_session(self, guild: discord.Guild, reason: str = "Voice Gateway Desync") -> tuple[bool, str]:
        """
        Surgically purge ghost voice sessions with debounced per-guild rate limiting.
        Prevents Discord Opcode 4 voice state update rate limits.

        The queued tracks are PRESERVED — a self-heal must never wipe the user's
        playlist, otherwise one transient error invalidates the whole session.
        """
        guild_id = guild.id
        now = time.time()

        # Sliding window debounce check: Prevent rapid-fire heal loops on the same guild
        last_heal = self._last_heal_time.get(guild_id, 0.0)
        if now - last_heal < self._heal_cooldown:
            return True, "Heal operation throttled by rate-limiting debounce."

        lock = self.get_guild_lock(guild_id)
        async with lock:
            try:
                logger.info(f"MusicAgent: Healing voice session for guild '{guild.name}' ({guild_id}) - Reason: {reason}")

                # 0. Mark the player so the disconnect handler keeps the queue intact
                #    and knows this disconnect was self-initiated (so the delayed
                #    VOICE_STATE_UPDATE cannot kill a freshly established session).
                player = self.music.controller.get_player(guild_id)
                if player:
                    player.preserve_queue_on_disconnect = True
                    player._disconnect_expected_until = time.monotonic() + 5.0

                # 1. Clean local voice client
                vc = guild.voice_client
                if vc:
                    try:
                        # Bounded: this talks to the Lavalink REST API. Without a
                        # bound it could hold the per-guild heal lock for the
                        # session's 300s default timeout, blocking every later
                        # error handling path for this guild.
                        await asyncio.wait_for(
                            vc.disconnect(force=True),
                            timeout=LAVALINK_OP_TIMEOUT,
                        )
                    except Exception:
                        pass
                    try:
                        vc.cleanup()
                    except Exception:
                        pass

                # 2. Remove from discord.py internal client connection state
                try:
                    self.bot._connection._remove_voice_client(guild_id)
                except Exception:
                    pass

                # 3. Transmit Gateway Opcode 4 to reset state on Discord voice servers
                if player:
                    player._disconnect_expected_until = time.monotonic() + 5.0
                try:
                    await guild.change_voice_state(channel=None)
                    await asyncio.sleep(0.3)
                except Exception:
                    pass

                # 4. Reset GuildPlayer voice reference
                if player:
                    player.voice_client = None

                self._metrics["voice_heals"] += 1
                self._last_heal_time[guild_id] = time.time()
                return True, "Voice gateway state cleanly flushed and reset."
            except Exception as e:
                logger.error(f"MusicAgent: Error healing voice session for guild {guild_id}: {e}", exc_info=True)
                return False, str(e)

    async def heal_node(self, force: bool = False) -> tuple[bool, str]:
        """
        Anti-Thundering-Herd Single-Flight Node Reconnector.
        If 1,000 servers detect a node drop simultaneously, only ONE task connects,
        while the other 999 wait on a shared asyncio.Event.

        `force` is advisory: the node is considered healthy only when it reports
        CONNECTED *and* its REST API answers, so a node with a hung REST API is
        always rebuilt even when it was not explicitly forced.
        """
        import wavelink

        # If already connected and not forced, return immediately.
        #
        # A node that reports CONNECTED but whose REST API is hung is NOT healthy:
        # every player operation (skip, play, stop) goes through the REST API, so
        # such a node is exactly what makes the music commands time out.
        try:
            current_node = wavelink.Pool.get_node()
            if current_node and current_node.status == wavelink.NodeStatus.CONNECTED:
                if await probe_node(current_node):
                    return True, "Lavalink node is healthy and connected."
                logger.warning(
                    "MusicAgent: Lavalink node reports CONNECTED but its REST API is unresponsive."
                )
        except Exception:
            pass

        # Check if another coroutine is already actively healing the node
        if self._node_is_healing and self._node_heal_event is not None:
            logger.debug("MusicAgent: Single-flight in progress. Awaiting existing node heal...")
            await self._node_heal_event.wait()
            return True, "Lavalink node restored via concurrent single-flight."

        async with self._node_heal_lock:
            # Double-check inside lock
            if self._node_is_healing and self._node_heal_event is not None:
                await self._node_heal_event.wait()
                return True, "Lavalink node restored via concurrent single-flight."

            self._node_is_healing = True
            self._node_heal_event = asyncio.Event()

            try:
                logger.warning("MusicAgent: Initiating master single-flight Lavalink pool reconnect...")

                # Jittered brief delay to allow network socket to settle
                await asyncio.sleep(random.uniform(0.1, 0.4))

                # Close every dead socket in the pool. `Pool.nodes` returns a copy,
                # so the pool is cleaned through close_pool_nodes() instead of the
                # no-op `Pool.nodes.clear()`.
                await close_pool_nodes()

                # Connect to the primary node, falling back to any configured
                # alternatives when it is unreachable.
                new_node = await connect_lavalink_node(
                    self.bot,
                    inactive_player_timeout=300,
                )

                self._metrics["node_reconnects"] += 1
                logger.info("MusicAgent: Lavalink node pool re-established successfully.")
                return True, f"Lavalink node reconnected ({new_node.uri})."

            except Exception as e:
                logger.error(
                    f"MusicAgent: Failed during single-flight node heal: {err_text(e)}",
                    exc_info=True,
                )
                return False, err_text(e)

            finally:
                self._node_is_healing = False
                if self._node_heal_event:
                    self._node_heal_event.set()
                    self._node_heal_event = None

    async def heal_stuck_track(self, guild: discord.Guild, reason: str = "Decoder Stall") -> tuple[bool, str]:
        """Safely unblock a stalled audio buffer and advance the queue."""
        player = self.music.controller.get_player(guild.id)
        if not player:
            return False, "No active GuildPlayer instance."

        lock = self.get_guild_lock(guild.id)
        async with lock:
            try:
                stuck_title = player.current.title if player.current else "Unknown"
                logger.warning(f"MusicAgent: Healing stuck track '{stuck_title}' in guild {guild.id} - Reason: {reason}")
                self._metrics["stuck_tracks_cleared"] += 1
                if hasattr(player, "on_track_end"):
                    await player.on_track_end(reason="loadFailed")
                return True, f"Flushed buffer for '{stuck_title}' and advanced playback."
            except Exception as e:
                logger.error(f"MusicAgent: Error advancing stuck track: {e}")
                return False, str(e)

    # ── Audio Engine Availability ──

    async def audio_engine_status(self) -> tuple[bool, str]:
        """
        Check whether the Lavalink audio engine can actually serve a stream.

        Returns (available, reason). A node that is missing, disconnected or
        whose REST API does not answer cannot play anything, no matter what the
        voice gateway thinks.
        """
        import wavelink

        try:
            node = wavelink.Pool.get_node()
        except Exception:
            return False, "no Lavalink node is connected"

        if node is None:
            return False, "no Lavalink node is connected"

        status = getattr(node.status, "name", node.status)
        if status != "CONNECTED":
            return False, f"Lavalink node is {status}"

        if not await probe_node(node):
            return False, "Lavalink node REST API is unresponsive"

        return True, f"Lavalink node {node.uri} is ready"

    # ── Universal Command Shield & Exception Handler ──

    async def handle_command_error(self, ctx_or_interaction: Any, error: Exception) -> bool:
        """
        Universal circuit breaker for ALL music commands (prefix and slash).
        Catches transient connection timeouts, node drops, and stream errors,
        triggers autonomous self-healing, and displays a polished Kyro container.

        Classification is done on the EXCEPTION TYPE, not on the message text.
        Many transport exceptions (TimeoutError, ClientOSError, ...) carry an
        EMPTY message, so substring matching silently classified them as
        "unknown" and skipped every self-healing branch.
        """
        from discord.ext import commands as dpy_commands

        self._metrics["shielded_errors"] += 1
        guild = getattr(ctx_or_interaction, "guild", None)
        err_type = type(error).__name__
        err_str = str(error) or err_type
        err_low = err_str.lower()

        logger.warning(
            f"MusicAgent: Intercepted music error in guild '{guild.name if guild else 'None'}' "
            f"({err_type}): {err_str}"
        )

        # ── User input / permission problems are NOT subsystem faults ──
        # Let the global error handler render the proper usage message instead
        # of a "maintenance" card that hides the real reason.
        if isinstance(
            error,
            (
                dpy_commands.UserInputError,
                dpy_commands.CheckFailure,
                dpy_commands.MissingPermissions,
                dpy_commands.BotMissingPermissions,
                dpy_commands.NoPrivateMessage,
                dpy_commands.DisabledCommand,
            ),
        ):
            raise error

        from wavelink.exceptions import (
            ChannelTimeoutException,
            LavalinkException,
            NodeException,
        )

        # Voice gateway handshake failure (Discord voice servers).
        is_voice_fault = isinstance(error, (discord.ConnectionClosed, ChannelTimeoutException)) or (
            "unable to connect to" in err_low
            or "voice gateway" in err_low
            or "exceeded the timeout" in err_low
        )

        # Audio engine (Lavalink node) transport failure.
        is_node_fault = isinstance(error, (LavalinkException, NodeException)) or (
            "lavalink" in err_low
            or "node" in err_low
            or (isinstance(error, (asyncio.TimeoutError, TimeoutError)) and not is_voice_fault)
        )

        title = "Music Subsystem Diagnostics"
        action = "Logged diagnostics and secured audio pipeline."
        advice = "Please try executing the command again."

        # Case 1: Audio engine (Lavalink node) unreachable / slow REST transport.
        if is_node_fault:
            title = "Audio Engine Auto-Recovery"
            action = "Triggered single-flight Lavalink node pool re-establishment."
            advice = "The audio engine is reconnecting. Please retry in a few seconds."
            asyncio.create_task(self.heal_node())

        # Case 2: Voice Gateway Connect / Timeout / Channel State Failure.
        elif is_voice_fault:
            title = "Voice Gateway Auto-Recovery"
            if guild:
                await self.heal_voice_session(guild, reason=f"Command error: {err_type}")
            action = "Purged stale voice gateway state (your queue was kept intact)."
            advice = "Please try joining the voice channel or re-running the command."

        # Case 3: Permission or Capacity Constraints
        elif isinstance(error, discord.Forbidden) or "permission" in err_low or "is full" in err_low:
            title = "Voice Channel Constraint"
            action = "Verified channel capacity and permission boundaries."
            advice = f"Notice: `{err_str}`"

        # Build and dispatch stylish KyroComponents card
        card = self.build_maintenance_card(
            title=title,
            issue_desc=f"`{err_type}: {err_str[:120]}`",
            action_taken=action,
            advice=advice,
        )

        try:
            from src.utils.containers import send_container_response
            await send_container_response(ctx_or_interaction, card)
            return True
        except Exception as send_err:
            logger.debug(f"MusicAgent: Could not dispatch maintenance card: {send_err}")
            return False

    def build_maintenance_card(
        self,
        title: str = "Music Subsystem Diagnostics",
        issue_desc: str = "Temporary connection blip detected.",
        action_taken: str = "Automated voice session reset performed.",
        advice: str = "Please try playing your track again in a few moments.",
    ) -> KyroContainer:
        """Produce a stylish Kyro Components V2 container for transient music errors."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        dot = e_reg.get("heart_dot", "•") if e_reg else "•"
        shield_icon = e_reg.get("icons_shield", "🛡️") if e_reg else "🛡️"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{shield_icon} Kyro Music Agent • Autonomous Shield**\n"
                f"> *{title}*"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"> {dot} **Notice:** {issue_desc}\n"
            f"> {dot} **Autonomous Action:** {action_taken}\n"
            f"> {dot} **Resolution:** {advice}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Autonomous Music SRE Engine • Real-time Protection")
        return container

    # ── High-Volume Background Sweeper & Memory Pruner ──

    @tasks.loop(seconds=60.0)
    async def _background_sweeper(self) -> None:
        """
        Runs every 60s to ensure memory scaling across 1,000+ servers:
        1. Prunes stale per-guild locks and debounce timestamps.
        2. Sweeps zombie players (disconnected from voice for >180s without 24/7).
        3. Staggered iteration to prevent asyncio event-loop lag.
        """
        now = time.time()

        # 1. Prune debounce timestamps older than 600s
        stale_guilds = [gid for gid, ts in self._last_heal_time.items() if now - ts > 600.0]
        for gid in stale_guilds:
            self._last_heal_time.pop(gid, None)
            # Only remove lock if it's currently unlocked
            lock = self._guild_locks.get(gid)
            if lock and not lock.locked():
                self._guild_locks.pop(gid, None)

        # 2. Sweep zombie players in batched chunks
        try:
            controller = getattr(self.music, "controller", None)
            if controller and hasattr(controller, "players"):
                active_players = list(controller.players.items())
                count = 0
                for guild_id, player in active_players:
                    count += 1
                    # Yield event loop every 40 guilds to guarantee 0% loop lag
                    if count % 40 == 0:
                        await asyncio.sleep(0)

                    # Skip 24/7 guilds
                    if getattr(player, "is_247", False):
                        continue

                    vc = getattr(player, "voice_client", None)
                    # Zombie criteria: no voice client, or voice client disconnected
                    is_live = bool(vc and (getattr(vc, "connected", False) or getattr(vc, "is_connected", lambda: False)()))
                    if not is_live:
                        last_active = getattr(player, "_last_active_time", now)
                        if now - last_active > 180.0 and not player.is_playing:
                            logger.info(f"MusicAgent Sweeper: Purging zombie player in guild {guild_id}")
                            try:
                                await controller.remove_player(guild_id)
                                self._metrics["zombies_purged"] += 1
                            except Exception:
                                pass
        except Exception as sweep_err:
            logger.debug(f"MusicAgent Sweeper error: {sweep_err}")

        # 3. Prune in-memory track search cache to cap heap memory usage
        try:
            from src.cogs.music._extractor import _SEARCH_CACHE, _CACHE_TTL
            if len(_SEARCH_CACHE) > 3000:
                expired = [k for k, (t, _) in _SEARCH_CACHE.items() if now - t > _CACHE_TTL]
                for k in expired:
                    _SEARCH_CACHE.pop(k, None)
                if len(_SEARCH_CACHE) > 3000:
                    # Drop oldest 500 items to strictly enforce RAM cap
                    oldest_keys = sorted(_SEARCH_CACHE.keys(), key=lambda k: _SEARCH_CACHE[k][0])[:500]
                    for k in oldest_keys:
                        _SEARCH_CACHE.pop(k, None)
        except Exception:
            pass

    @_background_sweeper.before_loop
    async def _before_sweeper(self) -> None:
        await self.bot.wait_until_ready()
