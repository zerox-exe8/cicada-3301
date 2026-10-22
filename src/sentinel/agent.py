from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
import gc
import json
import logging
import os
import re
import time
from typing import TYPE_CHECKING, Any, Optional

import aiohttp
import discord
from discord.ext import tasks

from src.core.lavalink import (
    LAVALINK_OP_TIMEOUT,
    LavalinkUnavailable,
    close_pool_nodes,
    connect_lavalink_node,
    err_text,
    probe_node,
)
from src.sentinel.models import Incident, IncidentSeverity, SubsystemType
from src.utils.containers import KyroContainer, send_container_response

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
    executes Gemini AI Root Cause Analysis (RCA) on anomalous tracebacks,
    sweeps zombie voice clients, and dispatches proactive telemetry alerts.
    """

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.incidents: deque[Incident] = deque(maxlen=50)
        self.start_time: datetime = datetime.now(timezone.utc)
        self.is_running: bool = False
        self._circuit_breakers: dict[str, int] = {}
        self._last_circuit_reset: float = time.time()
        self._last_alert_time: dict[str, float] = {}
        self._lavalink_breaker_open: bool = False
        self._event_loop_lag_ms: float = 0.0
        self._session: Optional[aiohttp.ClientSession] = None
        self._healed_counts: dict[str, int] = {
            "voice": 0,
            "music": 0,
            "database": 0,
            "gateway": 0,
            "memory": 0,
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
            if self._session and not self._session.closed:
                asyncio.create_task(self._session.close())
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
        traceback: Optional[str] = None,
    ) -> Incident:
        """Record an incident into circular telemetry buffer, run AI analysis, and log appropriately."""
        incident_id = f"INC-{int(time.time() * 1000) % 1000000:06d}"
        inc = Incident(
            id=incident_id,
            subsystem=subsystem,
            severity=severity,
            title=title,
            # Never allow an empty incident report: many transport exceptions carry
            # an empty message, which used to produce a completely useless alert.
            details=(details or "").strip() or "no error message (empty exception text)",
            guild_id=guild_id,
            action_taken=action_taken,
            resolved=resolved,
            timestamp=datetime.now(timezone.utc),
            traceback=traceback,
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

        # Trigger background Gemini RCA & proactive alerts for non-trivial incidents
        if severity in (IncidentSeverity.WARNING, IncidentSeverity.CRITICAL) and self.bot.is_ready():
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._process_incident_ai_and_alerts(inc))
            except RuntimeError:
                pass

        return inc

    # ── Gemini AI Autonomous Root Cause Analysis (RCA) ──

    async def _get_session(self) -> aiohttp.ClientSession:
        """Retrieve or create an aiohttp ClientSession for Sentinel."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def analyze_incident_with_gemini(self, incident: Incident) -> Optional[str]:
        """Perform autonomous Root Cause Analysis on an incident using Gemini."""
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return None

        if incident.ai_analysis:
            return incident.ai_analysis

        context_tb = incident.traceback or incident.details
        prompt = (
            "You are the Principal Site Reliability Engineering (SRE) Agent for Kyro Discord Bot.\n"
            "Architecture: discord.py, Wavelink 3 (Lavalink audio), PostgreSQL (asyncpg), Discord Components V2.\n"
            f"Incident ID: {incident.id}\n"
            f"Subsystem: {incident.subsystem.value}\n"
            f"Severity: {incident.severity.value}\n"
            f"Title: {incident.title}\n"
            f"Error / Context:\n{context_tb[:1200]}\n\n"
            "Generate a crisp, actionable Root Cause Analysis strictly in JSON:\n"
            "{\n"
            '  "root_cause": "1-2 concise sentences on what technically failed",\n'
            '  "impact": "1 sentence on affected user features",\n'
            '  "recommended_fix": "1-2 sentences on code fix or autonomous remediation"\n'
            "}"
        )

        models_to_try = ["gemini-flash-lite-latest", "gemma-4-26b-a4b-it", "gemini-flash-latest"]
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
        }

        session = await self._get_session()
        for model in models_to_try:
            endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            try:
                async with session.post(
                    endpoint, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=6.0)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            if parts:
                                raw_txt = parts[0].get("text", "{}").strip()
                                if raw_txt.startswith("```"):
                                    raw_txt = re.sub(r"^```(?:json)?\s*", "", raw_txt)
                                    raw_txt = re.sub(r"\s*```$", "", raw_txt)
                                parsed = json.loads(raw_txt)
                                rca = (
                                    f"**Root Cause:** {parsed.get('root_cause', 'Unknown')}\n"
                                    f"**Impact:** {parsed.get('impact', 'None')}\n"
                                    f"**Remediation:** {parsed.get('recommended_fix', 'Inspect logs')}"
                                )
                                incident.ai_analysis = rca
                                return rca
                    elif resp.status in (404, 503, 429):
                        continue
            except Exception as e:
                logger.debug(f"Sentinel: Notice during Gemini RCA ({model}): {e}")
                continue

        return None

    async def _process_incident_ai_and_alerts(self, incident: Incident) -> None:
        """Background coroutine to generate RCA and dispatch developer notification if needed."""
        try:
            await self.analyze_incident_with_gemini(incident)
        except Exception as e:
            logger.debug(f"Sentinel: Background AI RCA error: {e}")

        # Dispatch alert for CRITICAL incidents or tripped circuit breakers
        if incident.severity == IncidentSeverity.CRITICAL or not incident.resolved:
            await self._dispatch_developer_alert(incident)

    async def _dispatch_developer_alert(self, incident: Incident) -> None:
        """Send a direct proactive notification to bot developers on critical failures."""
        now = time.time()
        sub_key = incident.subsystem.value
        last_alert = self._last_alert_time.get(sub_key, 0)
        # Rate limit: Max 1 alert per subsystem per 5 minutes to prevent spam
        if now - last_alert < 300:
            return

        # A recurring fault (e.g. a Lavalink node that stays down) must not ping
        # the developer every 5 minutes forever. The same title is only sent
        # again after a much longer cooldown, while a DIFFERENT fault is
        # reported immediately.
        title_key = f"{sub_key}:{incident.title}"
        last_same = self._last_alert_time.get(title_key, 0)
        if last_same and now - last_same < 1800:
            return

        self._last_alert_time[sub_key] = now
        self._last_alert_time[title_key] = now

        # Determine target developers
        dev_ids: set[int] = set()
        perm_mgr = getattr(self.bot, "permission_mgr", None)
        if perm_mgr and hasattr(perm_mgr, "_developer_ids"):
            dev_ids.update(perm_mgr._developer_ids)
        if getattr(self.bot, "owner_ids", None):
            dev_ids.update(self.bot.owner_ids)
        elif getattr(self.bot, "owner_id", None):
            dev_ids.add(self.bot.owner_id)

        # Fallback default developer IDs
        if not dev_ids:
            dev_ids.update({1082437832087445604, 879986471866630155})

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**🚨 Kyro Sentinel Critical Incident Alert**\n"
                f"> **Incident:** `{incident.id}` | **Subsystem:** `{incident.subsystem.value}`\n"
                f"> **Issue:** **{incident.title}**\n"
                f"> **Details:** `{incident.details[:300]}`"
            )
        )

        if incident.ai_analysis:
            container.add_separator(divider=True)
            container.add_section(
                content=f"**🤖 Gemini AI Autonomous Diagnosis**\n{incident.ai_analysis}"
            )

        container.add_separator(divider=True)
        container.add_text(
            f"-# Autonomous Sentinel Telemetry • Time: `{incident.formatted_time}` • Use `?sentinel heal` to intervene"
        )

        for dev_id in dev_ids:
            try:
                user = self.bot.get_user(dev_id) or await self.bot.fetch_user(dev_id)
                if user:
                    await send_container_response(user, container)
            except Exception as e:
                logger.debug(f"Sentinel: Could not dispatch alert DM to developer {dev_id}: {e}")

    # ── Watchdog Core Loop ──

    @tasks.loop(seconds=30.0)
    async def watchdog_loop(self) -> None:
        """Periodic non-blocking system health check & self-healing execution."""
        # 1. Reset circuit breakers every 5 minutes
        now = time.time()
        if now - self._last_circuit_reset > 300:
            self._circuit_breakers.clear()
            self._last_circuit_reset = now
            self._lavalink_breaker_open = False

        # 2. Database Health Check
        await self._check_database_health()

        # 3. Lavalink Node Health Check
        await self._check_lavalink_health()

        # 4. Gateway Latency & Heartbeat Check
        self._check_gateway_health()

        # 5. Automated Zombie Voice Client Sweeper
        await self._sweep_zombie_voice_clients()

        # 6. Memory & Asyncio Loop Lag Diagnostics
        await self._check_resource_and_loop_health()

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
                        err_text(e),
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
        except Exception:
            await self._trigger_lavalink_reconnect(reason="No node found in Wavelink Pool")
            return

        if node.status != wavelink.NodeStatus.CONNECTED:
            await self._trigger_lavalink_reconnect(
                reason=f"Node status is {getattr(node.status, 'name', node.status)}"
            )
            return

        # A node can report CONNECTED while its REST API is hung. Every player
        # operation goes through the REST API, so the node is only really healthy
        # when the REST API answers too.
        if not await probe_node(node):
            await self._trigger_lavalink_reconnect(
                reason="Node reports CONNECTED but its REST API is unresponsive"
            )

    async def _trigger_lavalink_reconnect(self, reason: str) -> None:
        """Auto-reconnect Lavalink node with circuit breaker protection."""
        cb_key = "lavalink_node"
        fails = self._circuit_breakers.get(cb_key, 0) + 1
        self._circuit_breakers[cb_key] = fails

        if fails <= 3:
            logger.warning(f"Sentinel: Lavalink node offline ({reason}), auto-reconnecting...")
            try:
                await self.heal_lavalink()
                self._circuit_breakers.pop(cb_key, None)
                self._lavalink_breaker_open = False
                self.record_incident(
                    SubsystemType.MUSIC,
                    IncidentSeverity.WARNING,
                    "Lavalink Node Recovered",
                    reason,
                    action_taken="Cleanly re-established Wavelink node connection pool",
                    resolved=True,
                )
            except Exception as e:
                self.record_incident(
                    SubsystemType.MUSIC,
                    IncidentSeverity.CRITICAL,
                    "Lavalink Node Unreachable",
                    err_text(e),
                    action_taken=(
                        "Tried every configured node (primary + fallbacks). "
                        "Audio playback stays offline until one answers."
                    ),
                    resolved=False,
                )
        else:
            # Only report the tripped breaker once per open window, otherwise the
            # 30s watchdog loop floods the incident buffer and the health report.
            if not self._lavalink_breaker_open:
                self._lavalink_breaker_open = True
                self.record_incident(
                    SubsystemType.MUSIC,
                    IncidentSeverity.CRITICAL,
                    "Lavalink Circuit Breaker Tripped",
                    f"Lavalink reconnect failed {fails} times ({reason})",
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

    async def _sweep_zombie_voice_clients(self) -> None:
        """Autonomously sweep and recycle orphaned, disconnected, or hung voice clients."""
        try:
            for guild in list(self.bot.guilds):
                vc = guild.voice_client
                if vc:
                    # Check if voice connection is broken or channel missing
                    if not getattr(vc, "is_connected", lambda: True)() or not getattr(vc, "channel", None):
                        logger.warning(f"Sentinel: Detected zombie voice client in {guild.name} ({guild.id}). Purging...")
                        await self.heal_stuck_voice_client(guild)
        except Exception as e:
            logger.debug(f"Sentinel: Error during zombie voice sweep: {e}")

    async def _check_resource_and_loop_health(self) -> None:
        """Measure asyncio event loop latency and manage process memory footprints."""
        # 1. Event Loop Lag check
        t0 = time.perf_counter()
        await asyncio.sleep(0.01)
        lag_ms = max(0.0, (time.perf_counter() - t0 - 0.01) * 1000)
        self._event_loop_lag_ms = lag_ms

        if lag_ms > 1200:
            self.record_incident(
                SubsystemType.GATEWAY,
                IncidentSeverity.WARNING,
                "Event Loop Lag Detected",
                f"Asyncio loop lag spiked to {lag_ms:.1f}ms (blocking CPU operation detected)",
                action_taken="Logged thread contention metric",
                resolved=True,
            )

        # 2. Memory leak auto-remediation
        if psutil:
            try:
                p = psutil.Process(os.getpid())
                ram_mb = p.memory_info().rss / (1024 * 1024)
                if ram_mb > 550.0:
                    collected = gc.collect()
                    self._healed_counts["memory"] += 1
                    self.record_incident(
                        SubsystemType.COMMAND,
                        IncidentSeverity.INFO,
                        "High RAM Usage Auto-Purged",
                        f"Process RAM reached {ram_mb:.1f} MB (>550MB threshold)",
                        action_taken=f"Triggered Python garbage collection (reclaimed {collected} objects)",
                        resolved=True,
                    )
            except Exception:
                pass

    # ── Self-Healing Actuators ──

    async def heal_database(self) -> None:
        """Force recycle database connection pool."""
        if hasattr(self.bot, "db") and self.bot.db and hasattr(self.bot.db, "_heal_pool"):
            await self.bot.db._heal_pool()

    async def heal_lavalink(self) -> None:
        """
        Safely re-establish the Wavelink node connection.

        The MusicAgent owns a single-flight lock around node reconnection, so the
        heal is delegated to it. Without this the sentinel's 30s watchdog and the
        agent's command-error heal could run at the same time and clobber each
        other's node session.
        """
        music_cog = self.bot.get_cog("Music")
        agent = getattr(music_cog, "agent", None) if music_cog else None

        if agent is not None:
            ok, message = await agent.heal_node(force=True)
            if ok:
                self._circuit_breakers.pop("lavalink_node", None)
                return
            raise LavalinkUnavailable(message)

        # Fallback path (music cog not loaded yet): connect directly.
        try:
            await close_pool_nodes()
            node = await connect_lavalink_node(self.bot, inactive_player_timeout=300)
            self._circuit_breakers.pop("lavalink_node", None)
            logger.info(f"Sentinel: Lavalink node reconnected ({node.uri}).")
        except Exception as e:
            logger.error(f"Sentinel: Lavalink node heal error: {err_text(e)}")
            raise

    async def heal_stuck_voice_client(self, guild: discord.Guild) -> bool:
        """Cleanly reset a zombie/hung voice client in a guild."""
        try:
            vc = guild.voice_client
            if vc:
                try:
                    # Bounded: this talks to the Lavalink REST API and must never
                    # stall the sentinel watchdog loop.
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
            try:
                self.bot._connection._remove_voice_client(guild.id)
            except Exception:
                pass
            try:
                await guild.change_voice_state(channel=None)
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
                action_taken="Forcefully disconnected, purged cache and cleared gateway voice state",
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

        # Overall Status (true un-resolved tracking)
        has_critical = any(not inc.resolved and inc.severity == IncidentSeverity.CRITICAL for inc in self.incidents)
        has_warning = any(not inc.resolved for inc in self.incidents)
        overall_health = "CRITICAL" if has_critical else ("DEGRADED" if has_warning else "HEALTHY")

        ai_configured = bool(os.getenv("GEMINI_API_KEY", "").strip())

        return {
            "status": overall_health,
            "uptime": uptime_str,
            "ram_mb": f"{ram_mb:.1f} MB",
            "cpu_percent": f"{cpu_percent:.1f}%",
            "gateway_latency_ms": f"{self.bot.latency * 1000:.1f} ms" if self.bot.latency != float("inf") else "Offline",
            "loop_lag_ms": f"{self._event_loop_lag_ms:.1f} ms",
            "lavalink_node": node_status,
            "active_audio_streams": active_players,
            "guild_count": len(self.bot.guilds),
            "healed_counts": dict(self._healed_counts),
            "total_incidents": len(self.incidents),
            "unresolved_incidents": sum(1 for inc in self.incidents if not inc.resolved),
            "ai_rca_engine": "Gemini 2.5/Flash SRE" if ai_configured else "Unconfigured (Missing API Key)",
            "recent_incidents": list(self.incidents)[-5:],
        }
