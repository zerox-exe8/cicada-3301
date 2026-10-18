from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import logging
import os
import time
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord.ext import tasks

from src.core.config import Config
from src.sentinel.models import Incident, IncidentSeverity, SubsystemType

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Sentinel")

try:
    import psutil
except ImportError:
    psutil = None


class KyroSentinel:
    """
    Autonomous In-Bot SRE Sentinel Agent for Kyro Bot.
    Runs non-blocking live diagnostics, auto-recovers broken subsystems,
    and logs critical incident telemetry without taking the bot offline.
    """

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.incidents: deque[Incident] = deque(maxlen=50)
        self.start_time: datetime = datetime.now(timezone.utc)
        self.is_running: bool = False
        self._circuit_breakers: dict[str, int] = {}
        self._last_circuit_reset: float = time.time()
        self._healed_counts: dict[str, int] = {
            "voice": 0,
            "music": 0,
            "database": 0,
            "gateway": 0,
        }

    def start(self) -> None:
        """Start the background autonomous watchdog loop."""
        if not self.is_running:
            self.is_running = True
            self.watchdog_loop.start()
            logger.info("Kyro Autonomous Sentinel SRE Agent started successfully.")

    def stop(self) -> None:
        """Stop the background watchdog loop."""
        if self.is_running:
            self.is_running = False
            self.watchdog_loop.cancel()
            logger.info("Kyro Autonomous Sentinel SRE Agent stopped.")

    def record_incident(
        self,
        subsystem: SubsystemType,
        severity: IncidentSeverity,
        title: str,
        details: str,
        action_taken: str = "",
        resolved: bool = True,
        guild_id: Optional[int] = None,
    ) -> Incident:
        """Record an incident into circular telemetry buffer and log appropriately."""
        incident_id = f"INC-{int(time.time() * 1000) % 1000000:06d}"
        inc = Incident(
            id=incident_id,
            subsystem=subsystem,
            severity=severity,
            title=title,
            details=details,
            guild_id=guild_id,
            action_taken=action_taken,
            resolved=resolved,
            timestamp=datetime.now(timezone.utc),
        )
        self.incidents.append(inc)

        if resolved and action_taken:
            sub_key = subsystem.value.lower()
            if sub_key in self._healed_counts:
                self._healed_counts[sub_key] += 1

        log_msg = f"[Sentinel][{incident_id}][{subsystem.value}][{severity.value}] {title}: {details} | Action: {action_taken or 'None'} | Resolved: {resolved}"
        if severity == IncidentSeverity.CRITICAL:
            logger.error(log_msg)
        elif severity == IncidentSeverity.WARNING:
            logger.warning(log_msg)
        else:
            logger.info(log_msg)

        return inc

    # ── Watchdog Core Loop ──

    @tasks.loop(seconds=30.0)
    async def watchdog_loop(self) -> None:
        """Periodic non-blocking system health check & self-healing execution."""
        # 1. Reset circuit breakers every 5 minutes
        now = time.time()
        if now - self._last_circuit_reset > 300:
            self._circuit_breakers.clear()
            self._last_circuit_reset = now

        # 2. Database Health Check
        await self._check_database_health()

        # 3. Lavalink Node Health Check
        await self._check_lavalink_health()

        # 4. Gateway Latency & Heartbeat Check
        self._check_gateway_health()

    @watchdog_loop.before_loop
    async def before_watchdog_loop(self) -> None:
        await self.bot.wait_until_ready()

    # ── Subsystem Checkers ──

    async def _check_database_health(self) -> None:
        """Verify PostgreSQL pool responsiveness and auto-heal if dropped."""
        t_start = time.perf_counter()
        try:
            if hasattr(self.bot, "db") and self.bot.db:
                await self.bot.db.fetch_one("SELECT 1;")
                latency_ms = (time.perf_counter() - t_start) * 1000
                if latency_ms > 2000:
                    self.record_incident(
                        SubsystemType.DATABASE,
                        IncidentSeverity.WARNING,
                        "Slow Database Latency",
                        f"Query execution took {latency_ms:.1f}ms (>2000ms threshold)",
                        action_taken="Monitored query latency",
                        resolved=True,
                    )
        except Exception as e:
            cb_key = "db_pool"
            fails = self._circuit_breakers.get(cb_key, 0) + 1
            self._circuit_breakers[cb_key] = fails

            if fails <= 3:
                logger.warning(f"Sentinel: Database ping failed ({e}), initiating auto-heal...")
                try:
                    await self.heal_database()
                    self.record_incident(
                        SubsystemType.DATABASE,
                        IncidentSeverity.WARNING,
                        "Database Pool Disconnected",
                        str(e),
                        action_taken="Auto-healed connection pool via exponential backoff",
                        resolved=True,
                    )
                except Exception as heal_err:
                    self.record_incident(
                        SubsystemType.DATABASE,
                        IncidentSeverity.CRITICAL,
                        "Database Auto-Heal Failed",
                        f"Original: {e} | Heal error: {heal_err}",
                        action_taken="Escalated to developer alert",
                        resolved=False,
                    )
            else:
                self.record_incident(
                    SubsystemType.DATABASE,
                    IncidentSeverity.CRITICAL,
                    "Database Circuit Breaker Tripped",
                    f"Repeated database failures ({fails} attempts in 5m)",
                    action_taken="Paused auto-heal to prevent loop thrashing",
                    resolved=False,
                )

    async def _check_lavalink_health(self) -> None:
        """Verify Wavelink Lavalink Node connection and auto-reconnect if dropped."""
        import wavelink
        try:
            node = wavelink.Pool.get_node()
            if node.status != wavelink.NodeStatus.CONNECTED:
                await self._trigger_lavalink_reconnect(reason=f"Node status is {node.status.name}")
        except Exception:
            await self._trigger_lavalink_reconnect(reason="No node found in Wavelink Pool")

    async def _trigger_lavalink_reconnect(self, reason: str) -> None:
        """Auto-reconnect Lavalink node with circuit breaker protection."""
        cb_key = "lavalink_node"
        fails = self._circuit_breakers.get(cb_key, 0) + 1
        self._circuit_breakers[cb_key] = fails

        if fails <= 3:
            logger.warning(f"Sentinel: Lavalink node offline ({reason}), auto-reconnecting...")
            try:
                await self.heal_lavalink()
                self.record_incident(
                    SubsystemType.MUSIC,
                    IncidentSeverity.WARNING,
                    "Lavalink Node Recovered",
                    reason,
                    action_taken="Re-established Wavelink node connection pool",
                    resolved=True,
                )
            except Exception as e:
                self.record_incident(
                    SubsystemType.MUSIC,
                    IncidentSeverity.CRITICAL,
                    "Lavalink Reconnect Failed",
                    str(e),
                    action_taken="Retrying on next cycle",
                    resolved=False,
                )
        else:
            self.record_incident(
                SubsystemType.MUSIC,
                IncidentSeverity.CRITICAL,
                "Lavalink Circuit Breaker Tripped",
                f"Lavalink reconnect failed {fails} times",
                action_taken="Circuit breaker open, awaiting server restore",
                resolved=False,
            )

    def _check_gateway_health(self) -> None:
        """Monitor Discord WebSocket latency."""
        latency = self.bot.latency
        if latency != float("inf") and latency > 0.8:
            self.record_incident(
                SubsystemType.GATEWAY,
                IncidentSeverity.WARNING,
                "High Discord Gateway Latency",
                f"Websocket ping spiked to {latency * 1000:.1f}ms",
                action_taken="Logged latency metric",
                resolved=True,
            )

    # ── Self-Healing Actuators ──

    async def heal_database(self) -> None:
        """Force recycle database connection pool."""
        if hasattr(self.bot, "db") and self.bot.db and hasattr(self.bot.db, "_heal_pool"):
            await self.bot.db._heal_pool()

    async def heal_lavalink(self) -> None:
        """Force re-establish Wavelink node connection."""
        import wavelink
        try:
            node = wavelink.Node(
                uri=Config.LAVALINK_URI,
                password=Config.LAVALINK_PASSWORD,
                inactive_player_timeout=300,
            )
            await wavelink.Pool.connect(nodes=[node], client=self.bot)
            for _ in range(10):
                if node.status == wavelink.NodeStatus.CONNECTED:
                    break
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Sentinel: Lavalink node heal error: {e}")
            raise

    async def heal_stuck_voice_client(self, guild: discord.Guild) -> bool:
        """Cleanly reset a zombie/hung voice client in a guild."""
        try:
            vc = guild.voice_client
            if vc:
                try:
                    await vc.disconnect(force=True)
                except Exception:
                    pass
                try:
                    vc.cleanup()
                except Exception:
                    pass
            music_cog = self.bot.get_cog("Music")
            if music_cog and hasattr(music_cog, "controller"):
                player = music_cog.controller.get_player(guild.id)
                if player:
                    player.voice_client = None
            self.record_incident(
                SubsystemType.VOICE,
                IncidentSeverity.INFO,
                "Zombie Voice Client Cleaned",
                f"Cleaned stuck voice client in guild {guild.id}",
                action_taken="Forcefully disconnected and cleaned VC state",
                resolved=True,
                guild_id=guild.id,
            )
            return True
        except Exception as e:
            logger.error(f"Sentinel: Error healing voice client for guild {guild.id}: {e}")
            return False

    # ── Telemetry & Diagnostics ──

    def get_health_report(self) -> dict[str, Any]:
        """Compile complete real-time telemetry metrics."""
        now_dt = datetime.now(timezone.utc)
        uptime_seconds = int((now_dt - self.start_time).total_seconds())
        hours, rem = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(rem, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        # Memory usage
        ram_mb = 0.0
        cpu_percent = 0.0
        if psutil:
            try:
                p = psutil.Process(os.getpid())
                ram_mb = p.memory_info().rss / (1024 * 1024)
                cpu_percent = p.cpu_percent(interval=None)
            except Exception:
                pass

        # Wavelink Node status
        node_status = "OFFLINE"
        active_players = 0
        try:
            import wavelink
            node = wavelink.Pool.get_node()
            node_status = node.status.name if node else "OFFLINE"
        except Exception:
            node_status = "OFFLINE"

        music_cog = self.bot.get_cog("Music")
        if music_cog and hasattr(music_cog, "controller"):
            players = getattr(music_cog.controller, "_players", {})
            active_players = sum(1 for p in players.values() if getattr(p, "is_playing", False))

        # Overall Status
        has_critical = any(not inc.resolved and inc.severity == IncidentSeverity.CRITICAL for inc in self.incidents)
        has_warning = any(not inc.resolved for inc in self.incidents)
        overall_health = "CRITICAL" if has_critical else ("DEGRADED" if has_warning else "HEALTHY")

        return {
            "status": overall_health,
            "uptime": uptime_str,
            "ram_mb": f"{ram_mb:.1f} MB",
            "cpu_percent": f"{cpu_percent:.1f}%",
            "gateway_latency_ms": f"{self.bot.latency * 1000:.1f} ms" if self.bot.latency != float("inf") else "Offline",
            "lavalink_node": node_status,
            "active_audio_streams": active_players,
            "guild_count": len(self.bot.guilds),
            "healed_counts": dict(self._healed_counts),
            "total_incidents": len(self.incidents),
            "recent_incidents": list(self.incidents)[-5:],
        }
