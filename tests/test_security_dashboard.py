import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import os
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src.core.server import HealthServer
from src.core.config import Config


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

        resp = await self.server._handle_health(req)
        self.assertEqual(resp.status, 200)

        import json
        body = json.loads(resp.text)
        self.assertIn("components", body)
        self.assertEqual(body["components"]["database"], "connected")
        self.assertEqual(body["components"]["gateway"], "ready")
        self.assertEqual(body["ready"], True)


if __name__ == "__main__":
    unittest.main()
