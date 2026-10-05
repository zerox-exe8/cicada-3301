from __future__ import annotations

import asyncio
import logging
import math
import os
from typing import TYPE_CHECKING, Callable
from aiohttp import web

from src.core.config import Config

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Server")


class HealthServer:
    """Async web server for hosting health checks and real-time telemetry APIs."""

    def __init__(
        self,
        bot: KyroBot | None = None,
        bot_getter: Callable[[], KyroBot | None] | None = None,
    ) -> None:
        self._bot = bot
        self._bot_getter = bot_getter
        self.app = web.Application()
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

    def _setup_routes(self) -> None:
        self.app.router.add_get("/", self._handle_home)
        self.app.router.add_get("/health", self._handle_health)
        self.app.router.add_get("/api/stats", self._handle_api_stats)
        self.app.router.add_get("/api/guilds/{id}", self._handle_api_guild)
        self.app.router.add_get("/api/music/{id}", self._handle_api_music)

    async def _handle_home(self, request: web.Request) -> web.Response:
        """Root endpoint returning basic status."""
        return web.Response(
            text="Kyro Discord Bot is Online & Running 24/7!",
            content_type="text/plain",
            status=200,
        )

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Detailed health check endpoint."""
        bot = self.bot
        ws_ping = round(bot.latency * 1000) if (bot and bot.latency and not math.isnan(bot.latency)) else 0
        data = {
            "status": "healthy",
            "bot": "Kyro",
            "guilds": len(bot.guilds) if bot else 0,
            "ping_ms": ws_ping,
        }
        return web.json_response(data, status=200)

    async def _handle_api_stats(self, request: web.Request) -> web.Response:
        """Real-time bot telemetry metrics JSON API."""
        bot = self.bot
        if not bot:
            return web.json_response({"error": "Bot gateway not initialized"}, status=503)

        ws_ping = round(bot.latency * 1000) if (bot.latency and not math.isnan(bot.latency)) else 0
        total_members = sum(getattr(g, "member_count", 0) for g in bot.guilds)

        active_players = 0
        music_cog = bot.get_cog("Music")
        if music_cog and hasattr(music_cog, "controller"):
            active_players = sum(1 for p in music_cog.controller.players.values() if p and p.is_connected)

        ram_mb = 0.0
        try:
            import os
            import psutil
            process = psutil.Process(os.getpid())
            ram_mb = round(process.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            pass

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
        return web.json_response(data, headers={"Access-Control-Allow-Origin": "*"})

    async def _handle_api_guild(self, request: web.Request) -> web.Response:
        """Real-time guild telemetry and configuration."""
        bot = self.bot
        guild_id_str = request.match_info.get("id")
        try:
            guild_id = int(guild_id_str)
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503)

        guild = bot.get_guild(guild_id)
        if not guild:
            return web.json_response({"error": "Guild not found"}, status=404)

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
        return web.json_response(data, headers={"Access-Control-Allow-Origin": "*"})

    async def _handle_api_music(self, request: web.Request) -> web.Response:
        """Real-time audio streaming telemetry per guild."""
        bot = self.bot
        guild_id_str = request.match_info.get("id")
        try:
            guild_id = int(guild_id_str)
        except (ValueError, TypeError):
            return web.json_response({"error": "Invalid guild ID"}, status=400)

        if not bot:
            return web.json_response({"error": "Bot gateway offline"}, status=503)

        music_cog = bot.get_cog("Music")
        if not music_cog or not hasattr(music_cog, "controller"):
            return web.json_response({"is_playing": False, "connected": False})

        player = music_cog.controller.get_player(guild_id)
        if not player or not player.is_connected:
            return web.json_response({"is_playing": False, "connected": False})

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
        return web.json_response(data, headers={"Access-Control-Allow-Origin": "*"})

    async def _keepalive_loop(self) -> None:
        """Self-ping loop every 8 minutes to prevent Render Free tier spin-down."""
        render_url = os.getenv("RENDER_EXTERNAL_URL") or "https://cicada-3301.onrender.com"
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
