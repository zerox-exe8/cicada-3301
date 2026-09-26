"""
Kyro Discord Bot - Visual Anime Clash & Shadow Arena
Authentic high-resolution Anime RPG & Battle System.
Features:
- Real anime character illustrations & exact anime series display
- Live turn-based HP combat arena with iconic moves & element synergies
- Unboxing vault with radiant gacha reveal cards
- Hunter License progression, ranks, and themes
- Discord Components V2 Containers with zero emoji spam and in-place updates
"""

from __future__ import annotations

import asyncio
import io
import random
from typing import Any

import discord
from discord.ext import commands

from src.core.bot import KyroBot
from src.core.context import CustomContext
from src.utils.anime_canvas import (
    ELEMENT_DATA,
    HUNTER_BANNERS,
    RARITY_COLORS,
    THEMES,
    render_battle_clash,
    render_chest_open_card,
    render_hunter_profile,
)
from src.utils.containers import (
    KyroContainer,
    edit_container_response,
    send_container_response,
)
from src.utils.image_tools import download_image_bytes


# ==========================================
# MASTER ANIME HERO REGISTRY (20 Champions)
# ==========================================
HERO_REGISTRY: dict[str, dict[str, Any]] = {
    # --- COMMON HEROES (Base: 500 - 580) ---
    "tanjiro": {
        "id": "tanjiro",
        "name": "Tanjiro Kamado",
        "anime": "Demon Slayer",
        "rarity": "Common",
        "element": "Water",
        "power": 500,
        "stars": 1,
        "move": "Water Breathing: Tenth Form",
    },
    "zenitsu": {
        "id": "zenitsu",
        "name": "Zenitsu Agatsuma",
        "anime": "Demon Slayer",
        "rarity": "Common",
        "element": "Lightning",
        "power": 520,
        "stars": 1,
        "move": "Thunderclap and Flash: Sixfold",
    },
    "deku": {
        "id": "deku",
        "name": "Izuku Midoriya",
        "anime": "My Hero Academia",
        "rarity": "Common",
        "element": "Physical",
        "power": 540,
        "stars": 1,
        "move": "Detroit Smash: 100% Impact",
    },

    # --- RARE HEROES (Base: 620 - 720) ---
    "killua": {
        "id": "killua",
        "name": "Killua Zoldyck",
        "anime": "Hunter x Hunter",
        "rarity": "Rare",
        "element": "Lightning",
        "power": 650,
        "stars": 2,
        "move": "Godspeed: Whirlwind",
    },
    "megumi": {
        "id": "megumi",
        "name": "Megumi Fushiguro",
        "anime": "Jujutsu Kaisen",
        "rarity": "Rare",
        "element": "Shadow",
        "power": 610,
        "stars": 2,
        "move": "Chimera Shadow Garden",
    },
    "choso": {
        "id": "choso",
        "name": "Choso",
        "anime": "Jujutsu Kaisen",
        "rarity": "Rare",
        "element": "Physical",
        "power": 660,
        "stars": 2,
        "move": "Blood Manipulation: Piercing Blood",
    },

    # --- EPIC HEROES (Base: 780 - 860) ---
    "zoro": {
        "id": "zoro",
        "name": "Roronoa Zoro",
        "anime": "One Piece",
        "rarity": "Epic",
        "element": "Wind",
        "power": 820,
        "stars": 3,
        "move": "King of Hell: Three Dragon Slash",
    },
    "levi": {
        "id": "levi",
        "name": "Levi Ackerman",
        "anime": "Attack on Titan",
        "rarity": "Epic",
        "element": "Wind",
        "power": 790,
        "stars": 3,
        "move": "Spiral Blade Tempest",
    },
    "toji": {
        "id": "toji",
        "name": "Toji Fushiguro",
        "anime": "Jujutsu Kaisen",
        "rarity": "Epic",
        "element": "Physical",
        "power": 840,
        "stars": 3,
        "move": "Inverted Spear of Heaven",
    },
    "itachi": {
        "id": "itachi",
        "name": "Itachi Uchiha",
        "anime": "Naruto",
        "rarity": "Epic",
        "element": "Fire",
        "power": 850,
        "stars": 3,
        "move": "Tsukuyomi and Black Flames",
    },
    "rengoku": {
        "id": "rengoku",
        "name": "Kyojuro Rengoku",
        "anime": "Demon Slayer",
        "rarity": "Epic",
        "element": "Fire",
        "power": 830,
        "stars": 3,
        "move": "Flame Breathing: Ninth Form Purgatory",
    },

    # --- LEGENDARY HEROES (Base: 940 - 990) ---
    "gojo": {
        "id": "gojo",
        "name": "Gojo Satoru",
        "anime": "Jujutsu Kaisen",
        "rarity": "Legendary",
        "element": "Shadow",
        "power": 970,
        "stars": 4,
        "move": "Hollow Technique: Purple",
    },
    "sukuna": {
        "id": "sukuna",
        "name": "Ryomen Sukuna",
        "anime": "Jujutsu Kaisen",
        "rarity": "Legendary",
        "element": "Fire",
        "power": 980,
        "stars": 4,
        "move": "Malevolent Shrine: Cleave and Dismantle",
    },
    "jinwoo": {
        "id": "jinwoo",
        "name": "Sung Jin-Woo",
        "anime": "Solo Leveling",
        "rarity": "Legendary",
        "element": "Shadow",
        "power": 990,
        "stars": 4,
        "move": "ARISE: Monarch of Shadows",
    },
    "luffy": {
        "id": "luffy",
        "name": "Monkey D. Luffy",
        "anime": "One Piece",
        "rarity": "Legendary",
        "element": "Lightning",
        "power": 950,
        "stars": 4,
        "move": "Gear 5: Bajrang Sun God Gun",
    },
    "madara": {
        "id": "madara",
        "name": "Madara Uchiha",
        "anime": "Naruto",
        "rarity": "Legendary",
        "element": "Fire",
        "power": 960,
        "stars": 4,
        "move": "Tengai Shinsei: Dual Heavenly Meteor",
    },

    # --- MYTHIC DIVINE HEROES (Base: 1060 - 1100) ---
    "jinwoo_monarch": {
        "id": "jinwoo_monarch",
        "name": "Awakened Shadow Monarch",
        "anime": "Solo Leveling",
        "rarity": "Mythic",
        "element": "Shadow",
        "power": 1080,
        "stars": 5,
        "move": "Domain of Monarch: Death Extraction",
    },
    "sukuna_true": {
        "id": "sukuna_true",
        "name": "Heian Form Sukuna",
        "anime": "Jujutsu Kaisen",
        "rarity": "Mythic",
        "element": "Fire",
        "power": 1090,
        "stars": 5,
        "move": "World Cutting Slash: Spatial Dismantle",
    },
}

# Cursed Anime Weapons & Relics Registry (Equippable onto Hunter for Power Bonus)
RELIC_REGISTRY: dict[str, dict[str, Any]] = {
    "kamish_wrath": {
        "id": "kamish_wrath",
        "name": "Kamish's Wrath Daggers",
        "anime": "Solo Leveling",
        "rarity": "Mythic",
        "power": 150,
        "effect": "+150 Combat Power in all battles",
    },
    "inverted_spear": {
        "id": "inverted_spear",
        "name": "Inverted Spear of Heaven",
        "anime": "Jujutsu Kaisen",
        "rarity": "Legendary",
        "power": 130,
        "effect": "+130 Combat Power & Technique Nullify",
    },
    "sukuna_finger": {
        "id": "sukuna_finger",
        "name": "Sukuna's Cursed Finger",
        "anime": "Jujutsu Kaisen",
        "rarity": "Legendary",
        "power": 125,
        "effect": "+125 Combat Power & Cursed Aura",
    },
    "enma_blade": {
        "id": "enma_blade",
        "name": "Enma Cursed Katana",
        "anime": "One Piece",
        "rarity": "Legendary",
        "power": 120,
        "effect": "+120 Combat Power & Haki Infusion",
    },
    "nichirin_blade": {
        "id": "nichirin_blade",
        "name": "Demon Slayer Black Blade",
        "anime": "Demon Slayer",
        "rarity": "Epic",
        "power": 90,
        "effect": "+90 Combat Power & Sun Breathing Flow",
    },
    "playful_cloud": {
        "id": "playful_cloud",
        "name": "Playful Cloud Staff",
        "anime": "Jujutsu Kaisen",
        "rarity": "Epic",
        "power": 85,
        "effect": "+85 Combat Power & Pure Force",
    },
    "odm_blades": {
        "id": "odm_blades",
        "name": "Dual Ultra-Hard Steel Blades",
        "anime": "Attack on Titan",
        "rarity": "Rare",
        "power": 60,
        "effect": "+60 Combat Power & Agile Slashes",
    },
    "kunai_set": {
        "id": "kunai_set",
        "name": "Chakra Infused Kunai",
        "anime": "Naruto",
        "rarity": "Common",
        "power": 40,
        "effect": "+40 Combat Power",
    },
}

# Champion Battle Quotes & Critical Strike Cries
CHAMPION_BATTLE_LINES: dict[str, dict[str, str]] = {
    "tanjiro": {
        "cry": "Never give up! Set your heart ablaze!",
        "crit": "Water Breathing, Tenth Form: Constant Flux!",
    },
    "zenitsu": {
        "cry": "Thunderclap and Flash... Godspeed!",
        "crit": "I will protect them with everything I have!",
    },
    "deku": {
        "cry": "One For All... 100% Full Cowling!",
        "crit": "DETROIT SMASH!",
    },
    "killua": {
        "cry": "Too slow... Lightning flows through my veins.",
        "crit": "Godspeed Whirlwind!",
    },
    "megumi": {
        "cry": "Chimera Shadow Garden, unfold!",
        "crit": "With this treasure I summon... Eight-Handled Sword!",
    },
    "choso": {
        "cry": "As an older brother, I will never yield!",
        "crit": "Blood Manipulation: Piercing Blood!",
    },
    "zoro": {
        "cry": "Nine Mountains, Eight Seas... I will become the King of Hell!",
        "crit": "Three Thousand Worlds!",
    },
    "levi": {
        "cry": "Give up on your dreams and die. Spiral slash!",
        "crit": "You have no idea how fast I am.",
    },
    "toji": {
        "cry": "Sorry kid, nothing personal. Just business.",
        "crit": "Inverted Spear of Heaven pierce!",
    },
    "itachi": {
        "cry": "You are already trapped in my Tsukuyomi.",
        "crit": "Amaterasu... burn to ashes!",
    },
    "rengoku": {
        "cry": "Set your heart ablaze! Go beyond your limits!",
        "crit": "Flame Breathing, Ninth Form: Purgatory!",
    },
    "gojo": {
        "cry": "Throughout heaven and earth, I alone am the honored one.",
        "crit": "Domain Expansion: Infinite Void... Hollow Purple!",
    },
    "sukuna": {
        "cry": "Know your place, fool. Stand proud.",
        "crit": "Domain Expansion: Malevolent Shrine! Dismantle!",
    },
    "sukuna_true": {
        "cry": "Fools, behold true Jujutsu magnificence!",
        "crit": "World Cutting Slash!",
    },
    "jinwoo": {
        "cry": "ARISE. The hunt begins now.",
        "crit": "Shadow Army, slaughter them all!",
    },
    "jinwoo_monarch": {
        "cry": "I am the Monarch of Shadows. Bow before Death.",
        "crit": "Cataclysmic Shadow Realm Extraction!",
    },
    "luffy": {
        "cry": "I'm gonna be the King of the Pirates! Gear 5!",
        "crit": "BAJRANG GUN!",
    },
    "madara": {
        "cry": "Do not misunderstand... this is not power of your creation!",
        "crit": "Dual Heavenly Tengai Shinsei Meteor!",
    },
}

# Elemental Advantage Matrix (+15% damage bonus)
ELEMENT_ADVANTAGE: dict[str, str] = {
    "Fire": "Wind",
    "Wind": "Lightning",
    "Lightning": "Water",
    "Water": "Fire",
    "Shadow": "Physical",
    "Physical": "Shadow",
}

RANK_THRESHOLDS: list[tuple[int, str]] = [
    (0, "E-Rank"),
    (5, "D-Rank"),
    (15, "C-Rank"),
    (30, "B-Rank"),
    (50, "A-Rank"),
    (80, "S-Rank"),
    (120, "National Monarch"),
]

# Champion Ultimate Moves & Domain Expansions (Triggered at 100% Cursed Energy)
CHAMPION_ULTIMATES: dict[str, dict[str, Any]] = {
    "tanjiro": {
        "name": "Hinokami Kagura: Sun Halo Dragon",
        "domain": "Blazing Sun Dance",
        "quote": "Set your heart ablaze! Hinokami Kagura: Sun Halo Dragon Head Dance!",
        "dmg_mult": 2.2,
    },
    "zenitsu": {
        "name": "Seventh Form: Honoikazuchi no Kami",
        "domain": "Flaming Thunder God",
        "quote": "Thunder Breathing, Seventh Form... Flaming Thunder God!",
        "dmg_mult": 2.3,
    },
    "deku": {
        "name": "One For All 100%: United States of Smash",
        "domain": "Vestiges Resonance",
        "quote": "I have to be the symbol of peace! UNITED STATES OF SMASH!",
        "dmg_mult": 2.2,
    },
    "killua": {
        "name": "Godspeed: Thunderbolt Whirlwind",
        "domain": "Electric Aura Field",
        "quote": "If you move even a millimeter, I will tear your throat out. GODSPEED!",
        "dmg_mult": 2.25,
    },
    "megumi": {
        "name": "Domain Expansion: Chimera Shadow Garden",
        "domain": "Chimera Shadow Garden",
        "quote": "Domain Expansion... Chimera Shadow Garden! With this treasure I summon!",
        "dmg_mult": 2.4,
    },
    "choso": {
        "name": "Blood Manipulation: Supernova",
        "domain": "Crimson Blood Realm",
        "quote": "As an older brother, I will protect you to the bitter end! SUPERNOVA!",
        "dmg_mult": 2.2,
    },
    "zoro": {
        "name": "King of Hell, Three-Sword Serpent: 103 Mercies",
        "domain": "King of Hell Domain",
        "quote": "I promised Luffy... I will never lose again! King of Hell, Three-Sword Serpent!",
        "dmg_mult": 2.35,
    },
    "levi": {
        "name": "Spur Slash: Beyond the Walls",
        "domain": "Survey Corps Blade Dance",
        "quote": "Give up on your dreams and die. Spiral slash!",
        "dmg_mult": 2.3,
    },
    "toji": {
        "name": "Heavenly Restriction: Soul Splitter",
        "domain": "Zero Cursed Energy Purge",
        "quote": "You should have died in the gutter like the rest of us. Inverted Spear pierce!",
        "dmg_mult": 2.4,
    },
    "itachi": {
        "name": "Tsukuyomi & Susanoo Totsuka Blade",
        "domain": "Infinite Tsukuyomi Realm",
        "quote": "You are weak because you lack hatred... Susanoo Totsuka Blade Seal!",
        "dmg_mult": 2.45,
    },
    "rengoku": {
        "name": "Flame Breathing Ninth Form: Rengoku",
        "domain": "Purgatory Heart",
        "quote": "SET YOUR HEART ABLAZE! Ninth Form: PURGATORY!",
        "dmg_mult": 2.4,
    },
    "gojo": {
        "name": "Domain Expansion: Infinite Void",
        "domain": "Infinite Void",
        "quote": "Throughout heaven and earth, I alone am the honored one. Domain Expansion: Infinite Void... Hollow Purple!",
        "dmg_mult": 2.6,
    },
    "sukuna": {
        "name": "Domain Expansion: Malevolent Shrine",
        "domain": "Malevolent Shrine",
        "quote": "Domain Expansion: Malevolent Shrine! Dismantle and Cleave until nothing remains!",
        "dmg_mult": 2.6,
    },
    "sukuna_true": {
        "name": "World Cutting Slash: Spatial Severance",
        "domain": "True Form Malevolent Shrine",
        "quote": "Scale of the Dragon. Recoil. Twin Meteors. World Cutting Slash!",
        "dmg_mult": 2.7,
    },
    "jinwoo": {
        "name": "Ruler's Authority & Shadow Extraction: Arise",
        "domain": "Shadow Sovereign Territory",
        "quote": "The hunt begins now. ARISE, my soldiers!",
        "dmg_mult": 2.5,
    },
    "jinwoo_monarch": {
        "name": "Monarch of Shadows: Cataclysmic Annihilation",
        "domain": "Domain of the Monarch",
        "quote": "I am the Monarch of Shadows. Bow before the ruler of Death!",
        "dmg_mult": 2.7,
    },
    "luffy": {
        "name": "Gear 5: Bajrang Gun",
        "domain": "Sun God Nika Domain",
        "quote": "AHAHAHA! I can do whatever I want now! GOMU GOMU NO BAJRANG GUN!",
        "dmg_mult": 2.5,
    },
    "madara": {
        "name": "Perfect Susanoo & Tengai Shinsei Dual Meteors",
        "domain": "Sovereign Susanoo Domain",
        "quote": "Would you like these clones to use Susanoo or not? Tengai Shinsei!",
        "dmg_mult": 2.6,
    },
}

THEME_ORDER = ["shadow", "crimson", "cyber", "gold"]


class AnimeClash(commands.Cog):
    """Visual Anime Clash & Shadow Arena Game Cog."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot: KyroBot = bot
        self._schema_initialized = False
        self.recent_rivals: dict[int, list[str]] = {}

    async def cog_load(self) -> None:
        """Initialize database schema on cog startup."""
        await self._init_db()

    async def _init_db(self) -> None:
        """Ensure postgres tables exist for Anime Clash."""
        if self._schema_initialized:
            return

        queries = [
            """
            CREATE TABLE IF NOT EXISTS game_anime_profiles (
                user_id BIGINT PRIMARY KEY,
                hunter_rank VARCHAR(32) DEFAULT 'E-Rank',
                level INT DEFAULT 1,
                xp INT DEFAULT 0,
                gold BIGINT DEFAULT 150,
                wins INT DEFAULT 0,
                losses INT DEFAULT 0,
                win_streak INT DEFAULT 0,
                equipped_hero_id VARCHAR(64) DEFAULT 'tanjiro',
                theme VARCHAR(32) DEFAULT 'shadow',
                custom_title VARCHAR(64) DEFAULT 'Rookie Hunter',
                chests_bronze INT DEFAULT 1,
                chests_silver INT DEFAULT 0,
                chests_epic INT DEFAULT 0,
                chests_monarch INT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS game_anime_inventory (
                user_id BIGINT NOT NULL,
                hero_id VARCHAR(64) NOT NULL,
                stars INT DEFAULT 1,
                power_bonus INT DEFAULT 0,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, hero_id)
            );
            """,
        ]
        for q in queries:
            try:
                await self.bot.db.execute(q)
            except Exception as e:
                self.bot.logger.debug(f"Anime DB schema query notice: {e}")

        alter_queries = [
            "ALTER TABLE game_anime_profiles ADD COLUMN IF NOT EXISTS banner VARCHAR(64) DEFAULT 'shadow_realm';",
            "ALTER TABLE game_anime_profiles ADD COLUMN IF NOT EXISTS banners_unlocked TEXT DEFAULT 'shadow_realm';",
            "ALTER TABLE game_anime_profiles ADD COLUMN IF NOT EXISTS relic_id VARCHAR(64) DEFAULT NULL;",
            "ALTER TABLE game_anime_profiles ADD COLUMN IF NOT EXISTS relic_power INT DEFAULT 0;",
            "ALTER TABLE game_anime_profiles ADD COLUMN IF NOT EXISTS relics_unlocked TEXT DEFAULT '';",
            "ALTER TABLE game_anime_profiles ADD COLUMN IF NOT EXISTS healing_potions INT DEFAULT 0;",
        ]
        for q in alter_queries:
            try:
                await self.bot.db.execute(q)
            except Exception as e:
                self.bot.logger.debug(f"Anime DB alter notice: {e}")

        self._schema_initialized = True

    async def get_or_create_profile(self, user_id: int) -> dict[str, Any]:
        """Fetch or insert starter player profile."""
        await self._init_db()
        row = await self.bot.db.fetch_one(
            "SELECT * FROM game_anime_profiles WHERE user_id = $1;", user_id
        )
        if not row:
            await self.bot.db.execute(
                """
                INSERT INTO game_anime_profiles (user_id, gold, chests_bronze, equipped_hero_id)
                VALUES ($1, 150, 1, 'tanjiro')
                ON CONFLICT (user_id) DO NOTHING;
                """,
                user_id,
            )
            # Give starter hero Tanjiro
            await self.bot.db.execute(
                """
                INSERT INTO game_anime_inventory (user_id, hero_id, stars, power_bonus)
                VALUES ($1, 'tanjiro', 1, 0)
                ON CONFLICT (user_id, hero_id) DO NOTHING;
                """,
                user_id,
            )
            row = await self.bot.db.fetch_one(
                "SELECT * FROM game_anime_profiles WHERE user_id = $1;", user_id
            )

        return dict(row) if row else {}

    async def get_user_heroes(self, user_id: int) -> list[dict[str, Any]]:
        """Return list of all unlocked anime heroes with active stats."""
        rows = await self.bot.db.fetch_all(
            "SELECT * FROM game_anime_inventory WHERE user_id = $1 ORDER BY stars DESC, power_bonus DESC;",
            user_id,
        )
        user_heroes: list[dict[str, Any]] = []
        for r in rows:
            h_id = r["hero_id"]
            if h_id in HERO_REGISTRY:
                base = HERO_REGISTRY[h_id].copy()
                base["stars"] = r["stars"]
                base["power_bonus"] = r["power_bonus"]
                user_heroes.append(base)
        return user_heroes

    async def get_equipped_hero(self, profile: dict[str, Any]) -> dict[str, Any]:
        """Fetch the equipped hero details."""
        user_id = profile.get("user_id", 0)
        equipped_id = profile.get("equipped_hero_id") or "tanjiro"

        row = None
        if user_id:
            row = await self.bot.db.fetch_one(
                "SELECT * FROM game_anime_inventory WHERE user_id = $1 AND hero_id = $2;",
                user_id,
                equipped_id,
            )
        if not row or equipped_id not in HERO_REGISTRY:
            base = HERO_REGISTRY.get(equipped_id, HERO_REGISTRY["tanjiro"]).copy()
            base["stars"] = 1
            base["power_bonus"] = 0
            return base

        base = HERO_REGISTRY[equipped_id].copy()
        base["stars"] = row.get("stars", 1) if isinstance(row, dict) else (row["stars"] if hasattr(row, "__getitem__") else 1)
        base["power_bonus"] = row.get("power_bonus", 0) if isinstance(row, dict) else (row["power_bonus"] if hasattr(row, "__getitem__") else 0)
        # Add player's equipped relic / weapon power bonus
        base["power_bonus"] += profile.get("relic_power", 0)
        return base

    def compute_rank(self, wins: int) -> str:
        """Calculate Hunter Rank based on lifetime victories."""
        current_rank = "E-Rank"
        for thresh, title in RANK_THRESHOLDS:
            if wins >= thresh:
                current_rank = title
        return current_rank

    async def render_profile_container(
        self, user: discord.Member | discord.User, profile: dict[str, Any]
    ) -> tuple[KyroContainer, discord.File, ProfileHubView]:
        """Build and render the Hunter License container, image file, and action view."""
        equipped_hero = await self.get_equipped_hero(profile)
        user_heroes = await self.get_user_heroes(user.id)

        av_bytes: bytes | None = None
        # 1. Primary: Download via bot.session HTTP client
        if hasattr(self.bot, "session") and self.bot.session and hasattr(user, "display_avatar") and user.display_avatar:
            try:
                av_url = str(user.display_avatar.replace(size=256, static_format="png").url)
                av_bytes = await download_image_bytes(av_url, self.bot.session)
            except Exception:
                try:
                    av_bytes = await download_image_bytes(str(user.display_avatar.url), self.bot.session)
                except Exception:
                    pass

        # 2. Secondary fallback: internal discord.py asset read
        if not av_bytes and hasattr(user, "display_avatar") and user.display_avatar:
            try:
                av_bytes = await user.display_avatar.read()
            except Exception:
                try:
                    av_bytes = await user.default_avatar.read()
                except Exception:
                    pass

        lvl = profile.get("level", 1)
        xp = profile.get("xp", 0)
        xp_needed = lvl * 250
        rank = self.compute_rank(profile.get("wins", 0))

        chests_total = (
            profile.get("chests_bronze", 0)
            + profile.get("chests_silver", 0)
            + profile.get("chests_epic", 0)
            + profile.get("chests_monarch", 0)
        )

        active_banner = profile.get("banner") or profile.get("theme", "shadow_realm")
        img_buffer = await asyncio.to_thread(
            render_hunter_profile,
            avatar_bytes=av_bytes,
            username=user.display_name,
            title=profile.get("custom_title", "Rookie Hunter"),
            rank=rank,
            level=lvl,
            xp=xp,
            xp_needed=xp_needed,
            wins=profile.get("wins", 0),
            losses=profile.get("losses", 0),
            streak=profile.get("win_streak", 0),
            gold=profile.get("gold", 150),
            chests_count=chests_total,
            hero_data=equipped_hero,
            theme_key=active_banner,
        )

        discord_file = discord.File(img_buffer, filename="hunter_profile.png")

        # Container Interface with clean Media Gallery attachment (no redundant text)
        container = KyroContainer(accent_color=None)
        container.add_media("attachment://hunter_profile.png")

        view = ProfileHubView(self, user, profile, user_heroes)
        return container, discord_file, view

    # ==========================================
    # COMMAND: !hunter / !hp
    # ==========================================
    @commands.command(name="hunter", aliases=["hp", "hunterprofile", "shadowprofile"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def hunter_cmd(self, ctx: CustomContext, target: discord.Member | None = None) -> None:
        """Display high-resolution Hunter License Profile Card and Vault."""
        user = target or ctx.author
        profile = await self.get_or_create_profile(user.id)
        container, discord_file, view = await self.render_profile_container(user, profile)
        await send_container_response(ctx, container, file=discord_file, view=view)

    # ==========================================
    # COMMAND: !battle (Solo Turn Duel or 1v1 PvP)
    # ==========================================
    @commands.command(name="battle", aliases=["fight", "clash", "duel"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def battle_cmd(self, ctx: CustomContext, opponent: discord.Member | None = None) -> None:
        """
        Jump into Anime Clash Arena!
        - Alone: `!battle` matches you with a wild anime rival instantly for an interactive turn battle.
        - With friend: `!battle @user` issues a 1v1 challenge.
        """
        p1 = ctx.author
        p1_profile = await self.get_or_create_profile(p1.id)
        p1_heroes = await self.get_user_heroes(p1.id)

        if not p1_heroes:
            p1_heroes = [HERO_REGISTRY["tanjiro"].copy()]

        # 1. 1v1 PVP DUEL CHALLENGE
        if opponent and opponent.id != p1.id:
            if opponent.bot:
                await ctx.send_error("You cannot challenge bots to a duel! Use `!battle` to fight AI rivals.")
                return

            p2_profile = await self.get_or_create_profile(opponent.id)
            p2_heroes = await self.get_user_heroes(opponent.id)

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"### Anime Duel Challenge!\n"
                    f"> **{p1.mention}** has challenged **{opponent.mention}** to a Shadow Arena duel!\n\n"
                    f"> Opponent has 45 seconds to accept."
                )
            )
            view = PvPInviteView(self, ctx, p1, opponent, p1_heroes, p2_heroes)
            await send_container_response(ctx, container, view=view)
            return

        # 2. SOLO REAL-TIME TURN DUEL
        p1_main = await self.get_equipped_hero(p1_profile)
        p1_power = p1_main["power"] + p1_main.get("power_bonus", 0)

        # Matchmaking from rank pool with anti-repetition memory
        rank = p1_profile.get("hunter_rank", "E-Rank")
        if rank in ["E-Rank", "D-Rank"]:
            pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Common", "Rare"]]
        elif rank in ["C-Rank", "B-Rank"]:
            pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Rare", "Epic"]]
        else:
            pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Epic", "Legendary", "Mythic"]]

        if not pool:
            pool = list(HERO_REGISTRY.keys())

        # Filter out player's equipped hero (no mirror) and recently encountered rivals
        user_recent = self.recent_rivals.get(p1.id, [])
        eligible_pool = [k for k in pool if k != p1_main["id"] and k not in user_recent]
        if not eligible_pool:
            # If recent memory exhausted pool, only exclude the immediate last rival and self
            last_rival = user_recent[-1] if user_recent else None
            eligible_pool = [k for k in pool if k != p1_main["id"] and k != last_rival]
        if not eligible_pool:
            eligible_pool = [k for k in HERO_REGISTRY.keys() if k != p1_main["id"]]
        if not eligible_pool:
            eligible_pool = list(HERO_REGISTRY.keys())

        rival_id = random.choice(eligible_pool)
        user_recent.append(rival_id)
        if len(user_recent) > 4:
            user_recent.pop(0)
        self.recent_rivals[p1.id] = user_recent

        rival_hero = HERO_REGISTRY[rival_id].copy()

        # Balance rival power close to player's power (+/- 6%)
        scale = random.uniform(0.93, 1.05)
        rival_hero["power"] = max(420, int(p1_power * scale))
        rival_hero["power_bonus"] = 0

        # Render initial Round 1 Battle Arena Card
        card_buf = await asyncio.to_thread(
            render_battle_clash,
            player1_name=p1.display_name,
            player1_hero=p1_main,
            p1_hp=100,
            p1_max_hp=100,
            player2_name="AI Rival",
            player2_hero=rival_hero,
            p2_hp=100,
            p2_max_hp=100,
            winner_num=0,
            turn_action_text=f"ROUND 1: Duel Initiated! Choose your combat action below.",
            p1_energy=0,
            p2_energy=0,
            domain_active=None,
        )
        discord_file = discord.File(card_buf, filename="battle_clash.png")

        container = KyroContainer(accent_color=None)
        container.add_media("attachment://battle_clash.png")
        container.add_section(
            content=(
                f"### Rival Encountered: {rival_hero['name'].upper()}!\n"
                f"> **Your Champion:** **{p1_main['name']}** (« {p1_main.get('anime', 'Anime')} ») • `100/100 HP` | [{p1_main['element']}]\n"
                f"> **Rival Fighter:** **{rival_hero['name']}** (« {rival_hero.get('anime', 'Anime')} ») • `100/100 HP` | [{rival_hero['element']}]\n"
                f"> Strike using the combat buttons below!"
            )
        )

        view = SoloBattleSessionView(self, ctx, p1, p1_main, rival_hero, p1_profile)
        await send_container_response(ctx, container, file=discord_file, view=view)

    # ==========================================
    # COMMAND: !powers / !lore / !animeinfo (AniList API Live Lore)
    # ==========================================
    @commands.command(name="powers", aliases=["power", "animeinfo", "charinfo", "lore"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def powers_cmd(self, ctx: CustomContext, *, character_name: str) -> None:
        """
        Look up full canonical powers, abilities, and anime lore via AniList API.
        Example: `!powers Gojo`, `!powers Sukuna`, `!powers Madara`, `!powers Naruto`
        """
        search_query = character_name.strip()
        if not search_query:
            await ctx.send_error("Please specify an anime character name! Example: `!powers Satoru Gojo`")
            return

        graphql_query = """
        query ($search: String) {
          Character (search: $search) {
            id
            name {
              full
              native
              alternative
            }
            image {
              large
            }
            description
            media (perPage: 1, sort: POPULARITY_DESC) {
              nodes {
                title {
                  romaji
                  english
                }
              }
            }
          }
        }
        """

        session = self.bot.session
        if not session:
            await ctx.send_error("Bot HTTP session is not ready. Please try again.")
            return

        try:
            async with session.post(
                "https://graphql.anilist.co",
                json={"query": graphql_query, "variables": {"search": search_query}},
                headers={"Content-Type": "application/json", "User-Agent": "KyroBot/1.0"},
                timeout=10,
            ) as resp:
                if resp.status != 200:
                    await ctx.send_error(f"Character `{search_query}` not found on AniList database.")
                    return
                data = await resp.json()
                char = data.get("data", {}).get("Character")
                if not char:
                    await ctx.send_error(f"Character `{search_query}` not found.")
                    return
        except Exception as e:
            await ctx.send_error(f"Failed to fetch character powers: {e}")
            return

        full_name = char["name"]["full"]
        native_name = char["name"].get("native") or ""
        alt_names = char["name"].get("alternative") or []
        alias_str = f" • AKA: {', '.join(alt_names[:2])}" if alt_names else ""

        media_nodes = char.get("media", {}).get("nodes", [])
        anime_title = "Unknown Anime"
        if media_nodes:
            anime_title = media_nodes[0].get("title", {}).get("english") or media_nodes[0].get("title", {}).get("romaji", "Anime Series")

        raw_desc = char.get("description") or "No canonical ability summary available on AniList."
        # Clean spoiler tags, markdown formatting
        clean_desc = raw_desc.replace("~!~", "").replace("~!", "").replace("!~", "")
        clean_desc = clean_desc.replace("__", "").replace("**", "")
        if len(clean_desc) > 650:
            clean_desc = clean_desc[:650] + "..."

        container = KyroContainer(accent_color=None)
        img_url = char.get("image", {}).get("large")
        if img_url:
            container.add_media(img_url)

        container.add_section(
            content=(
                f"### {full_name.upper()} {f'({native_name})' if native_name else ''}\n"
                f"> **Origin Anime:** « {anime_title} »{alias_str}\n"
                f"> **Canonical Powers & Lore:**\n"
                f"{clean_desc}\n\n"
                f"> ⚔️ *Tip: You can fight or summon this champion in `!battle` and `!hunter` chests!*"
            )
        )
        await send_container_response(ctx, container)


# ==========================================
# INTERACTIVE VIEWS & IN-PLACE ACTIONS
# ==========================================

class ProfileHubView(discord.ui.View):
    """Modular In-Place Action Bar for Player Profile (Zero annoying popups)."""

    def __init__(
        self,
        cog: AnimeClash,
        user: discord.Member | discord.User,
        profile: dict[str, Any],
        heroes: list[dict[str, Any]],
    ) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user
        self.profile = profile
        self.heroes = heroes

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("This is not your profile hub.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Open Chest", style=discord.ButtonStyle.primary)
    async def open_chests_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Instantly unbox the highest available chest with multi-tier loot variety."""
        b = self.profile.get("chests_bronze", 0)
        s = self.profile.get("chests_silver", 0)
        e = self.profile.get("chests_epic", 0)
        m = self.profile.get("chests_monarch", 0)

        # Pick highest available chest tier
        target_tier = None
        col_name = None
        if m > 0:
            target_tier, col_name = "monarch", "chests_monarch"
        elif e > 0:
            target_tier, col_name = "epic", "chests_epic"
        elif s > 0:
            target_tier, col_name = "silver", "chests_silver"
        elif b > 0:
            target_tier, col_name = "bronze", "chests_bronze"

        if not target_tier or not col_name:
            await interaction.response.send_message(
                "You have no Battle Chests in your vault. Win battles with `?battle` to earn chests!",
                ephemeral=True,
            )
            return

        # Deduct chest from database
        await self.cog.bot.db.execute(
            f"UPDATE game_anime_profiles SET {col_name} = {col_name} - 1 WHERE user_id = $1;",
            interaction.user.id,
        )
        self.profile[col_name] -= 1

        # Determine loot category & rewards based on chest tier
        if target_tier == "bronze":
            chest_display_name = "Bronze Battle Chest"
            gold_reward = random.randint(50, 120)
            loot_type = random.choices(["jackpot", "consumable", "relic", "hero"], weights=[35, 25, 20, 20])[0]
        elif target_tier == "silver":
            chest_display_name = "Silver Cursed Chest"
            gold_reward = random.randint(150, 280)
            loot_type = random.choices(["banner", "relic", "hero", "consumable", "jackpot"], weights=[25, 25, 25, 15, 10])[0]
        elif target_tier == "epic":
            chest_display_name = "Shadow Epic Chest"
            gold_reward = random.randint(300, 600)
            loot_type = random.choices(["relic", "banner", "hero", "jackpot"], weights=[30, 30, 25, 15])[0]
        else:  # monarch
            chest_display_name = "Monarch Divine Chest"
            gold_reward = random.randint(800, 1500)
            loot_type = random.choices(["hero", "relic", "banner"], weights=[35, 35, 30])[0]

        if loot_type == "relic":
            # Pool based on tier
            if target_tier == "bronze":
                pool = [k for k, v in RELIC_REGISTRY.items() if v["rarity"] in ["Common", "Rare"]]
            elif target_tier == "silver":
                pool = [k for k, v in RELIC_REGISTRY.items() if v["rarity"] in ["Rare", "Epic"]]
            elif target_tier == "epic":
                pool = [k for k, v in RELIC_REGISTRY.items() if v["rarity"] in ["Epic", "Legendary"]]
            else:
                pool = [k for k, v in RELIC_REGISTRY.items() if v["rarity"] in ["Legendary", "Mythic"]]
            if not pool:
                pool = list(RELIC_REGISTRY.keys())

            chosen_id = random.choice(pool)
            relic = RELIC_REGISTRY[chosen_id].copy()

            unlocked_raw = self.profile.get("relics_unlocked") or ""
            unlocked_list = [r.strip() for r in unlocked_raw.split(",") if r.strip()]
            is_dup = chosen_id in unlocked_list

            if not is_dup:
                unlocked_list.append(chosen_id)
                self.profile["relics_unlocked"] = ",".join(unlocked_list)
                if not self.profile.get("relic_id") or relic["power"] > self.profile.get("relic_power", 0):
                    self.profile["relic_id"] = chosen_id
                    self.profile["relic_power"] = relic["power"]

                await self.cog.bot.db.execute(
                    """
                    UPDATE game_anime_profiles 
                    SET relics_unlocked = $1, relic_id = $2, relic_power = $3, gold = gold + $4 
                    WHERE user_id = $5;
                    """,
                    ",".join(unlocked_list),
                    self.profile.get("relic_id"),
                    self.profile.get("relic_power", 0),
                    gold_reward,
                    interaction.user.id,
                )
            else:
                gold_reward += 200
                if self.profile.get("relic_id") == chosen_id:
                    self.profile["relic_power"] = self.profile.get("relic_power", 0) + 15
                    await self.cog.bot.db.execute(
                        "UPDATE game_anime_profiles SET relic_power = relic_power + 15, gold = gold + $1 WHERE user_id = $2;",
                        gold_reward,
                        interaction.user.id,
                    )
                else:
                    await self.cog.bot.db.execute(
                        "UPDATE game_anime_profiles SET gold = gold + $1 WHERE user_id = $2;",
                        gold_reward,
                        interaction.user.id,
                    )

            self.profile["gold"] = self.profile.get("gold", 150) + gold_reward
            card_buf = await asyncio.to_thread(
                render_chest_open_card,
                user_name=interaction.user.display_name,
                chest_type=chest_display_name,
                gold_reward=gold_reward,
                reward_type="relic",
                reward_data=relic,
                is_duplicate=is_dup,
            )
            section_msg = (
                f"### {chest_display_name.upper()} UNBOXED!\n"
                f"> **Cursed Relic:** **{relic['name']}** (« {relic.get('anime', 'Anime')} ») • `{relic['rarity'].upper()}`\n"
                f"> **Combat Perk:** `+{relic['power']} Power` boost ({relic.get('effect', '')})\n"
                f"> **Status:** {'Equipped to your Hunter!' if self.profile.get('relic_id') == chosen_id else 'Added to Relic Vault'}\n"
                f"> **Treasury Spoils:** `+{gold_reward} Gold` added to vault."
            )

        elif loot_type == "banner":
            if target_tier in ["bronze", "silver"]:
                pool = [k for k, v in HUNTER_BANNERS.items() if v["rarity"] in ["Common", "Rare", "Epic"]]
            elif target_tier == "epic":
                pool = [k for k, v in HUNTER_BANNERS.items() if v["rarity"] in ["Epic", "Legendary"]]
            else:
                pool = [k for k, v in HUNTER_BANNERS.items() if v["rarity"] in ["Legendary", "Mythic"]]
            if not pool:
                pool = list(HUNTER_BANNERS.keys())

            chosen_id = random.choice(pool)
            banner = HUNTER_BANNERS[chosen_id].copy()

            unlocked_raw = self.profile.get("banners_unlocked") or "shadow_realm"
            unlocked_list = [b.strip() for b in unlocked_raw.split(",") if b.strip()]
            is_dup = chosen_id in unlocked_list

            if not is_dup:
                unlocked_list.append(chosen_id)
                self.profile["banners_unlocked"] = ",".join(unlocked_list)
                self.profile["banner"] = chosen_id
                self.profile["theme"] = chosen_id
                await self.cog.bot.db.execute(
                    """
                    UPDATE game_anime_profiles 
                    SET banners_unlocked = $1, banner = $2, theme = $2, gold = gold + $3 
                    WHERE user_id = $4;
                    """,
                    ",".join(unlocked_list),
                    chosen_id,
                    gold_reward,
                    interaction.user.id,
                )
            else:
                gold_reward += 300
                await self.cog.bot.db.execute(
                    "UPDATE game_anime_profiles SET gold = gold + $1 WHERE user_id = $2;",
                    gold_reward,
                    interaction.user.id,
                )

            self.profile["gold"] = self.profile.get("gold", 150) + gold_reward
            card_buf = await asyncio.to_thread(
                render_chest_open_card,
                user_name=interaction.user.display_name,
                chest_type=chest_display_name,
                gold_reward=gold_reward,
                reward_type="banner",
                reward_data=banner,
                is_duplicate=is_dup,
            )
            section_msg = (
                f"### {chest_display_name.upper()} UNBOXED!\n"
                f"> **Hunter Banner:** **{banner['name']}** (« {banner.get('anime', 'Anime')} ») • `{banner['rarity'].upper()}`\n"
                f"> **Aesthetic:** {banner.get('desc', 'Custom Hunter Backdrop')}\n"
                f"> **Status:** Active on your Hunter License! `+{gold_reward} Gold` added."
            )

        elif loot_type == "consumable":
            await self.cog.bot.db.execute(
                "UPDATE game_anime_profiles SET healing_potions = healing_potions + 2, gold = gold + $1 WHERE user_id = $2;",
                gold_reward,
                interaction.user.id,
            )
            self.profile["healing_potions"] = self.profile.get("healing_potions", 0) + 2
            self.profile["gold"] = self.profile.get("gold", 150) + gold_reward
            card_buf = await asyncio.to_thread(
                render_chest_open_card,
                user_name=interaction.user.display_name,
                chest_type=chest_display_name,
                gold_reward=gold_reward,
                reward_type="consumable",
                reward_data={"name": "Healing Potion", "rarity": "Rare"},
            )
            section_msg = (
                f"### {chest_display_name.upper()} UNBOXED!\n"
                f"> **Battle Supplies:** `2x Healing Potions` added to your pouch!\n"
                f"> **Effect:** Recovers +35 HP during duels.\n"
                f"> **Treasury Spoils:** `+{gold_reward} Gold` added to vault."
            )

        elif loot_type == "jackpot":
            if target_tier == "bronze":
                jackpot_gold = random.randint(250, 450)
                bonus_xp = 100
            elif target_tier == "silver":
                jackpot_gold = random.randint(450, 800)
                bonus_xp = 150
            elif target_tier == "epic":
                jackpot_gold = random.randint(900, 1600)
                bonus_xp = 250
            else:
                jackpot_gold = random.randint(2000, 3500)
                bonus_xp = 400

            await self.cog.bot.db.execute(
                "UPDATE game_anime_profiles SET gold = gold + $1, xp = xp + $2 WHERE user_id = $3;",
                jackpot_gold,
                bonus_xp,
                interaction.user.id,
            )
            self.profile["gold"] = self.profile.get("gold", 150) + jackpot_gold
            self.profile["xp"] = self.profile.get("xp", 0) + bonus_xp
            card_buf = await asyncio.to_thread(
                render_chest_open_card,
                user_name=interaction.user.display_name,
                chest_type=chest_display_name,
                gold_reward=jackpot_gold,
                reward_type="jackpot",
                reward_data={"name": "Treasury Jackpot", "rarity": "Legendary"},
            )
            section_msg = (
                f"### {chest_display_name.upper()} UNBOXED!\n"
                f"> **ROYAL BOUNTY JACKPOT:** `+{jackpot_gold:,} Gold` deposited!\n"
                f"> **Hunter Surge:** `+{bonus_xp} XP` bonus added to level progression!"
            )

        else:  # hero
            if target_tier == "bronze":
                loot_pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Common", "Rare"]]
            elif target_tier == "silver":
                loot_pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Rare", "Epic"]]
            elif target_tier == "epic":
                loot_pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Epic", "Legendary"]]
            else:
                loot_pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Legendary", "Mythic"]]

            if not loot_pool:
                loot_pool = list(HERO_REGISTRY.keys())

            chosen_id = random.choice(loot_pool)
            hero = HERO_REGISTRY[chosen_id].copy()

            row = await self.cog.bot.db.fetch_one(
                "SELECT * FROM game_anime_inventory WHERE user_id = $1 AND hero_id = $2;",
                interaction.user.id,
                chosen_id,
            )

            is_dup = False
            if row:
                is_dup = True
                await self.cog.bot.db.execute(
                    "UPDATE game_anime_inventory SET power_bonus = power_bonus + 50 WHERE user_id = $1 AND hero_id = $2;",
                    interaction.user.id,
                    chosen_id,
                )
                hero["power_bonus"] = row["power_bonus"] + 50
                hero["stars"] = row["stars"]
            else:
                await self.cog.bot.db.execute(
                    "INSERT INTO game_anime_inventory (user_id, hero_id, stars, power_bonus) VALUES ($1, $2, $3, 0);",
                    interaction.user.id,
                    chosen_id,
                    hero["stars"],
                )
                self.heroes.append(hero)

            await self.cog.bot.db.execute(
                "UPDATE game_anime_profiles SET gold = gold + $1 WHERE user_id = $2;",
                gold_reward,
                interaction.user.id,
            )
            self.profile["gold"] = self.profile.get("gold", 150) + gold_reward

            card_buf = await asyncio.to_thread(
                render_chest_open_card,
                user_name=interaction.user.display_name,
                chest_type=chest_display_name,
                unlocked_hero=hero,
                is_duplicate=is_dup,
                gold_reward=gold_reward,
                reward_type="hero",
                reward_data=hero,
            )
            section_msg = (
                f"### {chest_display_name.upper()} UNBOXED!\n"
                f"> **Champion:** **{hero['name']}** (« {hero.get('anime', 'Anime')} ») • `{hero['rarity'].upper()}`\n"
                f"> **Status:** {'Duplicate Power Up (+50 Power)!' if is_dup else 'Brand New Champion Added!'}\n"
                f"> **Spoils:** `+{gold_reward} Gold` added to treasury."
            )

        file = discord.File(card_buf, filename="chest_reveal.png")
        container = KyroContainer(accent_color=None)
        container.add_media("attachment://chest_reveal.png")
        container.add_section(content=section_msg)

        reveal_view = ChestRevealedView(self.cog, self.user, self.profile, self.heroes)
        await edit_container_response(interaction, container, file=file, view=reveal_view)

    @discord.ui.button(label="Equip Banner", style=discord.ButtonStyle.secondary)
    async def equip_banner_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Display select menu to equip unlocked background banner in-place."""
        equip_view = EquipBannerView(self.cog, self.user, self.profile, self.heroes)
        container = KyroContainer(accent_color=None)
        unlocked_count = len([b for b in (self.profile.get("banners_unlocked") or "shadow_realm").split(",") if b.strip()])
        container.add_section(
            content=(
                f"### Hunter Profile Banners ({unlocked_count} Unlocked)\n"
                f"> Select a custom anime theme banner below to decorate your Hunter License:"
            )
        )
        await edit_container_response(interaction, container, view=equip_view)

    @discord.ui.button(label="Roster & Equip", style=discord.ButtonStyle.secondary)
    async def my_heroes_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Display select menu to equip any unlocked anime fighter in-place."""
        if not self.heroes:
            await interaction.response.send_message("No champions unlocked yet!", ephemeral=True)
            return

        equip_view = EquipRosterView(self.cog, self.user, self.profile, self.heroes)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Hunter Champion Roster ({len(self.heroes)} Unlocked)\n"
                f"> Select a champion from the dropdown below to equip as your main fighter:"
            )
        )
        await edit_container_response(interaction, container, view=equip_view)

    @discord.ui.button(label="Relic Vault", style=discord.ButtonStyle.secondary)
    async def relic_vault_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Display select menu to equip unlocked cursed weapon or relic."""
        raw_relics = self.profile.get("relics_unlocked") or ""
        unlocked_relic_ids = [r.strip() for r in raw_relics.split(",") if r.strip()]
        if not unlocked_relic_ids:
            await interaction.response.send_message(
                "You have no Cursed Relics or Anime Weapons yet! Open Battle Chests with `Open Chest` to loot rare relics.",
                ephemeral=True,
            )
            return

        equip_view = EquipRelicView(self.cog, self.user, self.profile, self.heroes)
        curr_relic = RELIC_REGISTRY.get(self.profile.get("relic_id", ""), {})
        active_str = f"**Equipped:** {curr_relic.get('name', 'None')} (+{self.profile.get('relic_power', 0)} Power)" if curr_relic else "None equipped"
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Cursed Relics & Weapons Vault ({len(unlocked_relic_ids)} Unlocked)\n"
                f"> {active_str}\n"
                f"> Select a relic below to equip and boost all your fighters:"
            )
        )
        await edit_container_response(interaction, container, view=equip_view)


class ChestRevealedView(discord.ui.View):
    """View shown after opening a chest with a button to return to profile."""

    def __init__(
        self,
        cog: AnimeClash,
        user: discord.Member | discord.User,
        profile: dict[str, Any],
        heroes: list[dict[str, Any]],
    ) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.user = user
        self.profile = profile
        self.heroes = heroes

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

    @discord.ui.button(label="Return to Profile", style=discord.ButtonStyle.primary)
    async def return_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        container, discord_file, new_view = await self.cog.render_profile_container(self.user, self.profile)
        await edit_container_response(interaction, container, file=discord_file, view=new_view)


class EquipBannerView(discord.ui.View):
    """Dropdown menu allowing players to equip any unlocked background banner."""

    def __init__(
        self,
        cog: AnimeClash,
        user: discord.Member | discord.User,
        profile: dict[str, Any],
        heroes: list[dict[str, Any]],
    ) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.user = user
        self.profile = profile
        self.heroes = heroes

        raw_unlocked = profile.get("banners_unlocked") or "shadow_realm"
        unlocked_keys = [b.strip() for b in raw_unlocked.split(",") if b.strip()]
        if "shadow_realm" not in unlocked_keys:
            unlocked_keys.insert(0, "shadow_realm")

        current_active = profile.get("banner") or profile.get("theme", "shadow_realm")

        options = []
        for key in unlocked_keys:
            if key in HUNTER_BANNERS:
                b_info = HUNTER_BANNERS[key]
                options.append(
                    discord.SelectOption(
                        label=b_info["name"],
                        value=key,
                        description=f"{b_info['anime']} • {b_info['rarity']} ({b_info['desc'][:30]})",
                        default=(key == current_active),
                    )
                )

        if not options:
            options.append(
                discord.SelectOption(label="Monarch's Abyss", value="shadow_realm", default=True)
            )

        select = discord.ui.Select(placeholder="Choose Hunter Profile Banner...", options=options[:25])
        select.callback = self.select_callback
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

    async def select_callback(self, interaction: discord.Interaction) -> None:
        chosen_banner = interaction.data["values"][0]
        await self.cog.bot.db.execute(
            "UPDATE game_anime_profiles SET banner = $1, theme = $1 WHERE user_id = $2;",
            chosen_banner,
            interaction.user.id,
        )
        self.profile["banner"] = chosen_banner
        self.profile["theme"] = chosen_banner

        container, discord_file, new_view = await self.cog.render_profile_container(self.user, self.profile)
        await edit_container_response(interaction, container, file=discord_file, view=new_view)

    @discord.ui.button(label="Back to Profile", style=discord.ButtonStyle.secondary)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        container, discord_file, new_view = await self.cog.render_profile_container(self.user, self.profile)
        await edit_container_response(interaction, container, file=discord_file, view=new_view)


class EquipRelicView(discord.ui.View):
    """Dropdown menu allowing players to equip any unlocked cursed weapon or relic."""

    def __init__(
        self,
        cog: AnimeClash,
        user: discord.Member | discord.User,
        profile: dict[str, Any],
        heroes: list[dict[str, Any]],
    ) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.user = user
        self.profile = profile
        self.heroes = heroes

        raw_unlocked = profile.get("relics_unlocked") or ""
        unlocked_keys = [r.strip() for r in raw_relics.split(",") if r.strip()]
        current_relic = profile.get("relic_id")

        options = []
        for key in unlocked_keys:
            if key in RELIC_REGISTRY:
                r_info = RELIC_REGISTRY[key]
                options.append(
                    discord.SelectOption(
                        label=f"{r_info['name']} (+{r_info['power']} Power)",
                        value=key,
                        description=f"{r_info['anime']} • {r_info['rarity']} [{r_info.get('effect', '')[:25]}]",
                        default=(key == current_relic),
                    )
                )

        if options:
            select = discord.ui.Select(placeholder="Choose Relic to equip...", options=options[:25])
            select.callback = self.select_callback
            self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

    async def select_callback(self, interaction: discord.Interaction) -> None:
        chosen_relic_id = interaction.data["values"][0]
        relic_data = RELIC_REGISTRY.get(chosen_relic_id, {})
        power = relic_data.get("power", 0)

        await self.cog.bot.db.execute(
            "UPDATE game_anime_profiles SET relic_id = $1, relic_power = $2 WHERE user_id = $3;",
            chosen_relic_id,
            power,
            interaction.user.id,
        )
        self.profile["relic_id"] = chosen_relic_id
        self.profile["relic_power"] = power

        container, discord_file, new_view = await self.cog.render_profile_container(self.user, self.profile)
        await edit_container_response(interaction, container, file=discord_file, view=new_view)

    @discord.ui.button(label="Back to Profile", style=discord.ButtonStyle.secondary)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        container, discord_file, new_view = await self.cog.render_profile_container(self.user, self.profile)
        await edit_container_response(interaction, container, file=discord_file, view=new_view)


class EquipRosterView(discord.ui.View):
    """Dropdown menu allowing players to equip any unlocked fighter."""

    def __init__(
        self,
        cog: AnimeClash,
        user: discord.Member | discord.User,
        profile: dict[str, Any],
        heroes: list[dict[str, Any]],
    ) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.user = user
        self.profile = profile
        self.heroes = heroes

        options = []
        for h in heroes[:25]:
            p = h["power"] + h.get("power_bonus", 0)
            options.append(
                discord.SelectOption(
                    label=f"{h['name']} ({p} Power)",
                    value=h["id"],
                    description=f"{h.get('anime', 'Anime')} • {h['rarity']} [{h['element']}]",
                )
            )

        select = discord.ui.Select(placeholder="Choose champion to equip...", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

    async def select_callback(self, interaction: discord.Interaction) -> None:
        chosen_id = interaction.data["values"][0]
        await self.cog.bot.db.execute(
            "UPDATE game_anime_profiles SET equipped_hero_id = $1 WHERE user_id = $2;",
            chosen_id,
            interaction.user.id,
        )
        self.profile["equipped_hero_id"] = chosen_id

        container, discord_file, new_view = await self.cog.render_profile_container(self.user, self.profile)
        await edit_container_response(interaction, container, file=discord_file, view=new_view)

    @discord.ui.button(label="Back to Profile", style=discord.ButtonStyle.secondary)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        container, discord_file, new_view = await self.cog.render_profile_container(self.user, self.profile)
        await edit_container_response(interaction, container, file=discord_file, view=new_view)


# ==========================================
# TURN-BASED INTERACTIVE COMBAT VIEW
# ==========================================

class SoloBattleSessionView(discord.ui.View):
    """
    Real-time interactive turn-based anime battle session with live HP bars and signature moves.
    """

    def __init__(
        self,
        cog: AnimeClash,
        ctx: CustomContext,
        player: discord.Member,
        my_hero: dict[str, Any],
        rival_hero: dict[str, Any],
        profile: dict[str, Any],
    ) -> None:
        super().__init__(timeout=120)
        self.cog = cog
        self.ctx = ctx
        self.player = player
        self.my_hero = my_hero
        self.rival_hero = rival_hero
        self.profile = profile

        self.p1_max_hp = 100
        self.p1_hp = 100
        self.p2_max_hp = 100
        self.p2_hp = 100
        self.p1_energy = 0
        self.p2_energy = 0
        self.domain_active: str | None = None
        self.round_num = 1
        self.battle_concluded = False

        e1 = my_hero.get("element", "Physical")
        e2 = rival_hero.get("element", "Physical")
        self.p1_adv = ELEMENT_ADVANTAGE.get(e1) == e2
        self.p2_adv = ELEMENT_ADVANTAGE.get(e2) == e1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("This is not your duel.", ephemeral=True)
            return False
        return True

    async def _execute_turn(self, interaction: discord.Interaction, action_type: str) -> None:
        if self.battle_concluded:
            return

        p1_id = self.my_hero.get("id", "tanjiro")
        rival_id = self.rival_hero.get("id", "sukuna")
        p1_lines = CHAMPION_BATTLE_LINES.get(p1_id, {})
        rival_lines = CHAMPION_BATTLE_LINES.get(rival_id, {})

        # Critical Strike Roll (18% for player, 12% for rival)
        p1_crit = random.random() < 0.18
        rival_crit = random.random() < 0.12

        # 1. Action Resolution
        if action_type == "ultimate":
            if self.p1_energy < 100:
                await interaction.response.send_message(
                    f"⚠️ Cursed Energy at {self.p1_energy}%! Charge it to 100% using Attack, Technique, or Parries to unleash Domain Expansion.",
                    ephemeral=True,
                )
                return

            self.p1_energy = 0
            ult_info = CHAMPION_ULTIMATES.get(
                p1_id,
                {
                    "name": "Domain Expansion",
                    "domain": "Cursed Domain",
                    "quote": "Domain Expansion!",
                    "dmg_mult": 2.5,
                },
            )
            self.domain_active = ult_info["domain"]
            base_p1 = random.randint(55, 72) + (14 if self.p1_adv else 0)
            p1_dmg = int(base_p1 * ult_info.get("dmg_mult", 2.5))
            rival_dmg = random.randint(6, 12)
            turn_narrative = f"Round {self.round_num}: 🌌 DOMAIN EXPANSION! {ult_info['name'][:22]} strikes for {p1_dmg} DMG!"
            turn_narrative_full = (
                f"🌌 **DOMAIN EXPANSION: {ult_info['domain'].upper()}!**\n"
                f'*"{ult_info["quote"]}"*\n'
                f"> **💥 {self.my_hero['name']}** unleashed **{ult_info['name']}** dealing **{p1_dmg} CRITICAL DMG**!\n"
                f"> **{self.rival_hero['name']}** was paralyzed within the domain and countered for only `{rival_dmg} DMG`."
            )

        elif action_type == "attack":
            self.p1_energy = min(100, self.p1_energy + 25)
            self.p2_energy = min(100, self.p2_energy + random.choice([20, 25]))
            base_p1 = random.randint(22, 28) + (7 if self.p1_adv else 0)
            p1_dmg = int(base_p1 * 1.45) if p1_crit else base_p1

            base_rival = random.randint(16, 24) + (5 if self.p2_adv else 0)
            rival_dmg = int(base_rival * 1.35) if rival_crit else base_rival

            # Dynamic Anime Combat Events
            roll = random.random()
            if roll < 0.16:
                p1_dmg = int(p1_dmg * 1.6)
                turn_narrative = f"Round {self.round_num}: 💥 BLACK FLASH! {self.my_hero['name']} lands spatial hit for {p1_dmg} DMG!"
                turn_narrative_full = (
                    f"> 💥 **BLACK FLASH!** Space distorts with black cursed lightning as **{self.my_hero['name']}** strikes for **{p1_dmg} DMG**!\n"
                    f"> **{self.rival_hero['name']}** countered for **{rival_dmg} DMG**."
                )
            elif roll < 0.28:
                rival_dmg = 0
                turn_narrative = f"Round {self.round_num}: ⚡ FLASH STEP! {self.my_hero['name']} dealt {p1_dmg} DMG & dodged counter!"
                turn_narrative_full = (
                    f"> ⚡ **FLASH STEP!** **{self.my_hero['name']}** landed **{p1_dmg} DMG** and vanished in an afterimage, taking `0 DMG` from counter!"
                )
            elif roll < 0.40:
                turn_narrative = f"Round {self.round_num}: ⚔️ WEAPON CLASH! Both fighters locked blades! {p1_dmg} vs {rival_dmg}."
                turn_narrative_full = (
                    f"> ⚔️ **WEAPON CLASH!** Sparks flew as both attacks collided! **{self.my_hero['name']}** broke through for **{p1_dmg} DMG**! (Took `{rival_dmg} DMG`)."
                )
            else:
                cry = p1_lines.get("crit" if p1_crit else "cry", "Take this!")
                crit_flag = "💥 CRITICAL! " if p1_crit else ""
                turn_narrative = f"Round {self.round_num}: {crit_flag}{self.my_hero['name']} deals {p1_dmg} DMG! Rival hits for {rival_dmg}."
                turn_narrative_full = (
                    f'*"{cry}"*\n'
                    f"> **{crit_flag}{self.my_hero['name']}** landed a strike dealing **{p1_dmg} DMG**!\n"
                    f"> **{self.rival_hero['name']}** struck back with **{rival_dmg} DMG**."
                )

        elif action_type == "technique":
            self.p1_energy = min(100, self.p1_energy + 35)
            self.p2_energy = min(100, self.p2_energy + random.choice([20, 25]))
            base_p1 = random.randint(34, 46) + (9 if self.p1_adv else 0)
            p1_dmg = int(base_p1 * 1.4) if p1_crit else base_p1

            base_rival = random.randint(20, 32) + (5 if self.p2_adv else 0)
            rival_dmg = int(base_rival * 1.3) if rival_crit else base_rival

            move_name = self.my_hero.get("move", "Signature Hit")
            cry = p1_lines.get("crit" if p1_crit else "cry", f"{move_name}!")
            crit_flag = "💥 CRITICAL! " if p1_crit else ""
            turn_narrative = f"Round {self.round_num}: {crit_flag}{self.my_hero['name']} used {move_name[:20]} for {p1_dmg} DMG!"
            turn_narrative_full = (
                f'*"{cry}"*\n'
                f"> **{crit_flag}{self.my_hero['name']}** unleashed **{move_name}** for **{p1_dmg} DMG**!\n"
                f"> **{self.rival_hero['name']}** absorbed the shock and countered for **{rival_dmg} DMG**."
            )

        elif action_type == "potion":
            if self.profile.get("healing_potions", 0) <= 0:
                await interaction.response.send_message("You have no Healing Potions left in your pouch!", ephemeral=True)
                return
            await self.cog.bot.db.execute(
                "UPDATE game_anime_profiles SET healing_potions = healing_potions - 1 WHERE user_id = $1;",
                self.player.id,
            )
            self.profile["healing_potions"] -= 1
            heal_amt = 35
            self.p1_hp = min(self.p1_max_hp, self.p1_hp + heal_amt)
            p1_dmg = 0
            raw_rival = random.randint(10, 18)
            rival_dmg = raw_rival
            turn_narrative = f"Round {self.round_num}: 🧪 HEALED! Restored +{heal_amt} HP. Rival dealt {rival_dmg}."
            turn_narrative_full = (
                f"> 🧪 **COMBAT ELIXIR!** **{self.my_hero['name']}** consumed a Healing Potion and recovered **+{heal_amt} HP**! (Took `{rival_dmg} DMG` while drinking)."
            )
        else:  # guard
            self.p1_energy = min(100, self.p1_energy + 20)
            self.p2_energy = min(100, self.p2_energy + 15)
            p1_dmg = random.randint(15, 22)
            raw_rival = random.randint(18, 26) + (4 if self.p2_adv else 0)
            rival_dmg = max(3, int(raw_rival * 0.25))

            turn_narrative = f"Round {self.round_num}: 🛡️ PARRY! {self.my_hero['name']} blocked 75% DMG & dealt {p1_dmg}."
            turn_narrative_full = (
                f"> 🛡️ **PERFECT PARRY!** **{self.my_hero['name']}** blocked 75% damage and counter-attacked for **{p1_dmg} DMG**! (Took only `{rival_dmg} DMG`)."
            )

        # Check Rival Ultimate Awakening
        if self.p2_energy >= 100 and (self.p2_hp - p1_dmg) > 0 and action_type != "ultimate":
            self.p2_energy = 0
            rival_ult = CHAMPION_ULTIMATES.get(rival_id, {})
            if rival_ult:
                rival_dmg = int(rival_dmg * 1.5)
                turn_narrative_full += f"\n> ⚠️ **RIVAL AWAKENED!** **{self.rival_hero['name']}** countered with **{rival_ult['name']}**!"

        # 2. Update HP
        self.p2_hp = max(0, self.p2_hp - p1_dmg)
        self.p1_hp = max(0, self.p1_hp - rival_dmg)
        self.round_num += 1

        # 3. Check Victory / Defeat
        winner_num = 0
        chest_dropped: str | None = None
        gold_win = 0
        xp_gain = 0

        if self.p2_hp <= 0 or self.p1_hp <= 0:
            self.battle_concluded = True
            self.stop()
            winner_num = 1 if self.p2_hp <= 0 else 2

            if winner_num == 1:
                gold_win = random.randint(65, 110)
                xp_gain = 35
                streak = self.profile.get("win_streak", 0) + 1

                roll = random.random()
                if streak >= 5 or roll < 0.06:
                    chest_dropped = "Monarch Divine Chest"
                    await self.cog.bot.db.execute(
                        "UPDATE game_anime_profiles SET chests_monarch = chests_monarch + 1 WHERE user_id = $1;",
                        self.player.id,
                    )
                elif streak >= 3 or roll < 0.22:
                    chest_dropped = "Shadow Epic Chest"
                    await self.cog.bot.db.execute(
                        "UPDATE game_anime_profiles SET chests_epic = chests_epic + 1 WHERE user_id = $1;",
                        self.player.id,
                    )
                elif roll < 0.50:
                    chest_dropped = "Silver Cursed Chest"
                    await self.cog.bot.db.execute(
                        "UPDATE game_anime_profiles SET chests_silver = chests_silver + 1 WHERE user_id = $1;",
                        self.player.id,
                    )
                elif roll < 0.85:
                    chest_dropped = "Bronze Battle Chest"
                    await self.cog.bot.db.execute(
                        "UPDATE game_anime_profiles SET chests_bronze = chests_bronze + 1 WHERE user_id = $1;",
                        self.player.id,
                    )

                await self.cog.bot.db.execute(
                    """
                    UPDATE game_anime_profiles
                    SET wins = wins + 1, win_streak = win_streak + 1, gold = gold + $1, xp = xp + $2
                    WHERE user_id = $3;
                    """,
                    gold_win,
                    xp_gain,
                    self.player.id,
                )
            else:
                xp_gain = 15
                await self.cog.bot.db.execute(
                    """
                    UPDATE game_anime_profiles
                    SET losses = losses + 1, win_streak = 0, xp = xp + $1
                    WHERE user_id = $2;
                    """,
                    xp_gain,
                    self.player.id,
                )

            # Check level up
            curr_lvl = self.profile.get("level", 1)
            curr_xp = self.profile.get("xp", 0) + xp_gain
            if curr_xp >= curr_lvl * 250:
                await self.cog.bot.db.execute(
                    "UPDATE game_anime_profiles SET level = level + 1, xp = 0 WHERE user_id = $1;",
                    self.player.id,
                )

        # 4. Render updated battle card
        card_buf = await asyncio.to_thread(
            render_battle_clash,
            player1_name=self.player.display_name,
            player1_hero=self.my_hero,
            p1_hp=self.p1_hp,
            p1_max_hp=self.p1_max_hp,
            player2_name="AI Rival",
            player2_hero=self.rival_hero,
            p2_hp=self.p2_hp,
            p2_max_hp=self.p2_max_hp,
            winner_num=winner_num,
            turn_action_text=turn_narrative,
            chest_reward=chest_dropped,
            gold_reward=gold_win,
            p1_energy=self.p1_energy,
            p2_energy=self.p2_energy,
            domain_active=self.domain_active,
        )

        discord_file = discord.File(card_buf, filename="battle_clash.png")
        container = KyroContainer(accent_color=None)
        container.add_media("attachment://battle_clash.png")

        if winner_num == 1:
            win_quote = p1_lines.get("cry", "Victory is ours!")
            title_text = (
                f"### 🏆 VICTORY OVER RIVAL!\n"
                f'*"{win_quote}"*\n'
                f"> **{self.my_hero['name']}** (« {self.my_hero.get('anime', 'Anime')} ») defeated **{self.rival_hero['name']}**!\n"
                f"> **Spoils of War:** `+{gold_win} Gold` | `+{xp_gain} XP`\n"
            )
            if chest_dropped:
                title_text += f"> **Vault Drop:** `{chest_dropped}` stored in your vault."
            container.add_section(content=title_text)
            self.clear_items()
            self.add_item(BattleAgainButton(self.cog, self.ctx))
        elif winner_num == 2:
            rival_quote = rival_lines.get("cry", "You are not ready for this arena.")
            title_text = (
                f"### 💀 DEFEATED BY RIVAL!\n"
                f'*"{rival_quote}"*\n'
                f"> **{self.rival_hero['name']}** (« {self.rival_hero.get('anime', 'Anime')} ») overpowered your fighter!\n"
                f"> **Consolation:** `+{xp_gain} XP` gained from experience."
            )
            container.add_section(content=title_text)
            self.clear_items()
            self.add_item(BattleAgainButton(self.cog, self.ctx))
        else:
            adv_str = " | ⚡ **Element Advantage!**" if self.p1_adv else ""
            container.add_section(
                content=(
                    f"### Combat In Progress — Round {self.round_num - 1}{adv_str}\n"
                    f"{turn_narrative_full}\n"
                    f"> **{self.my_hero['name']}:** `{self.p1_hp}/{self.p1_max_hp} HP` vs **{self.rival_hero['name']}:** `{self.p2_hp}/{self.p2_max_hp} HP`"
                )
            )

            # Update Domain Button label and style based on Cursed Energy
            if self.p1_energy >= 100:
                self.ultimate_btn.label = "🔥 UNLEASH DOMAIN (100% Ready!)"
                self.ultimate_btn.style = discord.ButtonStyle.danger
            else:
                self.ultimate_btn.label = f"🔥 Domain [CE: {self.p1_energy}%]"
                self.ultimate_btn.style = discord.ButtonStyle.secondary

        await edit_container_response(interaction, container, file=discord_file, view=self)

    @discord.ui.button(label="Attack", style=discord.ButtonStyle.primary, row=0)
    async def attack_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._execute_turn(interaction, "attack")

    @discord.ui.button(label="Technique", style=discord.ButtonStyle.success, row=0)
    async def technique_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._execute_turn(interaction, "technique")

    @discord.ui.button(label="Guard & Counter", style=discord.ButtonStyle.secondary, row=0)
    async def guard_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._execute_turn(interaction, "guard")

    @discord.ui.button(label="🔥 Domain [CE: 0%]", style=discord.ButtonStyle.secondary, row=1)
    async def ultimate_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._execute_turn(interaction, "ultimate")

    @discord.ui.button(label="Use Potion (+35 HP)", style=discord.ButtonStyle.secondary, row=1)
    async def potion_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._execute_turn(interaction, "potion")


class BattleAgainButton(discord.ui.Button):
    """Button to start another battle instantly."""

    def __init__(self, cog: AnimeClash, ctx: CustomContext) -> None:
        super().__init__(label="Battle Again", style=discord.ButtonStyle.primary)
        self.cog = cog
        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the player can battle again.", ephemeral=True)
            return
        await interaction.response.defer()
        await self.ctx.invoke(self.cog.battle_cmd)


class PvPInviteView(discord.ui.View):
    """Challenge Invite Handler for 1v1 PvP."""

    def __init__(
        self,
        cog: AnimeClash,
        ctx: CustomContext,
        challenger: discord.Member,
        opponent: discord.Member,
        p1_heroes: list[dict[str, Any]],
        p2_heroes: list[dict[str, Any]],
    ) -> None:
        super().__init__(timeout=45)
        self.cog = cog
        self.ctx = ctx
        self.challenger = challenger
        self.opponent = opponent
        self.p1_heroes = p1_heroes
        self.p2_heroes = p2_heroes

    @discord.ui.button(label="Accept Battle", style=discord.ButtonStyle.success)
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Only the challenged user can accept this duel.", ephemeral=True)
            return

        self.stop()
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Duel Accepted!\n"
                f"> **{self.challenger.mention}** vs **{self.opponent.mention}**\n"
                f"> Both fighters, click the button below to lock in your champion."
            )
        )
        lock_view = PvPLockFightersView(self.cog, self.ctx, self.challenger, self.opponent, self.p1_heroes, self.p2_heroes)
        await edit_container_response(interaction, container, view=lock_view)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Only the challenged user can decline.", ephemeral=True)
            return

        self.stop()
        container = KyroContainer(accent_color=None)
        container.add_section(content=f"> **{self.opponent.display_name} declined the duel challenge.**")
        await edit_container_response(interaction, container)


class PvPLockFightersView(discord.ui.View):
    """Fighter Selection for both PvP Combatants."""

    def __init__(
        self,
        cog: AnimeClash,
        ctx: CustomContext,
        p1: discord.Member,
        p2: discord.Member,
        p1_heroes: list[dict[str, Any]],
        p2_heroes: list[dict[str, Any]],
    ) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.p1 = p1
        self.p2 = p2
        self.p1_heroes = p1_heroes
        self.p2_heroes = p2_heroes
        self.p1_choice: dict[str, Any] | None = None
        self.p2_choice: dict[str, Any] | None = None

    @discord.ui.button(label="Lock Champion", style=discord.ButtonStyle.primary)
    async def lock_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        uid = interaction.user.id
        if uid not in (self.p1.id, self.p2.id):
            await interaction.response.send_message("You are not part of this duel.", ephemeral=True)
            return

        heroes = self.p1_heroes if uid == self.p1.id else self.p2_heroes
        options = []
        for h in heroes[:5]:
            p = h["power"] + h.get("power_bonus", 0)
            options.append(
                discord.SelectOption(
                    label=f"{h['name']} ({p} Power)",
                    value=h["id"],
                    description=f"{h.get('anime', 'Anime')} [{h['element']}]",
                )
            )

        view = discord.ui.View(timeout=30)
        select = discord.ui.Select(placeholder="Select your champion...", options=options)

        async def sel_callback(sel_inter: discord.Interaction):
            val = sel_inter.data["values"][0]
            chosen = HERO_REGISTRY[val].copy()
            for h in heroes:
                if h["id"] == val:
                    chosen["power_bonus"] = h.get("power_bonus", 0)
                    chosen["stars"] = h.get("stars", 1)

            if uid == self.p1.id:
                self.p1_choice = chosen
            else:
                self.p2_choice = chosen

            await sel_inter.response.send_message(f"Champion locked in.", ephemeral=True)

            if self.p1_choice and self.p2_choice:
                self.stop()
                await self.resolve_pvp()

        select.callback = sel_callback
        view.add_item(select)
        await interaction.response.send_message("Select your champion:", view=view, ephemeral=True)

    async def resolve_pvp(self) -> None:
        h1 = self.p1_choice or self.p1_heroes[0]
        h2 = self.p2_choice or self.p2_heroes[0]

        e1 = h1.get("element", "Shadow")
        e2 = h2.get("element", "Shadow")
        p1_adv = ELEMENT_ADVANTAGE.get(e1) == e2
        p2_adv = ELEMENT_ADVANTAGE.get(e2) == e1

        p1_power = (h1["power"] + h1.get("power_bonus", 0)) * (1.08 if p1_adv else 1.0) * random.uniform(0.96, 1.04)
        p2_power = (h2["power"] + h2.get("power_bonus", 0)) * (1.08 if p2_adv else 1.0) * random.uniform(0.96, 1.04)

        winner = 1 if p1_power > p2_power else 2
        gold_win = random.randint(70, 140)

        win_user = self.p1 if winner == 1 else self.p2
        lose_user = self.p2 if winner == 1 else self.p1

        await self.cog.bot.db.execute(
            """
            UPDATE game_anime_profiles
            SET wins = wins + 1, win_streak = win_streak + 1, gold = gold + $1, chests_silver = chests_silver + 1
            WHERE user_id = $2;
            """,
            gold_win,
            win_user.id,
        )
        await self.cog.bot.db.execute(
            "UPDATE game_anime_profiles SET losses = losses + 1, win_streak = 0 WHERE user_id = $1;",
            lose_user.id,
        )

        card_buf = await asyncio.to_thread(
            render_battle_clash,
            player1_name=self.p1.display_name,
            player1_hero=h1,
            p1_hp=100 if winner == 1 else 0,
            p1_max_hp=100,
            player2_name=self.p2.display_name,
            player2_hero=h2,
            p2_hp=100 if winner == 2 else 0,
            p2_max_hp=100,
            winner_num=winner,
            turn_action_text=f"DUEL RESOLVED: {win_user.display_name} landed the final hit!",
            chest_reward="Silver Cursed Chest",
            gold_reward=gold_win,
        )

        file = discord.File(card_buf, filename="pvp_clash.png")
        container = KyroContainer(accent_color=None)
        container.add_media("attachment://pvp_clash.png")
        container.add_section(
            content=(
                f"### Duel Resolved!\n"
                f"> **{win_user.mention}** emerges victorious over **{lose_user.mention}**!\n"
                f"> **Rewards:** `+{gold_win} Gold` and `Silver Cursed Chest` awarded to {win_user.mention}."
            )
        )
        await send_container_response(self.ctx, container, file=file)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(AnimeClash(bot))
