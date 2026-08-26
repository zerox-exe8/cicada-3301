"""
Cicada 3301 Discord Bot - Core Bot Class
Subclasses commands.AutoShardedBot for high scalability and lifecycle control.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import aiohttp
import discord
from discord.ext import commands, tasks

from src.core.config import Config
from src.core.context import CustomContext
from src.database.base import BaseDatabase
from src.database.postgres import PostgresDatabase
from src.managers.guild_manager import GuildManager
from src.managers.permission_manager import PermissionManager
from src.managers.blacklist_manager import BlacklistManager
from src.managers.system_manager import SystemManager
from src.managers.log_manager import LogManager
from src.managers.premium_manager import PremiumManager
from src.utils.emojis import EmojiRegistry

logger = logging.getLogger("Cicada.Core")


async def get_prefix(bot: CicadaBot, message: discord.Message) -> list[str] | str:
    """
    Dynamic prefix resolver:
    - Bot Owner & Developers can use commands with NO prefix (e.g. 'ping', 'help') or normal prefixes.
    - Regular members must use server prefix or bot mention.
    """
    guild_id = message.guild.id if message.guild else None
    guild_prefix = bot.guild_mgr.get_prefix(guild_id)

    # Check if author is Owner or Developer
    if message.author and await bot.perm_mgr.is_developer(message.author.id):
        return commands.when_mentioned_or(guild_prefix, "")(bot, message)

    return commands.when_mentioned_or(guild_prefix)(bot, message)


class CicadaBot(commands.Bot):
    """Production-grade custom Discord bot class for Cicada 3301."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True

        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            strip_after_prefix=True,
        )

        # Sole Database Driver (Supabase PostgreSQL)
        from src.database.postgres import PostgresDatabase
        self.db: PostgresDatabase = PostgresDatabase(Config.DATABASE_URL)

        self.session: aiohttp.ClientSession | None = None
        self.start_time: discord.datetime = discord.utils.utcnow()

        # Core Managers & Emoji Registry
        self.guild_mgr: GuildManager = GuildManager(self.db)
        self.perm_mgr: PermissionManager = PermissionManager(self, self.db)
        self.blacklist_mgr: BlacklistManager = BlacklistManager(self.db)
        self.sys_mgr: SystemManager = SystemManager(self.db)
        self.log_mgr: LogManager = LogManager(self.db)
        self.premium_mgr: PremiumManager = PremiumManager(self.db)
        self.custom_emojis: EmojiRegistry = EmojiRegistry(self)
        
        # 24/7 Keep-Alive Web Server
        from src.core.server import HealthServer
        self.server: HealthServer = HealthServer(self)

        # Attach Global Command Guard
        self.add_check(self._global_command_check)

    async def get_context(
        self, origin: discord.Message | discord.Interaction, *, cls: type[CustomContext] = CustomContext
    ) -> CustomContext:
        """Inject our CustomContext into all commands."""
        return await super().get_context(origin, cls=cls)

    async def _global_command_check(self, ctx: commands.Context) -> bool:
        """Global guard: blocks blacklisted users/guilds and handles maintenance mode."""
        # 1. Blacklist Check
        if self.blacklist_mgr.is_user_blacklisted(ctx.author.id):
            reason = self.blacklist_mgr.get_blacklist_reason(ctx.author.id)
            raise commands.CheckFailure(f"You are globally blacklisted from using this bot.\n> Reason: `{reason}`")

        if ctx.guild and self.blacklist_mgr.is_guild_blacklisted(ctx.guild.id):
            reason = self.blacklist_mgr.get_blacklist_reason(ctx.guild.id)
            raise commands.CheckFailure(f"This server is blacklisted from using this bot.\n> Reason: `{reason}`")

        # 2. Maintenance Mode Check
        if self.sys_mgr.maintenance_mode:
            is_dev = await self.perm_mgr.is_developer(ctx.author.id)
            if not is_dev:
                raise commands.CheckFailure(
                    f"Bot is currently in Maintenance Mode.\n> Reason: `{self.sys_mgr.maintenance_reason}`"
                )

        # 3. Disabled Command Check
        cmd_name = ctx.command.qualified_name if ctx.command else ""
        if self.sys_mgr.is_command_disabled(cmd_name):
            is_dev = await self.perm_mgr.is_developer(ctx.author.id)
            if not is_dev:
                raise commands.CheckFailure(f"Command `{cmd_name}` is temporarily disabled by administrators.")

        if ctx.guild and self.guild_mgr.is_command_disabled(ctx.guild.id, cmd_name):
            raise commands.CheckFailure(f"Command `{cmd_name}` is disabled in this server.")

        return True

    async def on_message(self, message: discord.Message) -> None:
        """Handle standalone bot mentions and process prefix/mention commands."""
        if message.author.bot:
            return

        # Check if message is purely mentioning the bot
        if self.user and message.content in [f"<@{self.user.id}>", f"<@!{self.user.id}>"]:
            from src.utils.containers import CicadaContainer, send_container_response
            current_prefix = self.guild_mgr.get_prefix(message.guild.id if message.guild else None)
            container = CicadaContainer(accent_color=None)
            container.add_text(
                f"**Hey, I'm {Config.BOT_NAME}**\n"
                f"> Modular, high-performance Discord management system.\n\n"
                f"• **Prefix:** `{current_prefix}` | **Slash:** `/`\n"
                f"• **Help:** `{current_prefix}help`"
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {message.author.display_name}")
            await send_container_response(message, container)
            return

        await self.process_commands(message)

    async def setup_hook(self) -> None:
        """Asynchronous initialization before websocket login."""
        logger.info("Initializing async subsystems and managers...")

        # 1. Start HTTP Client Session
        self.session = aiohttp.ClientSession()

        # 2. Connect to Database Pool
        await self.db.connect()

        # 3. Load all Manager Caches & Custom Emojis
        await self.guild_mgr.load_cache()
        await self.perm_mgr.load_cache()
        await self.blacklist_mgr.load_cache()
        await self.sys_mgr.load_cache()
        await self.log_mgr.load_cache()
        await self.premium_mgr.load_cache()
        await self.custom_emojis.load()

        # 4. Load Error Handler
        await self.load_extension("src.errors.handler")

        # 5. Dynamically Load all Cogs
        await self._load_all_extensions()

        # 6. Start 24/7 Keep-Alive Web Server
        await self.server.start()

        logger.info("Setup hook completed successfully.")

    async def _load_all_extensions(self) -> None:
        """Walk through src/cogs and load every python module."""
        cogs_dir = Path(__file__).resolve().parent.parent / "cogs"

        for file in cogs_dir.rglob("*.py"):
            if file.name.startswith("_"):
                continue  # Skip __init__.py and private files

            relative = file.relative_to(cogs_dir.parent.parent)
            module_name = ".".join(relative.with_suffix("").parts)

            try:
                await self.load_extension(module_name)
                logger.info(f"Loaded extension: {module_name}")
            except Exception as e:
                logger.error(f"Failed to load extension {module_name}: {e}", exc_info=e)

    async def close(self) -> None:
        """Gracefully release database pools, servers, and network sessions."""
        logger.info("Shutting down Cicada 3301 Bot gracefully...")

        if hasattr(self, "server"):
            await self.server.stop()

        if self.session:
            await self.session.close()

        if self.db:
            await self.db.close()

        await super().close()

    @tasks.loop(seconds=18)
    async def _rotate_presence(self) -> None:
        """Dynamic rotating activity presence loop."""
        total_guilds = len(self.guilds)
        total_users = sum(g.member_count or 0 for g in self.guilds)

        activities = [
            discord.Activity(
                type=discord.ActivityType.watching,
                name=f"◈ {Config.DEFAULT_PREFIX}help | 3301 Protocol",
            ),
            discord.Activity(
                type=discord.ActivityType.listening,
                name="◈ Cryptographic Frequencies // 3301",
            ),
            discord.Activity(
                type=discord.ActivityType.watching,
                name=f"◈ {total_guilds} Network Nodes | {total_users} Entities",
            ),
            discord.Activity(
                type=discord.ActivityType.competing,
                name="◈ Prime Sequences & Ciphers",
            ),
        ]

        # Rotate to next activity
        current_idx = getattr(self, "_activity_index", 0)
        selected_activity = activities[current_idx % len(activities)]
        self._activity_index = current_idx + 1

        try:
            await self.change_presence(
                status=discord.Status.dnd,
                activity=selected_activity,
            )
        except Exception:
            pass


    @_rotate_presence.before_loop
    async def _before_rotate_presence(self) -> None:
        await self.wait_until_ready()

    async def on_ready(self) -> None:
        """Fired when Discord client has finished caching guilds."""
        logger.info(
            f"Logged in as {self.user} (ID: {self.user.id}) across {len(self.guilds)} guilds."
        )

        # Start rotating DND status loop
        if not self._rotate_presence.is_running():
            self._rotate_presence.start()

        # Auto sync global application commands tree with Discord
        try:
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} application/slash commands globally.")
        except Exception as e:
            logger.warning(f"Automatic command tree sync failed: {e}")
