from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.bot import KyroBot
    from src.database.base import BaseDatabase
    from src.core.cache import MicrosecondCache

logger = logging.getLogger("Kyro.Core.Services")


class ServiceRegistry:
    """
    Centralized Domain Service Registry & Dependency Injection Container.
    Decouples individual domain managers from the monolithic KyroBot God Object
    and provides fault-tolerant, isolated hydration.
    """

    def __init__(self, bot: KyroBot, db: BaseDatabase, cache: MicrosecondCache) -> None:
        self.bot = bot
        self.db = db
        self.cache = cache

        # Lazy / Modular Manager Instantiation
        from src.managers.guild_manager import GuildManager
        from src.managers.permission_manager import PermissionManager
        from src.managers.blacklist_manager import BlacklistManager
        from src.managers.system_manager import SystemManager
        from src.managers.log_manager import LogManager
        from src.managers.premium_manager import PremiumManager
        from src.managers.embed_manager import EmbedManager
        from src.managers.event_manager import EventManager
        from src.managers.ticket_manager import TicketManager
        from src.managers.tech_manager import TechNewsManager
        from src.managers.dev_pulse_manager import DevPulseManager
        from src.managers.tech_realtime_manager import TechRealtimeManager
        from src.managers.temp_voice_manager import TempVoiceManager
        from src.managers.translator_manager import TranslatorManager
        from src.managers.sticky_manager import StickyManager
        from src.managers.antinuke_manager import AntinukeManager
        from src.managers.media_manager import MediaManager
        from src.managers.giveaway_manager import GiveawayManager

        self.guild: GuildManager = GuildManager(db, cache=cache)
        self.perm: PermissionManager = PermissionManager(bot, db)
        self.blacklist: BlacklistManager = BlacklistManager(db)
        self.system: SystemManager = SystemManager(db)
        self.log: LogManager = LogManager(db)
        self.premium: PremiumManager = PremiumManager(db)
        self.embed: EmbedManager = EmbedManager(db)
        self.event: EventManager = EventManager(db)
        self.ticket: TicketManager = TicketManager(db)
        self.tech: TechNewsManager = TechNewsManager(db)
        self.dev: DevPulseManager = DevPulseManager(db)
        self.tech_realtime: TechRealtimeManager = TechRealtimeManager(db)
        self.temp_voice: TempVoiceManager = TempVoiceManager(db)
        self.translator: TranslatorManager = TranslatorManager(db)
        self.sticky: StickyManager = StickyManager(db)
        self.antinuke: AntinukeManager = AntinukeManager(db)
        self.media: MediaManager = MediaManager(db)
        self.giveaway: GiveawayManager = GiveawayManager(db)

        # Domain Concurrency Locks: Prevents simultaneous write race conditions per guild
        self._domain_locks: dict[str, dict[int, asyncio.Lock]] = {
            "ticket": {},
            "antinuke": {},
            "meeting": {},
            "premium": {},
        }

    def get_lock(self, domain: str, guild_id: int) -> asyncio.Lock:
        """Retrieve or create an isolated async mutex lock for a specific guild & domain."""
        if domain not in self._domain_locks:
            self._domain_locks[domain] = {}
        locks = self._domain_locks[domain]
        if guild_id not in locks:
            locks[guild_id] = asyncio.Lock()
        return locks[guild_id]

    async def load_all(self) -> None:
        """
        Fault-tolerant cache hydration.
        Each manager loads in an isolated try-except block so a single DB glitch
        in one domain NEVER cascades to break other features.
        """
        hydration_targets = [
            ("GuildManager", self.guild.load_cache),
            ("PermissionManager", self.perm.load_cache),
            ("BlacklistManager", self.blacklist.load_cache),
            ("SystemManager", self.system.load_cache),
            ("LogManager", self.log.load_cache),
            ("PremiumManager", self.premium.load_cache),
            ("TicketManager", self.ticket.load_cache),
            ("TechNewsManager", self.tech.load_cache),
            ("DevPulseManager", self.dev.load_cache),
            ("TechRealtimeManager", self.tech_realtime.initialize),
            ("TempVoiceManager", self.temp_voice.load_cache),
            ("TranslatorManager", self.translator.load_cache),
            ("StickyManager", self.sticky.load_cache),
            ("AntinukeManager", self.antinuke.load_cache),
            ("MediaManager", self.media.load_cache),
            ("GiveawayManager", self.giveaway.load_cache),
        ]

        logger.info(f"Initiating fault-tolerant hydration for {len(hydration_targets)} domain services...")
        success_count = 0
        for name, load_fn in hydration_targets:
            try:
                await load_fn()
                success_count += 1
            except Exception as e:
                logger.error(f"ServiceRegistry: Isolated notice during {name} hydration: {e}", exc_info=e)

        logger.info(f"ServiceRegistry: {success_count}/{len(hydration_targets)} domain services successfully hydrated.")
