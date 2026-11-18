from __future__ import annotations

import asyncio
import logging
import math
import os
import secrets
import time
from typing import TYPE_CHECKING, Callable

import discord
from aiohttp import web

from src.core.config import Config

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Server")


class HealthServer:
    """Async web server for hosting health checks and authenticated real-time telemetry APIs."""

    def __init__(
        self,
        bot: KyroBot | None = None,
        bot_getter: Callable[[], KyroBot | None] | None = None,
    ) -> None:
        self._bot = bot
        self._bot_getter = bot_getter
        self._start_time = time.monotonic()
        self.app = web.Application(middlewares=[self._api_auth_middleware])
        self.runner: web.AppRunner | None = None
        self._setup_routes()

    @property
    def bot(self) -> KyroBot | None:
        if self._bot_getter:
            return self._bot_getter()
        return self._bot

    @bot.setter
    def bot(self, value: KyroBot | None) -> None:
        self._bot = value

    @web.middleware
    async def _api_auth_middleware(self, request: web.Request, handler: Callable) -> web.Response:
        """Authenticate all /api/* requests with a secret Bearer token and enforce CORS policies."""
        if request.path.startswith("/api/"):
            if request.method == "OPTIONS":
                return await handler(request)

            expected = (os.getenv("DASHBOARD_TOKEN") or getattr(Config, "DASHBOARD_TOKEN", "")).strip()
            is_prod = getattr(Config, "ENVIRONMENT", "development").lower() == "production"

            if not expected:
                if is_prod:
                    return web.json_response(
                        {"error": "Dashboard API disabled: DASHBOARD_TOKEN not configured in production"},
                        status=503,
                        headers=self._cors_headers(request),
                    )
                # In non-production, only allow loopback without token
                remote = getattr(request, "remote", "")
                if remote not in ("127.0.0.1", "::1", "localhost", None):
                    return web.json_response(
                        {"error": "Unauthorized: Valid Bearer token required"},
                        status=401,
                        headers=self._cors_headers(request),
                    )
            else:
                auth = request.headers.get("Authorization", "").strip()
                expected_header = f"Bearer {expected}"
                if not secrets.compare_digest(auth, expected_header):
                    return web.json_response(
                        {"error": "Unauthorized: Valid Bearer token required"},
                        status=401,
                        headers=self._cors_headers(request),
                    )

        return await handler(request)

    def _setup_routes(self) -> None:
        self.app.router.add_get("/", self._handle_home)
        self.app.router.add_get("/health", self._handle_health)
        self.app.router.add_get("/api/stats", self._handle_api_stats)
        self.app.router.add_get("/api/guilds", self._handle_api_guilds)
        self.app.router.add_get("/api/guilds/{id}", self._handle_api_guild)
        self.app.router.add_get("/api/guilds/{id}/antinuke", self._handle_api_antinuke_get)
        self.app.router.add_patch("/api/guilds/{id}/antinuke", self._handle_api_antinuke_patch)
        self.app.router.add_get("/api/commands", self._handle_api_commands)
        self.app.router.add_get("/api/music/{id}", self._handle_api_music)
        # CORS preflight for website & dashboard
        self.app.router.add_options("/api/{tail:.*}", self._handle_options)
        self.app.router.add_options("/health", self._handle_options)

    async def _handle_options(self, request: web.Request) -> web.Response:
        return web.Response(status=204, headers=self._cors_headers(request))

    def _cors_headers(self, request: web.Request | None = None) -> dict[str, str]:
        """Produce CORS headers restricted to DASHBOARD_ORIGINS or allowed dev origins."""
        origin = request.headers.get("Origin", "") if request else ""
        allowed_origins = getattr(Config, "DASHBOARD_ORIGINS", []) or [
            o.strip() for o in os.getenv("DASHBOARD_ORIGINS", "").split(",") if o.strip()
        ]

        headers: dict[str, str] = {
            "Access-Control-Allow-Methods": "GET, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
        }

        if origin and allowed_origins and origin in allowed_origins:
            headers["Access-Control-Allow-Origin"] = origin
        elif not allowed_origins:
            is_prod = getattr(Config, "ENVIRONMENT", "development").lower() == "production"
            if not is_prod:
                headers["Access-Control-Allow-Origin"] = origin or "*"
        elif allowed_origins:
            headers["Access-Control-Allow-Origin"] = allowed_origins[0]

        return headers

    def _check_dashboard_auth(self, request: web.Request) -> bool:
        """Bearer-token guard for write endpoints with constant-time comparison and environment gating."""
        expected = (os.getenv("DASHBOARD_TOKEN") or getattr(Config, "DASHBOARD_TOKEN", "")).strip()
        if not expected:
            is_local_dev = getattr(Config, "ENVIRONMENT", "development").lower() in ("dev", "development", "local")
            remote = getattr(request, "remote", "")
            if is_local_dev and remote in ("127.0.0.1", "::1", "localhost", None):
                return True
            return False

        auth = request.headers.get("Authorization", "").strip()
        expected_header = f"Bearer {expected}"
        return secrets.compare_digest(auth, expected_header)

    async def _handle_home(self, request: web.Request) -> web.Response:
        """Root endpoint returning basic status."""
        return web.Response(
            text="Kyro Discord Bot is Online & Running 24/7!",
            content_type="text/plain",
            status=200,
        )

    async def _handle_health(self, request: web.Request) -> web.Response:
        """
        Detailed health check endpoint reporting true subsystem health.
        Returns 200 during 180s startup grace period to avoid restart loops.
        Returns 503 if bot is not ready or database is disconnected after grace period.
        Does NOT leak guild counts publicly.
        """
        bot = self.bot
        ws_ping = round(bot.latency * 1000) if (bot and bot.latency and not math.isnan(bot.latency)) else 0
        is_ready = bool(bot and bot.is_ready())
        db_ok = bool(
            bot
            and getattr(bot, "db", None)
            and getattr(bot.db, "pool", None)
            and not getattr(bot.db.pool, "_closed", True)
        )
        lavalink_ok = False
        try:
            import wavelink
            node = wavelink.Pool.get_node()
            lavalink_ok = bool(node and getattr(node, "status", None) == wavelink.NodeStatus.CONNECTED)
        except Exception as node_err:
            logger.debug(f"Health Lavalink node check notice: {node_err}")

        uptime = time.monotonic() - getattr(self, "_start_time", 0.0)
        in_grace_period = uptime < 180.0

        if is_ready and db_ok:
            overall = "healthy" if lavalink_ok else "degraded"
        elif in_grace_period:
            overall = "initializing"
        else:
            overall = "unhealthy"

        data = {
            "status": overall,
            "bot": "Kyro",
            "ready": is_ready,
            "ping_ms": ws_ping,
            "components": {
                "database": "connected" if db_ok else "disconnected",
                "lavalink": "connected" if lavalink_ok else "disconnected",
                "gateway": "ready" if is_ready else "connecting",
            },
        }

        if in_grace_period:
            status_code = 200
        else:
            status_code = 200 if (is_ready and db_ok) else 503

        return web.json_response(data, status=status_code, headers=self._cors_headers(request))

    async def _handle_api_stats(self, request: web.Request) -> web.Response:
        """Real-time bot telemetry metrics JSON API."""
        bot = self.bot
        if not bot:
            return web.json_response({"error": "Bot gateway not initialized"}, status=503, headers=self._cors_headers(request))

        ws_ping = round(bot.latency * 1000) if (bot.latency and not math.isnan(bot.latency)) else 0
        total_members = sum(getattr(g, "member_count", 0) for g in bot.guilds)

        active_players = 0
        music_cog = bot.get_cog("Music")
        if music_cog and hasattr(music_cog, "controller"):
            active_players = sum(1 for p in music_cog.controller.players.values() if p and p.is_connected)

        ram_mb = 0.0
        try:
            import psutil
            process = psutil.Process(os.getpid())
            ram_mb = round(process.memory_info().rss / (1024 * 1024), 2)
        except Exception as ps_err:
            logger.debug(f"Health psutil stats notice: {ps_err}")

        data = {
            "status": "online",
            "bot_name": Config.BOT_NAME,
            "version": getattr(Config, "VERSION", "2.4.0"),
            "latency_ms": ws_ping,
            "guilds": len(bot.guilds),
            "total_users": total_members,
            "active_audio_players": active_players,
            "ram_usage_mb": ram_mb,
            "loaded_cogs": list(bot.cogs.keys()),
            "total_commands": len(bot.commands),
            "uptime_seconds": int((discord.utils.utcnow() - bot.start_time).total_seconds()) if hasattr(bot, "start_time") else 0,
        }
        return web.json_response(data, headers=self._cors_headers(request))

    async def _handle_api_guild(self, request: web.Request) -> web.Response:
        """Real-time guild telemetry and configuration."""
        bot = self.bot
        guild_id_str = request.match_info.get("id")
        try:
            guild_id = int(guild_id_str)
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400, headers=self._cors_headers(request))

        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503, headers=self._cors_headers(request))

        guild = bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "Guild not found"}, status=404, headers=self._cors_headers(request))

        prefix = bot.guild_mgr.get_prefix(guild.id)
        modlog_ch = bot.log_mgr.get_log_channel(guild, "mod")

        data = {
            "id": str(guild.id),
            "name": guild.name,
            "member_count": getattr(guild, "member_count", 0),
            "prefix": prefix,
            "modlog_channel_id": str(modlog_ch.id) if modlog_ch else None,
            "icon_url": str(guild.icon.url) if guild.icon else None,
        }
        return web.json_response(data, headers=self._cors_headers(request))

    async def _handle_api_guilds(self, request: web.Request) -> web.Response:
        """Real guild list — every server the bot is actually in."""
        bot = self.bot
        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503, headers=self._cors_headers(request))
        guilds = [
            {
                "id": str(g.id),
                "name": g.name,
                "member_count": getattr(g, "member_count", 0) or 0,
                "icon_url": str(g.icon.url) if g.icon else None,
            }
            for g in bot.guilds
        ]
        return web.json_response({"guilds": guilds}, headers=self._cors_headers(request))

    async def _handle_api_antinuke_get(self, request: web.Request) -> web.Response:
        """Real antinuke state for a guild, straight from AntinukeManager memory."""
        bot = self.bot
        try:
            guild_id = int(request.match_info.get("id"))
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400, headers=self._cors_headers(request))
        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503, headers=self._cors_headers(request))
        if not bot.get_guild(guild_id):
            return web.json_response({"error": "Guild not found"}, status=404, headers=self._cors_headers(request))

        from src.managers.antinuke_manager import PROTECTION_MODULES
        cfg = bot.antinuke_mgr.get_settings(guild_id)
        data = {
            "guild_id": str(guild_id),
            "enabled": bool(cfg.get("enabled", False)),
            "punishment": cfg.get("punishment", "ban"),
            "log_channel_id": str(cfg["log_channel_id"]) if cfg.get("log_channel_id") else None,
            "modules": {m: bool(cfg.get(f"{m}_protection", True)) for m in PROTECTION_MODULES},
        }
        return web.json_response(data, headers=self._cors_headers(request))

    async def _handle_api_antinuke_patch(self, request: web.Request) -> web.Response:
        """Apply antinuke changes for real — master switch, punishment, modules."""
        bot = self.bot
        try:
            guild_id = int(request.match_info.get("id"))
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400, headers=self._cors_headers(request))
        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503, headers=self._cors_headers(request))
        if not bot.get_guild(guild_id):
            return web.json_response({"error": "Guild not found"}, status=404, headers=self._cors_headers(request))
        if not self._check_dashboard_auth(request):
            return web.json_response(
                {"error": "Unauthorized: Valid Bearer token required"}, status=401,
                headers=self._cors_headers(request),
            )
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400,
                                     headers=self._cors_headers(request))

        from src.managers.antinuke_manager import PROTECTION_MODULES
        updates: dict = {}
        if "enabled" in body:
            updates["enabled"] = bool(body["enabled"])
        if "punishment" in body and str(body["punishment"]).lower() in ("ban", "kick", "quarantine", "strip_roles"):
            updates["punishment"] = str(body["punishment"]).lower()
        if isinstance(body.get("modules"), dict):
            for m in PROTECTION_MODULES:
                if m in body["modules"]:
                    updates[f"{m}_protection"] = bool(body["modules"][m])
        if not updates:
            return web.json_response({"error": "Nothing to update"}, status=400,
                                     headers=self._cors_headers(request))

        await bot.antinuke_mgr.update_settings(guild_id, **updates)
        return await self._handle_api_antinuke_get(request)

    async def _handle_api_commands(self, request: web.Request) -> web.Response:
        """Real command registry — every loaded prefix command with its help text."""
        bot = self.bot
        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503, headers=self._cors_headers(request))
        cmds = []
        for cmd in sorted(bot.commands, key=lambda c: c.qualified_name):
            if getattr(cmd, "hidden", False):
                continue
            cmds.append({
                "name": cmd.qualified_name,
                "help": (cmd.help or cmd.description or "No description yet.").strip().split("\n")[0][:160],
                "cog": cmd.cog_name or "General",
            })
        return web.json_response({"count": len(cmds), "commands": cmds}, headers=self._cors_headers(request))

    async def _handle_api_music(self, request: web.Request) -> web.Response:
        """Real-time audio streaming telemetry per guild."""
        bot = self.bot
        guild_id_str = request.match_info.get("id")
        try:
            guild_id = int(guild_id_str)
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400, headers=self._cors_headers(request))

        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503, headers=self._cors_headers(request))

        music_cog = bot.get_cog("Music")
        if not music_cog or not hasattr(music_cog, "controller"):
            return web.json_response({"is_playing": False, "connected": False}, headers=self._cors_headers(request))

        player = music_cog.controller.get_player(guild_id)
        if not player or not player.is_connected:
            return web.json_response({"is_playing": False, "connected": False}, headers=self._cors_headers(request))

        current_track = None
        if player.current:
            current_track = {
                "title": player.current.title,
                "author": player.current.author,
                "duration": player.current.duration,
                "url": player.current.url,
                "requester": player.current.requester,
            }

        data = {
            "connected": True,
            "is_playing": player.is_playing,
            "is_paused": player.is_paused,
            "volume": int(player.volume * 100),
            "loop_mode": player.loop_mode,
            "is_247": getattr(player, "is_247", False),
            "queue_length": len(player.queue),
            "current": current_track,
        }
        return web.json_response(data, headers=self._cors_headers(request))

    async def _keepalive_loop(self) -> None:
        """Self-ping loop every 8 minutes to prevent Render Free tier spin-down when RENDER_EXTERNAL_URL is set."""
        render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
        if not render_url:
            logger.info("RENDER_EXTERNAL_URL not configured. Keep-alive self-pinger inactive.")
            return

        target_url = f"{render_url.rstrip('/')}/health"
        logger.info(f"Initialized 24/7 keep-alive pinger for: {target_url}")

        await asyncio.sleep(60)  # Initial delay after server boot

        while True:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(target_url, timeout=15) as resp:
                        logger.debug(f"Render keep-alive ping status: {resp.status}")
            except Exception as e:
                logger.debug(f"Render keep-alive notice: {e}")
            await asyncio.sleep(480)  # Ping every 8 minutes (Render sleeps at 15m)

    async def start(self) -> None:
        """Start the async HTTP server with automatic port fallback."""
        base_port = int(os.getenv("PORT", 8080))
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        for port in [base_port, base_port + 1, base_port + 2, 0]:
            try:
                site = web.TCPSite(self.runner, "0.0.0.0", port)
                await site.start()
                actual_port = port if port != 0 else getattr(site._server.sockets[0], "getsockname", lambda: (0, 0))()[1]
                logger.info(f"Keep-Alive Health Server listening on http://0.0.0.0:{actual_port}")
                if os.getenv("RENDER_EXTERNAL_URL", "").strip():
                    self._keepalive_task = asyncio.create_task(self._keepalive_loop())
                return
            except OSError as e:
                logger.warning(f"Port {port} is in use ({e}). Trying next port...")
        logger.error("Could not bind HealthServer to any open port.")

    async def stop(self) -> None:
        """Gracefully stop the web server."""
        if hasattr(self, "_keepalive_task") and self._keepalive_task:
            self._keepalive_task.cancel()
        if self.runner:
            await self.runner.cleanup()
            logger.info("Keep-Alive Health Server stopped.")
