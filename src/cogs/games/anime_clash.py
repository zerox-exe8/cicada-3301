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

THEME_ORDER = ["shadow", "crimson", "cyber", "gold"]


class AnimeClash(commands.Cog):
    """Visual Anime Clash & Shadow Arena Game Cog."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot: KyroBot = bot
        self._schema_initialized = False

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
        user_id = profile["user_id"]
        equipped_id = profile.get("equipped_hero_id") or "tanjiro"

        row = await self.bot.db.fetch_one(
            "SELECT * FROM game_anime_inventory WHERE user_id = $1 AND hero_id = $2;",
            user_id,
            equipped_id,
        )
        if not row or equipped_id not in HERO_REGISTRY:
            base = HERO_REGISTRY["tanjiro"].copy()
            base["stars"] = 1
            base["power_bonus"] = 0
            return base

        base = HERO_REGISTRY[equipped_id].copy()
        base["stars"] = row["stars"]
        base["power_bonus"] = row["power_bonus"]
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

        theme = profile.get("theme", "shadow")
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
            theme_key=theme,
        )

        discord_file = discord.File(img_buffer, filename="hunter_profile.png")

        # Container / Embed Interface with Media Gallery attachment
        container = KyroContainer(accent_color=THEMES.get(theme, THEMES["shadow"])["accent"][0])
        container.add_media("attachment://hunter_profile.png")
        container.add_section(
            content=(
                f"### Hunter License — {user.mention}\n"
                f"> **Rank:** `{rank}` | **Level:** `{lvl}` | **Streak:** `{profile.get('win_streak', 0)}`\n"
                f"> **Champion:** **{equipped_hero['name']}** (« {equipped_hero.get('anime', 'Anime')} ») • `{equipped_hero['power'] + equipped_hero.get('power_bonus', 0)} Power`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"• **Treasury:** `{profile.get('gold', 150):,} Gold`\n"
            f"• **Vault:** `{profile.get('chests_bronze', 0)}` Bronze | `{profile.get('chests_silver', 0)}` Silver | `{profile.get('chests_epic', 0)}` Epic | `{profile.get('chests_monarch', 0)}` Monarch\n"
            f"• **Roster:** `{len(user_heroes)} / {len(HERO_REGISTRY)} Fighters Unlocked`"
        )

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
                await ctx.error("You cannot challenge bots to a duel! Use `!battle` to fight AI rivals.")
                return

            p2_profile = await self.get_or_create_profile(opponent.id)
            p2_heroes = await self.get_user_heroes(opponent.id)

            container = KyroContainer(accent_color=0xA855F7)
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

        # Matchmaking from rank pool
        rank = p1_profile.get("hunter_rank", "E-Rank")
        if rank in ["E-Rank", "D-Rank"]:
            pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Common", "Rare"]]
        elif rank in ["C-Rank", "B-Rank"]:
            pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Rare", "Epic"]]
        else:
            pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Epic", "Legendary", "Mythic"]]

        if not pool:
            pool = list(HERO_REGISTRY.keys())

        rival_id = random.choice(pool)
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
        )
        discord_file = discord.File(card_buf, filename="battle_clash.png")

        container = KyroContainer(accent_color=0x38BDF8)
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
        """Instantly unbox the highest available chest and update message in-place with unboxing card."""
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

        # Determine loot pool and rewards
        if target_tier == "bronze":
            chest_display_name = "Bronze Battle Chest"
            gold_reward = random.randint(50, 120)
            loot_pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Common", "Rare"]]
        elif target_tier == "silver":
            chest_display_name = "Silver Cursed Chest"
            gold_reward = random.randint(150, 280)
            loot_pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Rare", "Epic"]]
        elif target_tier == "epic":
            chest_display_name = "Shadow Epic Chest"
            gold_reward = random.randint(300, 600)
            loot_pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Epic", "Legendary"]]
        else:  # monarch
            chest_display_name = "Monarch Divine Chest"
            gold_reward = random.randint(800, 1500)
            loot_pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Legendary", "Mythic"]]

        if not loot_pool:
            loot_pool = list(HERO_REGISTRY.keys())

        chosen_id = random.choice(loot_pool)
        hero = HERO_REGISTRY[chosen_id].copy()

        # Check duplicate
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

        # Render unboxing card with full Media Gallery attachment
        card_buf = await asyncio.to_thread(
            render_chest_open_card,
            user_name=interaction.user.display_name,
            chest_type=chest_display_name,
            unlocked_hero=hero,
            is_duplicate=is_dup,
            gold_reward=gold_reward,
        )

        file = discord.File(card_buf, filename="chest_reveal.png")
        container = KyroContainer(accent_color=0xEAB308 if is_dup else 0x22C55E)
        container.add_media("attachment://chest_reveal.png")
        container.add_section(
            content=(
                f"### {chest_display_name.upper()} UNBOXED!\n"
                f"> **Champion:** **{hero['name']}** (« {hero.get('anime', 'Anime')} ») • `{hero['rarity'].upper()}`\n"
                f"> **Status:** {'Duplicate Power Up (+50 Power)!' if is_dup else 'Brand New Champion Added!'}\n"
                f"> **Spoils:** `+{gold_reward} Gold` added to treasury."
            )
        )

        reveal_view = ChestRevealedView(self.cog, self.user, self.profile, self.heroes)
        await edit_container_response(interaction, container, file=file, view=reveal_view)

    @discord.ui.button(label="Switch Theme", style=discord.ButtonStyle.secondary)
    async def switch_theme_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Cycle card theme instantly in-place without any popup."""
        curr_theme = self.profile.get("theme", "shadow")
        curr_idx = THEME_ORDER.index(curr_theme) if curr_theme in THEME_ORDER else 0
        next_theme = THEME_ORDER[(curr_idx + 1) % len(THEME_ORDER)]

        await self.cog.bot.db.execute(
            "UPDATE game_anime_profiles SET theme = $1 WHERE user_id = $2;",
            next_theme,
            interaction.user.id,
        )
        self.profile["theme"] = next_theme

        # Re-render updated container and edit in-place
        container, discord_file, new_view = await self.cog.render_profile_container(self.user, self.profile)
        await edit_container_response(interaction, container, file=discord_file, view=new_view)

    @discord.ui.button(label="Roster & Equip", style=discord.ButtonStyle.secondary)
    async def my_heroes_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Display select menu to equip any unlocked anime fighter in-place."""
        if not self.heroes:
            await interaction.response.send_message("No champions unlocked yet!", ephemeral=True)
            return

        equip_view = EquipRosterView(self.cog, self.user, self.profile, self.heroes)
        container = KyroContainer(accent_color=0x9333EA)
        container.add_section(
            content=(
                f"### Hunter Champion Roster ({len(self.heroes)} Unlocked)\n"
                f"> Select a champion from the dropdown below to equip as your main fighter:"
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
        self.round_num = 1
        self.is_finished = False

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
        if self.is_finished:
            return

        # 1. Calculate Player and Rival Damage
        if action_type == "attack":
            p1_dmg = random.randint(22, 28) + (6 if self.p1_adv else 0)
            rival_dmg = random.randint(16, 24) + (5 if self.p2_adv else 0)
            turn_narrative = (
                f"Round {self.round_num}: {self.my_hero['name']} used Attack for {p1_dmg} DMG! "
                f"{self.rival_hero['name']} hit back for {rival_dmg} DMG."
            )
        elif action_type == "technique":
            p1_dmg = random.randint(34, 46) + (8 if self.p1_adv else 0)
            rival_dmg = random.randint(20, 32) + (5 if self.p2_adv else 0)
            move_name = self.my_hero.get("move", "Signature Hit")
            turn_narrative = (
                f"Round {self.round_num}: {self.my_hero['name']} unleashed {move_name[:26]} for {p1_dmg} DMG! "
                f"{self.rival_hero['name']} countered for {rival_dmg} DMG."
            )
        else:  # guard
            p1_dmg = random.randint(14, 20)
            # Guard blocks 75% of incoming damage
            raw_rival = random.randint(18, 26) + (4 if self.p2_adv else 0)
            rival_dmg = max(4, int(raw_rival * 0.25))
            turn_narrative = (
                f"Round {self.round_num}: {self.my_hero['name']} guarded, blocking 75% damage and counter-attacked for {p1_dmg} DMG!"
            )

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
            self.is_finished = True
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
        )

        discord_file = discord.File(card_buf, filename="battle_clash.png")
        container = KyroContainer(
            accent_color=0x22C55E if winner_num == 1 else (0xEF4444 if winner_num == 2 else 0x38BDF8)
        )
        container.add_media("attachment://battle_clash.png")

        if winner_num == 1:
            title_text = (
                f"### VICTORY OVER RIVAL!\n"
                f"> **{self.my_hero['name']}** (« {self.my_hero.get('anime', 'Anime')} ») defeated **{self.rival_hero['name']}**!\n"
                f"> **Spoils of War:** `+{gold_win} Gold` | `+{xp_gain} XP`\n"
            )
            if chest_reward:
                title_text += f"> **Vault Drop:** `{chest_reward}` stored in your vault."
            container.add_section(content=title_text)
            self.clear_items()
            self.add_item(BattleAgainButton(self.cog, self.ctx))
        elif winner_num == 2:
            title_text = (
                f"### DEFEATED BY RIVAL!\n"
                f"> **{self.rival_hero['name']}** (« {self.rival_hero.get('anime', 'Anime')} ») overpowered your fighter!\n"
                f"> **Consolation:** `+{xp_gain} XP` gained from experience."
            )
            container.add_section(content=title_text)
            self.clear_items()
            self.add_item(BattleAgainButton(self.cog, self.ctx))
        else:
            container.add_section(
                content=(
                    f"### Combat In Progress — Round {self.round_num - 1}\n"
                    f"> **{self.my_hero['name']}:** `{self.p1_hp}/{self.p1_max_hp} HP` | "
                    f"**{self.rival_hero['name']}:** `{self.p2_hp}/{self.p2_max_hp} HP`\n"
                    f"> {turn_narrative}"
                )
            )

        await edit_container_response(interaction, container, file=discord_file, view=self)

    @discord.ui.button(label="Attack", style=discord.ButtonStyle.primary)
    async def attack_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._execute_turn(interaction, "attack")

    @discord.ui.button(label="Technique", style=discord.ButtonStyle.success)
    async def technique_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._execute_turn(interaction, "technique")

    @discord.ui.button(label="Guard & Counter", style=discord.ButtonStyle.secondary)
    async def guard_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._execute_turn(interaction, "guard")


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
        await self.cog.battle_cmd(self.ctx)


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
        container = KyroContainer(accent_color=0x22C55E)
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
        container = KyroContainer(accent_color=0xEF4444)
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
        container = KyroContainer(accent_color=0x22C55E)
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
