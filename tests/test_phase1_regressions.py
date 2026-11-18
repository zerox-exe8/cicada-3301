import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands

from src.cogs.developer.identity import IdentityCog
from src.cogs.general.channelinfo import ChannelInfo
from src.cogs.music._agent import MusicAgent
from src.cogs.utility.embed_builder import ContainerDraft, EmbedBuilderView
from src.managers.dev_pulse_manager import DevPulseManager


class TestPhase1Regressions(unittest.IsolatedAsyncioTestCase):
    """Regression test suite for Phase 1 crashing bugs."""

    async def test_channelinfo_container_defined(self):
        """P1-1: ?channelinfo must instantiate KyroContainer and not raise NameError."""
        bot = MagicMock()
        cog = ChannelInfo(bot)

        ctx = MagicMock()
        ctx.author.display_name = "TestUser"
        ctx.channel = MagicMock(spec=discord.TextChannel)
        ctx.channel.name = "general"
        ctx.channel.id = 123456789
        ctx.channel.type = discord.ChannelType.text
        ctx.channel.category = None
        ctx.channel.created_at = discord.utils.utcnow()
        ctx.channel.slowmode_delay = 0
        ctx.channel.nsfw = False

        with patch("src.cogs.general.channelinfo.send_container_response", new_callable=AsyncMock) as mock_send:
            await cog.channelinfo.callback(cog, ctx, channel=ctx.channel)
            mock_send.assert_awaited_once()
            args, _ = mock_send.call_args
            container = args[1]
            self.assertIsNotNone(container)
            self.assertGreater(len(container.components), 0)

    async def test_identity_config_imported(self):
        """P1-2: identity.py ?setstatus logic must access Config without NameError."""
        bot = MagicMock()
        bot.db = MagicMock()
        bot.db.execute = AsyncMock()
        cog = IdentityCog(bot)

        ctx = MagicMock()
        ctx.clean_prefix = "?"
        ctx.send_success = AsyncMock()

        # Test resetting status which accesses Config.DEFAULT_PREFIX
        await cog.edit_status.callback(cog, ctx, new_status="reset")

    async def test_music_agent_wavelink_imported_and_ladder(self):
        """P1-3: handle_command_error must have wavelink imported; alive node + LavalinkException must not heal_node."""
        bot = MagicMock()
        bot.wait_until_ready = AsyncMock()
        music_cog = MagicMock()
        agent = MusicAgent(bot, music_cog)
        agent._background_sweeper.cancel()
        agent.heal_node = AsyncMock()

        import wavelink
        from wavelink.exceptions import LavalinkException

        mock_node = MagicMock()
        mock_node.status = wavelink.NodeStatus.CONNECTED

        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.send_error = AsyncMock()

        with patch("wavelink.Pool.get_node", return_value=mock_node):
            with patch("src.utils.containers.send_container_response", new_callable=AsyncMock) as mock_send:
                err = LavalinkException(data={"timestamp": 12345, "status": 400, "error": "Bad Request", "trace": "", "message": "Track blocked", "path": "/loadtracks", "severity": "COMMON"})
                await agent.handle_command_error(ctx, err)
                # heal_node should NOT have been called because node is alive and error is track-level
                agent.heal_node.assert_not_called()
                mock_send.assert_awaited_once()

    async def test_embed_builder_patch_payload_builder(self):
        """P1-4: update_view_channel_patch must build payload with build_container_payload."""
        bot = MagicMock()
        bot.http.request = AsyncMock(return_value={"id": "999"})
        bot.embed_mgr.save_template = AsyncMock()
        bot.get_guild = MagicMock(return_value=None)
        bot.get_channel = MagicMock(return_value=None)

        author = MagicMock()
        author.id = 111
        author.guild = None

        draft = ContainerDraft()
        draft.title = "Test Draft"
        view = EmbedBuilderView(
            bot=bot,
            author=author,
            draft=draft,
        )
        view.channel_id = 123
        view.message_id = 456

        # Calling update_view_channel_patch should not raise NameError: build_container_payload
        await view.update_view_channel_patch()
        bot.http.request.assert_awaited_once()

    async def test_dev_pulse_remoteok_logo_defined(self):
        """P1-5: RemoteOK fallback in _harvest_jobs must define logo and not raise NameError."""
        bot = MagicMock()
        mgr = DevPulseManager(bot)

        fake_job = {
            "position": "Backend Python Engineer",
            "company": "RemoteCo",
            "url": "https://remoteok.com/job/123",
            "company_logo": "https://remoteok.com/logo.png",
        }

        # Mock aiohttp session
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=[fake_job])
        mock_resp.__aenter__.return_value = mock_resp

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        # Force Jobicy to return 0 stories so it falls back to RemoteOK
        with patch.object(mgr, "_seen_hashes", set()):
            stories = await mgr._harvest_jobs(mock_session, limit=2)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0].image_url, "https://remoteok.com/logo.png")
