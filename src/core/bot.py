"""
Kyro Discord Bot - Core Bot Class
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
from src.managers.embed_manager import EmbedManager
from src.managers.event_manager import EventManager
from src.managers.ticket_manager import TicketManager
from src.utils.emojis import EmojiRegistry

logger = logging.getLogger("Kyro.Core")


async def get_prefix(bot: KyroBot, message: discord.Message) -> list[str] | str:
    """
    Dynamic prefix resolver:
    - Bot Owner, Developers & No-Prefix Authorized Users can use commands with NO prefix (e.g. 'ping', 'help') or normal prefixes.
    - Regular members must use server prefix or bot mention.
    """
    guild_id = message.guild.id if message.guild else None
    guild_prefix = bot.guild_mgr.get_prefix(guild_id)

    # Check if author has No-Prefix authorization or is Owner/Developer
    if message.author:
        author_id = message.author.id
        if author_id in getattr(bot, "no_prefix_users", set()) or bot.perm_mgr.is_developer_sync(author_id):
            return commands.when_mentioned_or(guild_prefix, "")(bot, message)

    return commands.when_mentioned_or(guild_prefix)(bot, message)


class KyroBot(commands.Bot):
    """Production-grade custom Discord bot class for Kyro."""

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
            status=discord.Status.dnd,
            activity=discord.CustomActivity(
                name=f"Listening to {Config.DEFAULT_PREFIX}help",
            ),
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
        self.embed_mgr: EmbedManager = EmbedManager(self.db)
        self.event_mgr: EventManager = EventManager(self.db)
        self.ticket_mgr: TicketManager = TicketManager(self.db)
        self.custom_emojis: EmojiRegistry = EmojiRegistry(self)
        self.no_prefix_users: set[int] = set()
        self.custom_status: str | None = None

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

        # Check if message is purely mentioning the bot (with optional spaces)
        clean_content = message.content.strip()
        if self.user and clean_content in [f"<@{self.user.id}>", f"<@!{self.user.id}>"]:
            from src.utils.containers import KyroContainer, send_container_response
            current_prefix = self.guild_mgr.get_prefix(message.guild.id if message.guild else None)
            container = KyroContainer(accent_color=None)
            container.add_text(
                f"**Hey, I'm {Config.BOT_NAME}**\n"
                f"> Modular, high-performance Discord management system.\n\n"
                f"• **Prefix:** `{current_prefix}` | **Slash:** `/`\n"
                f"• **Help:** `{current_prefix}help`"
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {message.author.display_name}")
            await send_container_response(message.channel, container)
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
        await self.ticket_mgr.load_cache()
        await self.custom_emojis.load()

        # Load No-Prefix authorized users into memory
        try:
            np_rows = await self.db.fetch_all("SELECT user_id FROM system_no_prefix;")
            self.no_prefix_users = {int(r["user_id"]) for r in np_rows}
            logger.info(f"Loaded {len(self.no_prefix_users)} No-Prefix authorized user(s) into memory cache.")
        except Exception as e:
            logger.debug(f"Notice loading No-Prefix users: {e}")

        # Load persistent custom bot status into memory
        try:
            status_row = await self.db.fetch_one("SELECT value FROM system_state WHERE key = 'bot_status';")
            if status_row and status_row.get("value"):
                self.custom_status = status_row["value"]
                logger.info(f"Loaded persistent custom bot status: {self.custom_status}")
        except Exception as e:
            logger.debug(f"Notice loading custom status: {e}")

        # 4. Load Error Handler
        await self.load_extension("src.errors.handler")

        # 5. Dynamically Load all Cogs
        await self._load_all_extensions()

        logger.info("Setup hook completed successfully.")

    async def _load_all_extensions(self) -> None:
        """Walk through src/cogs and load every python module."""
        cogs_dir = Path(__file__).resolve().parent.parent / "cogs"

        for file in cogs_dir.rglob("*.py"):
            # Skip any file that starts with '_' or is inside a directory starting with '_'
            if any(part.startswith("_") for part in file.relative_to(cogs_dir).parts):
                continue

            relative = file.relative_to(cogs_dir.parent.parent)
            module_name = ".".join(relative.with_suffix("").parts)

            try:
                await self.load_extension(module_name)
                logger.info(f"Loaded extension: {module_name}")
            except Exception as e:
                logger.error(f"Failed to load extension {module_name}: {e}", exc_info=e)

    async def close(self) -> None:
        """Gracefully release database pools and network sessions."""
        logger.info("Shutting down Kyro Bot gracefully...")

        if self.session:
            await self.session.close()

        if self.db:
            await self.db.close()

        await super().close()

    @tasks.loop(seconds=60)
    async def _rotate_presence(self) -> None:
        """Maintain persistent bot presence and DND status."""
        try:
            status_text = self.custom_status or f"Listening to {Config.DEFAULT_PREFIX}help"
            await self.change_presence(
                status=discord.Status.dnd,
                activity=discord.CustomActivity(name=status_text),
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

        # Cache application owner credentials once logged in
        try:
            app_info = await self.application_info()
            if app_info.team:
                self.owner_ids = {m.id for m in app_info.team.members}
            else:
                self.owner_id = app_info.owner.id
            logger.info("Application owner credentials cached in memory.")
        except Exception as e:
            logger.debug(f"Notice caching application info: {e}")

        # Immediately lock presence to DND with persistent custom status
        try:
            status_text = self.custom_status or f"Listening to {Config.DEFAULT_PREFIX}help"
            await self.change_presence(
                status=discord.Status.dnd,
                activity=discord.CustomActivity(name=status_text),
            )
        except Exception as e:
            logger.warning(f"Could not enforce DND presence: {e}")
        if not self._rotate_presence.is_running():
            self._rotate_presence.start()

        # Auto sync global application commands tree with Discord
        try:
            synced = await self.tree.sync()
            logger.info(f"Successfully synced {len(synced)} application/slash commands globally.")
        except Exception as e:
            logger.warning(f"Automatic command tree sync failed: {e}")

        # Automatically sync custom application emojis from assets in background
        asyncio.create_task(self.custom_emojis.sync_from_assets())


# Backward Compatibility Alias
KyroBot = KyroBot
