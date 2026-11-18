import json
import os
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from src.core.config import Config
from src.core.server import HealthServer


class TestSecurityDashboard(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying dashboard API security, authentication and health reporting."""

    def setUp(self):
        self.server = HealthServer(bot=None)

    def test_dashboard_auth_no_token_remote_rejected(self):
        """Unauthenticated write requests from non-loopback addresses must be rejected when DASHBOARD_TOKEN is unset."""
        req = MagicMock(spec=web.Request)
        req.remote = "192.168.1.100"
        req.headers = {}

        with patch.dict(os.environ, {"DASHBOARD_TOKEN": ""}):
            result = self.server._check_dashboard_auth(req)
            self.assertFalse(result, "Remote unauthenticated request must be denied when DASHBOARD_TOKEN is unset.")

    def test_dashboard_auth_valid_bearer_token_accepted(self):
        """Requests with matching Bearer token must be authenticated successfully."""
        req = MagicMock(spec=web.Request)
        req.remote = "192.168.1.100"
        req.headers = {"Authorization": "Bearer super_secure_token_12345"}

        with patch.dict(os.environ, {"DASHBOARD_TOKEN": "super_secure_token_12345"}):
            result = self.server._check_dashboard_auth(req)
            self.assertTrue(result, "Matching Bearer token must authenticate.")

    def test_dashboard_auth_invalid_bearer_token_rejected(self):
        """Requests with wrong Bearer token must be rejected."""
        req = MagicMock(spec=web.Request)
        req.remote = "192.168.1.100"
        req.headers = {"Authorization": "Bearer wrong_token"}

        with patch.dict(os.environ, {"DASHBOARD_TOKEN": "super_secure_token_12345"}):
            result = self.server._check_dashboard_auth(req)
            self.assertFalse(result, "Mismatched Bearer token must be rejected.")

    async def test_api_middleware_auth_flow(self):
        """Test API middleware authentication: missing token -> 401, wrong -> 401, valid -> 200."""
        handler = AsyncMock(return_value=web.Response(text="ok", status=200))

        # 1. Missing token
        req_no_token = MagicMock(spec=web.Request)
        req_no_token.path = "/api/stats"
        req_no_token.method = "GET"
        req_no_token.remote = "192.168.1.100"
        req_no_token.headers = {}
        with patch.dict(os.environ, {"DASHBOARD_TOKEN": "secret_abc"}):
            resp = await self.server._api_auth_middleware(req_no_token, handler)
            self.assertEqual(resp.status, 401)
            body = json.loads(resp.text)
            self.assertIn("Valid Bearer token required", body["error"])

        # 2. Wrong token
        req_wrong = MagicMock(spec=web.Request)
        req_wrong.path = "/api/stats"
        req_wrong.method = "GET"
        req_wrong.remote = "192.168.1.100"
        req_wrong.headers = {"Authorization": "Bearer wrong_token"}
        with patch.dict(os.environ, {"DASHBOARD_TOKEN": "secret_abc"}):
            resp = await self.server._api_auth_middleware(req_wrong, handler)
            self.assertEqual(resp.status, 401)

        # 3. Correct token
        req_valid = MagicMock(spec=web.Request)
        req_valid.path = "/api/stats"
        req_valid.method = "GET"
        req_valid.remote = "192.168.1.100"
        req_valid.headers = {"Authorization": "Bearer secret_abc"}
        with patch.dict(os.environ, {"DASHBOARD_TOKEN": "secret_abc"}):
            resp = await self.server._api_auth_middleware(req_valid, handler)
            self.assertEqual(resp.status, 200)

        # 4. Empty token in production -> 503
        req_prod_empty = MagicMock(spec=web.Request)
        req_prod_empty.path = "/api/stats"
        req_prod_empty.method = "GET"
        req_prod_empty.headers = {}
        with patch.dict(os.environ, {"DASHBOARD_TOKEN": "", "ENVIRONMENT": "production"}):
            with patch.object(Config, "ENVIRONMENT", "production"):
                resp = await self.server._api_auth_middleware(req_prod_empty, handler)
                self.assertEqual(resp.status, 503)
                body = json.loads(resp.text)
                self.assertIn("DASHBOARD_TOKEN not configured", body["error"])

    async def test_health_endpoint_reports_components(self):
        """Health endpoint must accurately report database, gateway and lavalink readiness."""
        mock_bot = MagicMock()
        mock_bot.is_ready = MagicMock(return_value=True)
        mock_bot.latency = 0.045
        mock_bot.guilds = [MagicMock(), MagicMock()]
        mock_bot.db = MagicMock()
        mock_bot.db.pool = MagicMock()
        mock_bot.db.pool._closed = False

        self.server.bot = mock_bot
        req = MagicMock(spec=web.Request)
        req.headers = {}

        resp = await self.server._handle_health(req)
        self.assertEqual(resp.status, 200)

        body = json.loads(resp.text)
        self.assertIn("components", body)
        self.assertEqual(body["components"]["database"], "connected")
        self.assertEqual(body["components"]["gateway"], "ready")
        self.assertEqual(body["ready"], True)
        # Verify guilds count is NOT leaked on health check
        self.assertNotIn("guilds", body)

    async def test_health_grace_period_and_post_grace_503(self):
        """Health check returns 200 during 180s grace period and 503 when unhealthy after grace period."""
        mock_bot = MagicMock()
        mock_bot.is_ready = MagicMock(return_value=False)
        mock_bot.latency = 0.0
        mock_bot.db = None
        self.server.bot = mock_bot
        req = MagicMock(spec=web.Request)
        req.headers = {}

        # 1. During grace period (uptime = 30s) -> 200
        self.server._start_time = time.monotonic() - 30.0
        resp_grace = await self.server._handle_health(req)
        self.assertEqual(resp_grace.status, 200)
        body_grace = json.loads(resp_grace.text)
        self.assertEqual(body_grace["status"], "initializing")

        # 2. After grace period (uptime = 200s) -> 503
        self.server._start_time = time.monotonic() - 200.0
        resp_post_grace = await self.server._handle_health(req)
        self.assertEqual(resp_post_grace.status, 503)
        body_post_grace = json.loads(resp_post_grace.text)
        self.assertEqual(body_post_grace["status"], "unhealthy")


if __name__ == "__main__":
    unittest.main()
