import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock
import discord
from discord.ext import commands
from discord import app_commands

from src.core.permissions import (
    install_permission_overrides,
    is_owner_or_developer_sync,
    is_owner_or_developer_async,
    owner_override_has_permissions,
    owner_override_app_has_permissions,
    IMMUTABLE_DEVELOPER_IDS,
)


class TestOwnerPermissionsOverride(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying transparent application owner & developer overrides."""

    def setUp(self):
        install_permission_overrides()
        self.bot = MagicMock()
        self.bot.owner_id = 999999999999999999
        self.bot.owner_ids = {self.bot.owner_id}
        self.bot.perm_mgr = MagicMock()
        self.bot.perm_mgr.is_developer_sync = MagicMock(
            side_effect=lambda uid: uid in IMMUTABLE_DEVELOPER_IDS or uid == self.bot.owner_id
        )
        self.bot.is_owner = AsyncMock(side_effect=lambda u: u.id == self.bot.owner_id)

    async def test_normal_user_missing_permissions_raises(self):
        """Standard user without permission must raise MissingPermissions."""
        check_decorator = commands.has_permissions(manage_guild=True)
        predicate = check_decorator.predicate

        ctx = MagicMock()
        ctx.bot = self.bot
        ctx.author = MagicMock(id=123456789)
        ctx.channel.permissions_for = MagicMock(return_value=discord.Permissions(send_messages=True))

        with self.assertRaises(commands.MissingPermissions):
            await predicate(ctx)

    async def test_normal_user_with_permission_passes(self):
        """Standard user with permission must succeed."""
        check_decorator = commands.has_permissions(manage_guild=True)
        predicate = check_decorator.predicate

        ctx = MagicMock()
        ctx.bot = self.bot
        ctx.author = MagicMock(id=123456789)
        ctx.channel.permissions_for = MagicMock(return_value=discord.Permissions(manage_guild=True))

        result = await predicate(ctx)
        self.assertTrue(result)

    async def test_owner_bypasses_missing_guild_permission(self):
        """Application Owner must succeed EVEN IF channel permissions are completely empty."""
        check_decorator = commands.has_permissions(administrator=True, manage_guild=True, ban_members=True)
        predicate = check_decorator.predicate

        ctx = MagicMock()
        ctx.bot = self.bot
        ctx.author = MagicMock(id=self.bot.owner_id)
        # Empty channel permissions (0)
        ctx.channel.permissions_for = MagicMock(return_value=discord.Permissions.none())

        result = await predicate(ctx)
        self.assertTrue(result)

    async def test_developer_bypasses_missing_guild_permission(self):
        """Developer ID must succeed EVEN IF channel permissions are completely empty."""
        dev_id = list(IMMUTABLE_DEVELOPER_IDS)[0]
        check_decorator = commands.has_permissions(ban_members=True)
        predicate = check_decorator.predicate

        ctx = MagicMock()
        ctx.bot = self.bot
        ctx.author = MagicMock(id=dev_id)
        ctx.channel.permissions_for = MagicMock(return_value=discord.Permissions.none())

        result = await predicate(ctx)
        self.assertTrue(result)

    async def test_app_command_owner_bypass(self):
        """Slash command check must allow application owner without interaction permissions."""
        check_decorator = app_commands.checks.has_permissions(manage_messages=True)
        # In discord.app_commands, decorator appends predicate to unwrapped function
        dummy_cmd = MagicMock()
        decorated = check_decorator(dummy_cmd)
        predicate = dummy_cmd.__discord_app_commands_checks__[0]

        interaction = MagicMock()
        interaction.client = self.bot
        interaction.user = MagicMock(id=self.bot.owner_id)
        interaction.permissions = discord.Permissions.none()

        result = await predicate(interaction)
        self.assertTrue(result)

    async def test_app_command_normal_user_missing_perms(self):
        """Slash command check must reject normal user without permissions."""
        check_decorator = app_commands.checks.has_permissions(manage_messages=True)
        dummy_cmd = MagicMock()
        decorated = check_decorator(dummy_cmd)
        predicate = dummy_cmd.__discord_app_commands_checks__[0]

        interaction = MagicMock()
        interaction.client = self.bot
        interaction.user = MagicMock(id=555555555)
        interaction.permissions = discord.Permissions.none()

        with self.assertRaises(app_commands.MissingPermissions):
            await predicate(interaction)


if __name__ == "__main__":
    unittest.main()
