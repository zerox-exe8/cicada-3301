import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

import discord
from discord import app_commands
from discord.ext import commands

from src.core.permissions import (
    install_permission_overrides,
    is_owner_or_developer_async,
    is_owner_or_developer_sync,
    is_owner_sync,
    owner_override_app_has_permissions,
    owner_override_has_permissions,
)
from src.managers.permission_manager import is_developer, is_owner


class TestOwnerPermissionsOverride(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying transparent application owner overrides."""

    def setUp(self):
        install_permission_overrides()
        self.bot = MagicMock()
        self.bot.owner_id = 999999999999999999
        self.bot.owner_ids = {self.bot.owner_id}
        self.bot.perm_mgr = MagicMock()
        self.bot.perm_mgr.is_owner_sync = MagicMock(side_effect=lambda uid: uid == self.bot.owner_id)
        self.bot.perm_mgr.is_developer_sync = MagicMock(
            side_effect=lambda uid: uid in {888888888888888888, self.bot.owner_id}
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
        ctx.guild = MagicMock(id=777)
        ctx.command = MagicMock(qualified_name="test_cmd")
        ctx.channel.permissions_for = MagicMock(return_value=discord.Permissions.none())

        result = await predicate(ctx)
        self.assertTrue(result)

    async def test_developer_does_not_bypass_missing_guild_permission(self):
        """Developers (non-owners) must NOT bypass server-level permissions."""
        dev_id = 888888888888888888
        check_decorator = commands.has_permissions(ban_members=True)
        predicate = check_decorator.predicate

        ctx = MagicMock()
        ctx.bot = self.bot
        ctx.author = MagicMock(id=dev_id)
        ctx.guild = MagicMock(id=777)
        ctx.command = MagicMock(qualified_name="ban")
        ctx.channel.permissions_for = MagicMock(return_value=discord.Permissions.none())

        # Developer should be rejected like any other member without ban_members permission
        with self.assertRaises(commands.MissingPermissions):
            await predicate(ctx)

    async def test_app_command_owner_bypass(self):
        """Slash command check must allow application owner without interaction permissions."""
        check_decorator = app_commands.checks.has_permissions(manage_messages=True)
        dummy_cmd = MagicMock()
        check_decorator(dummy_cmd)
        predicate = dummy_cmd.__discord_app_commands_checks__[0]

        interaction = MagicMock()
        interaction.client = self.bot
        interaction.user = MagicMock(id=self.bot.owner_id)
        interaction.guild_id = 777
        interaction.command = MagicMock(name="slash_cmd")
        interaction.permissions = discord.Permissions.none()

        result = await predicate(interaction)
        self.assertTrue(result)

    async def test_app_command_normal_user_missing_perms(self):
        """Slash command check must reject normal user without permissions."""
        check_decorator = app_commands.checks.has_permissions(manage_messages=True)
        dummy_cmd = MagicMock()
        check_decorator(dummy_cmd)
        predicate = dummy_cmd.__discord_app_commands_checks__[0]

        interaction = MagicMock()
        interaction.client = self.bot
        interaction.user = MagicMock(id=555555555)
        interaction.permissions = discord.Permissions.none()

        with self.assertRaises(app_commands.MissingPermissions):
            await predicate(interaction)

    async def test_noprefix_owner_check_passes_for_owner(self):
        """is_owner check for noprefix commands must pass for bot owner."""
        check = is_owner()
        predicate = check.predicate

        ctx = MagicMock()
        ctx.bot = self.bot
        ctx.bot.perm_mgr.is_owner = AsyncMock(return_value=True)
        ctx.author = MagicMock(id=self.bot.owner_id)

        result = await predicate(ctx)
        self.assertTrue(result)

    async def test_noprefix_owner_check_rejects_developer(self):
        """is_owner check for noprefix commands must reject non-owner developers."""
        check = is_owner()
        predicate = check.predicate

        ctx = MagicMock()
        ctx.bot = self.bot
        # User is developer but NOT owner
        ctx.bot.perm_mgr.is_owner = AsyncMock(return_value=False)
        ctx.author = MagicMock(id=888888888888888888)

        with self.assertRaises(commands.NotOwner):
            await predicate(ctx)

    async def test_noprefix_owner_check_rejects_normal_user(self):
        """is_owner check for noprefix commands must reject regular users."""
        check = is_owner()
        predicate = check.predicate

        ctx = MagicMock()
        ctx.bot = self.bot
        ctx.bot.perm_mgr.is_owner = AsyncMock(return_value=False)
        ctx.author = MagicMock(id=123456789)

        with self.assertRaises(commands.NotOwner):
            await predicate(ctx)


if __name__ == "__main__":
    unittest.main()
