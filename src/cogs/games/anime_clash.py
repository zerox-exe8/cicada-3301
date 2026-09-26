"""
Kyro Discord Bot - Anime Clash: Shadow Arena
Next-Gen Visual Anime Battle & Collection Engine.
Features:
- Pure Battle-Driven Chest Progression (No summon clutter!)
- High-Resolution Canvas Visual Cards (Profile, Clash Arena, Chest Reveal)
- Solo Dungeon / Rival Matchmaking & 1v1 PvP Duel Challenges
- Modular Profile Embeds with Theme Customization, Hero Equipping, and Vault Openers
"""

from __future__ import annotations

import asyncio
import io
import random
from typing import Any, TYPE_CHECKING

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    KyroContainer,
    send_container_response,
    edit_container_response,
)
from src.utils.anime_canvas import (
    render_hunter_profile,
    render_battle_clash,
    render_chest_open_card,
    THEMES,
    RARITY_COLORS,
    ELEMENT_DATA,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot


# ==========================================
# 🎴 CURATED ANIME HERO ROSTER (Master Data)
# ==========================================
HERO_REGISTRY: dict[str, dict[str, Any]] = {
    # --- COMMON HEROES (Base: 460 - 520) ---
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
    "kiba": {
        "id": "kiba",
        "name": "Kiba Inuzuka",
        "anime": "Naruto",
        "rarity": "Common",
        "element": "Wind",
        "power": 460,
        "stars": 1,
        "move": "Fang Over Fang",
    },
    "raditz": {
        "id": "raditz",
        "name": "Raditz",
        "anime": "Dragon Ball Z",
        "rarity": "Common",
        "element": "Lightning",
        "power": 480,
        "stars": 1,
        "move": "Double Sunday Blast",
    },
    "rocklee": {
        "id": "rocklee",
        "name": "Rock Lee",
        "anime": "Naruto",
        "rarity": "Common",
        "element": "Physical",
        "power": 520,
        "stars": 1,
        "move": "Primary Lotus Gate",
    },

    # --- RARE HEROES (Base: 600 - 680) ---
    "zenitsu": {
        "id": "zenitsu",
        "name": "Zenitsu Agatsuma",
        "anime": "Demon Slayer",
        "rarity": "Rare",
        "element": "Lightning",
        "power": 620,
        "stars": 2,
        "move": "Thunderclap & Flash: Sixfold",
    },
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
        "move": "Blood Manipulation: Piercing",
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
        "move": "Tsukuyomi & Black Flames",
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
        "move": "Malevolent Shrine: Cleave & Dismantle",
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

# Elemental Advantage Matrix
# Key beats Value (+8% combat power)
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


class AnimeClash(commands.Cog):
    """Next-Gen Visual Anime Clash & Shadow Arena."""

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
            # Fallback to Tanjiro
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

    # ==========================================
    # 🪪 COMMAND: !hunter / !hp
    # ==========================================
    @commands.command(name="hunter", aliases=["hp", "hunterprofile", "shadowprofile"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def hunter_cmd(self, ctx: CustomContext, target: discord.Member | None = None) -> None:
        """Display high-resolution Hunter License Profile Card and Vault."""
        user = target or ctx.author
        profile = await self.get_or_create_profile(user.id)
        equipped_hero = await self.get_equipped_hero(profile)
        user_heroes = await self.get_user_heroes(user.id)

        # Avatar Bytes
        av_bytes: bytes | None = None
        try:
            av_bytes = await user.display_avatar.with_format("png").with_size(256).read()
        except Exception:
            pass

        # Calculate XP progression
        lvl = profile.get("level", 1)
        xp = profile.get("xp", 0)
        xp_needed = lvl * 250
        rank = self.compute_rank(profile.get("wins", 0))

        # Total chests
        chests_total = (
            profile.get("chests_bronze", 0)
            + profile.get("chests_silver", 0)
            + profile.get("chests_epic", 0)
            + profile.get("chests_monarch", 0)
        )

        # Render high-resolution visual card in background thread
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

        # Container / Embed Interface
        container = KyroContainer(accent_color=THEMES.get(theme, THEMES["shadow"])["accent"][0])
        container.add_section(
            content=(
                f"### 🪪 Hunter License — {user.mention}\n"
                f"> **Rank:** `{rank}` | **Level:** `{lvl}` | **Streak:** `🔥 {profile.get('win_streak', 0)}`\n"
                f"> **Equipped Champion:** **{equipped_hero['name']}** (`⚡ {equipped_hero['power'] + equipped_hero.get('power_bonus', 0)} Power`)"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"• **Treasury:** `🪙 {profile.get('gold', 150):,} Gold`\n"
            f"• **Chests In Vault:** `🪵 {profile.get('chests_bronze', 0)}` Bronze | `🔷 {profile.get('chests_silver', 0)}` Silver | `🔮 {profile.get('chests_epic', 0)}` Epic | `👑 {profile.get('chests_monarch', 0)}` Monarch\n"
            f"• **Unlocked Heroes:** `{len(user_heroes)} / {len(HERO_REGISTRY)} Fighters`"
        )

        view = ProfileHubView(self, ctx, user.id, profile, user_heroes)
        await send_container_response(ctx, container, file=discord_file, view=view)

    # ==========================================
    # ⚔️ COMMAND: !battle (Solo AI or 1v1 PvP)
    # ==========================================
    @commands.command(name="battle", aliases=["fight", "clash", "duel"])
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def battle_cmd(self, ctx: CustomContext, opponent: discord.Member | None = None) -> None:
        """
        Jump into Anime Clash Arena!
        - Alone: `!battle` matches you with a wild anime rival instantly.
        - With friend: `!battle @user` issues a 1v1 challenge.
        """
        p1 = ctx.author
        p1_profile = await self.get_or_create_profile(p1.id)
        p1_heroes = await self.get_user_heroes(p1.id)

        if not p1_heroes:
            p1_heroes = [HERO_REGISTRY["tanjiro"].copy()]

        # ----------------------------------------
        # 1. 1v1 PVP DUEL CHALLENGE
        # ----------------------------------------
        if opponent and opponent.id != p1.id:
            if opponent.bot:
                await ctx.error("You cannot challenge bots to a duel! Use `!battle` to fight AI rivals.")
                return

            p2_profile = await self.get_or_create_profile(opponent.id)
            p2_heroes = await self.get_user_heroes(opponent.id)

            container = KyroContainer(accent_color=0xA855F7)
            container.add_section(
                content=(
                    f"### ⚔️ ANIME DUEL CHALLENGE!\n"
                    f"> **{p1.mention}** has challenged **{opponent.mention}** to a Shadow Arena duel!\n\n"
                    f"> ⏱️ *Opponent has 45 seconds to accept.*"
                )
            )
            view = PvPInviteView(self, ctx, p1, opponent, p1_heroes, p2_heroes)
            await send_container_response(ctx, container, view=view)
            return

        # ----------------------------------------
        # 2. SOLO INSTANT AI ENCOUNTER
        # ----------------------------------------
        # Scale rival close to player's power level
        p1_main = await self.get_equipped_hero(p1_profile)
        p1_power = p1_main["power"] + p1_main.get("power_bonus", 0)

        # Pick random rival hero
        candidate_ids = list(HERO_REGISTRY.keys())
        rival_id = random.choice(candidate_ids)
        rival_hero = HERO_REGISTRY[rival_id].copy()

        # Scale rival power within +/- 15%
        scale = random.uniform(0.90, 1.12)
        rival_hero["power"] = int(rival_hero["power"] * scale)
        rival_hero["power_bonus"] = 0

        # Ask player to confirm fighter or pick from their top 3 heroes
        top_heroes = sorted(p1_heroes, key=lambda h: h["power"] + h.get("power_bonus", 0), reverse=True)[:3]

        container = KyroContainer(accent_color=0x38BDF8)
        container.add_section(
            content=(
                f"### ⚔️ RIVAL ENCOUNTERED: {rival_hero['name'].upper()}!\n"
                f"> **Rival Element:** `{rival_hero['element']}` | **Estimated Power:** `⚡ {rival_hero['power']}`\n"
                f"> Select your fighter below to strike!"
            )
        )

        view = SoloSelectFighterView(self, ctx, p1, top_heroes, rival_hero, p1_profile)
        await send_container_response(ctx, container, view=view)


# ==========================================
# 🎮 INTERACTIVE VIEWS & DIALOGS
# ==========================================

class ProfileHubView(discord.ui.View):
    """Modular Action Bar for Player Profile."""

    def __init__(
        self,
        cog: AnimeClash,
        ctx: CustomContext,
        target_id: int,
        profile: dict[str, Any],
        heroes: list[dict[str, Any]],
    ) -> None:
        super().__init__(timeout=90)
        self.cog = cog
        self.ctx = ctx
        self.target_id = target_id
        self.profile = profile
        self.heroes = heroes

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_id:
            await interaction.response.send_message("❌ This is not your profile hub!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Open Chests", style=discord.ButtonStyle.primary, emoji="📦")
    async def open_chests_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Open chest selector dialog."""
        b = self.profile.get("chests_bronze", 0)
        s = self.profile.get("chests_silver", 0)
        e = self.profile.get("chests_epic", 0)
        m = self.profile.get("chests_monarch", 0)

        total = b + s + e + m
        if total <= 0:
            await interaction.response.send_message(
                "❌ You have no Battle Chests in your vault! Win battles with `!battle` to earn chests.",
                ephemeral=True,
            )
            return

        chest_options = []
        if b > 0:
            chest_options.append(discord.SelectOption(label=f"Bronze Chest ({b} available)", value="bronze", emoji="🪵"))
        if s > 0:
            chest_options.append(discord.SelectOption(label=f"Silver Chest ({s} available)", value="silver", emoji="🔷"))
        if e > 0:
            chest_options.append(discord.SelectOption(label=f"Shadow Epic Chest ({e} available)", value="epic", emoji="🔮"))
        if m > 0:
            chest_options.append(discord.SelectOption(label=f"Monarch Divine Chest ({m} available)", value="monarch", emoji="👑"))

        view = ChestSelectView(self.cog, self.ctx, self.profile, chest_options)
        await interaction.response.send_message("📦 **Select a Battle Chest to unbox:**", view=view, ephemeral=True)

    @discord.ui.button(label="My Heroes", style=discord.ButtonStyle.secondary, emoji="🃏")
    async def my_heroes_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Display list of unlocked anime fighters."""
        if not self.heroes:
            await interaction.response.send_message("No heroes unlocked yet!", ephemeral=True)
            return

        lines = []
        for h in self.heroes[:15]:
            p = h["power"] + h.get("power_bonus", 0)
            lines.append(f"• **{h['name']}** ({h['rarity']}) — `⚡ {p} Power` | [{h['element']}]")

        resp = "\n".join(lines)
        container = KyroContainer(accent_color=0x9333EA)
        container.add_section(
            content=(
                f"### 🃏 Unlocked Anime Fighters ({len(self.heroes)} Total)\n"
                f"{resp}\n\n"
                f"-# Win rare chests in `!battle` to unlock Epic & Mythic champions!"
            )
        )
        await send_container_response(interaction, container, ephemeral=True)

    @discord.ui.button(label="Customize", style=discord.ButtonStyle.secondary, emoji="🎨")
    async def customize_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Open theme / display customizer."""
        view = CustomizeView(self.cog, self.ctx, self.profile, self.heroes)
        await interaction.response.send_message("🎨 **Profile Customization Studio:**", view=view, ephemeral=True)


class ChestSelectView(discord.ui.View):
    """Dropdown selector to open battle chests."""

    def __init__(self, cog: AnimeClash, ctx: CustomContext, profile: dict[str, Any], options: list[discord.SelectOption]) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.profile = profile

        select = discord.ui.Select(placeholder="Choose a chest to open...", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction) -> None:
        val = interaction.data["values"][0]  # bronze, silver, epic, monarch
        col_name = f"chests_{val}"
        current_count = self.profile.get(col_name, 0)
        if current_count <= 0:
            await interaction.response.send_message("❌ You don't have this chest anymore!", ephemeral=True)
            return

        # Deduct chest
        await self.cog.bot.db.execute(
            f"UPDATE game_anime_profiles SET {col_name} = {col_name} - 1 WHERE user_id = $1;",
            interaction.user.id,
        )

        # Roll loot based on chest rarity
        loot_pool: list[str] = []
        gold_reward = 100
        chest_display_name = "Bronze Chest"

        if val == "bronze":
            chest_display_name = "Bronze Battle Chest"
            gold_reward = random.randint(50, 120)
            # 70% Common, 30% Rare
            loot_pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Common", "Rare"]]
        elif val == "silver":
            chest_display_name = "Silver Cursed Chest"
            gold_reward = random.randint(150, 280)
            # 60% Rare, 40% Epic
            loot_pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Rare", "Epic"]]
        elif val == "epic":
            chest_display_name = "Shadow Epic Chest"
            gold_reward = random.randint(300, 600)
            # 60% Epic, 40% Legendary
            loot_pool = [k for k, v in HERO_REGISTRY.items() if v["rarity"] in ["Epic", "Legendary"]]
        elif val == "monarch":
            chest_display_name = "Monarch Divine Chest"
            gold_reward = random.randint(800, 1500)
            # 60% Legendary, 40% Mythic
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
            # Upgrade power bonus by +50
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

        # Award Gold
        await self.cog.bot.db.execute(
            "UPDATE game_anime_profiles SET gold = gold + $1 WHERE user_id = $2;",
            gold_reward,
            interaction.user.id,
        )

        # Render Unboxing Graphic Card in thread
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
        container.add_section(
            content=(
                f"### 🎉 {chest_display_name.upper()} UNBOXED!\n"
                f"> **Fighter:** **{hero['name']}** (`✦ {hero['rarity'].upper()}`)\n"
                f"> **Status:** {'⭐ Duplicate Power Up (+50 Power)!' if is_dup else '✨ Brand New Fighter Added!'}\n"
                f"> **Bonus:** `+{gold_reward} Gold` added to treasury."
            )
        )
        await send_container_response(interaction, container, file=file)


class CustomizeView(discord.ui.View):
    """Interactive Hub to Equip Main Fighter or Change Profile Theme."""

    def __init__(self, cog: AnimeClash, ctx: CustomContext, profile: dict[str, Any], heroes: list[dict[str, Any]]) -> None:
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.profile = profile

        # Theme Dropdown
        theme_options = [
            discord.SelectOption(label="Shadow Realm (Neon Violet)", value="theme:shadow", emoji="🟣"),
            discord.SelectOption(label="Blood Moon (Crimson Red)", value="theme:crimson", emoji="🔴"),
            discord.SelectOption(label="Neon Cyber (Cyan Electric)", value="theme:cyber", emoji="🔷"),
            discord.SelectOption(label="Monarch Sun (Imperial Gold)", value="theme:gold", emoji="🟡"),
        ]
        theme_sel = discord.ui.Select(placeholder="Change Card Theme...", options=theme_options)
        theme_sel.callback = self.theme_callback
        self.add_item(theme_sel)

        # Hero Equip Dropdown (Top 10)
        hero_options = []
        for h in heroes[:12]:
            hero_options.append(
                discord.SelectOption(
                    label=f"{h['name']} ({h['rarity']})",
                    value=f"equip:{h['id']}",
                    description=f"Power: {h['power'] + h.get('power_bonus', 0)} | {h['element']}",
                )
            )

        if hero_options:
            hero_sel = discord.ui.Select(placeholder="Equip Main Champion...", options=hero_options)
            hero_sel.callback = self.equip_callback
            self.add_item(hero_sel)

    async def theme_callback(self, interaction: discord.Interaction) -> None:
        raw_val = interaction.data["values"][0].replace("theme:", "")
        await self.cog.bot.db.execute(
            "UPDATE game_anime_profiles SET theme = $1 WHERE user_id = $2;",
            raw_val,
            interaction.user.id,
        )
        await interaction.response.send_message(
            f"✅ **Theme Updated to `{THEMES[raw_val]['name']}`!** Type `!hunter` to see the new look.",
            ephemeral=True,
        )

    async def equip_callback(self, interaction: discord.Interaction) -> None:
        raw_val = interaction.data["values"][0].replace("equip:", "")
        await self.cog.bot.db.execute(
            "UPDATE game_anime_profiles SET equipped_hero_id = $1 WHERE user_id = $2;",
            raw_val,
            interaction.user.id,
        )
        hero_name = HERO_REGISTRY.get(raw_val, {}).get("name", "Hero")
        await interaction.response.send_message(
            f"✅ **Equipped {hero_name} as your Main Champion!**",
            ephemeral=True,
        )


class SoloSelectFighterView(discord.ui.View):
    """Let player select their champion for the solo AI battle."""

    def __init__(
        self,
        cog: AnimeClash,
        ctx: CustomContext,
        player: discord.Member,
        heroes: list[dict[str, Any]],
        rival_hero: dict[str, Any],
        profile: dict[str, Any],
    ) -> None:
        super().__init__(timeout=45)
        self.cog = cog
        self.ctx = ctx
        self.player = player
        self.heroes = heroes
        self.rival_hero = rival_hero
        self.profile = profile

        for i, h in enumerate(heroes[:3]):
            p = h["power"] + h.get("power_bonus", 0)
            btn = discord.ui.Button(
                label=f"{h['name']} ({p})",
                style=discord.ButtonStyle.primary if i == 0 else discord.ButtonStyle.secondary,
                custom_id=f"solo_hero_{h['id']}",
            )
            btn.callback = self.make_callback(h)
            self.add_item(btn)

    def make_callback(self, chosen_hero: dict[str, Any]):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != self.player.id:
                await interaction.response.send_message("❌ This is not your match!", ephemeral=True)
                return

            self.stop()
            # Calculate battle
            await self.resolve_battle(interaction, chosen_hero)

        return callback

    async def resolve_battle(self, interaction: discord.Interaction, hero1: dict[str, Any]) -> None:
        hero2 = self.rival_hero

        # Check Elemental Advantages
        e1 = hero1.get("element", "Shadow")
        e2 = hero2.get("element", "Shadow")

        p1_adv = ELEMENT_ADVANTAGE.get(e1) == e2
        p2_adv = ELEMENT_ADVANTAGE.get(e2) == e1

        p1_power = hero1["power"] + hero1.get("power_bonus", 0)
        p2_power = hero2["power"] + hero2.get("power_bonus", 0)

        p1_eff = p1_power * (1.08 if p1_adv else 1.0) * random.uniform(0.96, 1.04)
        p2_eff = p2_power * (1.08 if p2_adv else 1.0) * random.uniform(0.96, 1.04)

        winner = 1 if p1_eff > p2_eff else 2

        # Rewards calculation
        gold_win = random.randint(45, 90)
        xp_gain = 35 if winner == 1 else 10
        chest_dropped: str | None = None

        if winner == 1:
            # Streak
            streak = self.profile.get("win_streak", 0) + 1
            # Chest roll (65% chance on win)
            roll = random.random()
            if streak >= 5 or roll < 0.05:
                chest_dropped = "Monarch Divine Chest"
                await self.cog.bot.db.execute(
                    "UPDATE game_anime_profiles SET chests_monarch = chests_monarch + 1 WHERE user_id = $1;",
                    self.player.id,
                )
            elif streak >= 3 or roll < 0.20:
                chest_dropped = "Shadow Epic Chest"
                await self.cog.bot.db.execute(
                    "UPDATE game_anime_profiles SET chests_epic = chests_epic + 1 WHERE user_id = $1;",
                    self.player.id,
                )
            elif roll < 0.45:
                chest_dropped = "Silver Cursed Chest"
                await self.cog.bot.db.execute(
                    "UPDATE game_anime_profiles SET chests_silver = chests_silver + 1 WHERE user_id = $1;",
                    self.player.id,
                )
            elif roll < 0.75:
                chest_dropped = "Bronze Battle Chest"
                await self.cog.bot.db.execute(
                    "UPDATE game_anime_profiles SET chests_bronze = chests_bronze + 1 WHERE user_id = $1;",
                    self.player.id,
                )

            # Update DB Win
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
            # Loss
            await self.cog.bot.db.execute(
                """
                UPDATE game_anime_profiles
                SET losses = losses + 1, win_streak = 0, xp = xp + $1
                WHERE user_id = $2;
                """,
                xp_gain,
                self.player.id,
            )

        # Check Level Up
        curr_lvl = self.profile.get("level", 1)
        curr_xp = self.profile.get("xp", 0) + xp_gain
        if curr_xp >= curr_lvl * 250:
            await self.cog.bot.db.execute(
                "UPDATE game_anime_profiles SET level = level + 1, xp = 0 WHERE user_id = $1;",
                self.player.id,
            )

        # Render Battle Card
        card_buf = await asyncio.to_thread(
            render_battle_clash,
            player1_name=self.player.display_name,
            player1_hero=hero1,
            player2_name=hero2["name"],
            player2_hero=hero2,
            winner_num=winner,
            p1_advantage=p1_adv,
            p2_advantage=p2_adv,
            chest_reward=chest_dropped,
            gold_reward=gold_win,
        )

        file = discord.File(card_buf, filename="battle_clash.png")
        container = KyroContainer(accent_color=0x22C55E if winner == 1 else 0xEF4444)
        if winner == 1:
            title_text = f"### 🏆 VICTORY OVER RIVAL!\n> **{self.player.mention}** defeated **{hero2['name']}**!"
        else:
            title_text = f"### 💀 DEFEATED BY RIVAL!\n> **{hero2['name']}** overpowered **{self.player.mention}**!"

        container.add_section(content=title_text)
        if chest_dropped:
            container.add_separator(divider=True)
            container.add_text(f"-# 🎁 Bonus Reward: {chest_dropped} added to your vault! Use `!hunter` to open it.")

        await send_container_response(interaction, container, file=file)


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
        self.p1_choice: dict[str, Any] | None = None
        self.p2_choice: dict[str, Any] | None = None

    @discord.ui.button(label="Accept Battle", style=discord.ButtonStyle.success, emoji="⚔️")
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("❌ Only the challenged user can accept this duel!", ephemeral=True)
            return

        self.stop()
        button.disabled = True

        # Open selection prompt for both
        container = KyroContainer(accent_color=0x22C55E)
        container.add_section(
            content=(
                f"### ⚔️ DUEL ACCEPTED!\n"
                f"> **{self.challenger.mention}** vs **{self.opponent.mention}**\n"
                f"> Both fighters, click the button below to secretly lock in your champion!"
            )
        )
        lock_view = PvPLockFightersView(self.cog, self.ctx, self.challenger, self.opponent, self.p1_heroes, self.p2_heroes)
        await send_container_response(interaction, container, view=lock_view)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("❌ Only the challenged user can decline!", ephemeral=True)
            return

        self.stop()
        await interaction.response.send_message(f"🏳️ **{self.opponent.display_name} declined the duel challenge.**")


class PvPLockFightersView(discord.ui.View):
    """Secret Fighter Selection for both PvP Combatants."""

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

    @discord.ui.button(label="Lock My Champion", style=discord.ButtonStyle.primary, emoji="🔒")
    async def lock_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        uid = interaction.user.id
        if uid not in (self.p1.id, self.p2.id):
            await interaction.response.send_message("❌ You are not part of this duel!", ephemeral=True)
            return

        heroes = self.p1_heroes if uid == self.p1.id else self.p2_heroes
        options = []
        for h in heroes[:5]:
            p = h["power"] + h.get("power_bonus", 0)
            options.append(discord.SelectOption(label=f"{h['name']} ({p})", value=h["id"], description=f"Element: {h['element']}"))

        view = discord.ui.View(timeout=30)
        select = discord.ui.Select(placeholder="Select your champion...", options=options)

        async def sel_callback(sel_inter: discord.Interaction):
            val = sel_inter.data["values"][0]
            chosen = HERO_REGISTRY[val].copy()
            # Find power bonus
            for h in heroes:
                if h["id"] == val:
                    chosen["power_bonus"] = h.get("power_bonus", 0)
                    chosen["stars"] = h.get("stars", 1)

            if uid == self.p1.id:
                self.p1_choice = chosen
            else:
                self.p2_choice = chosen

            await sel_inter.response.send_message(f"🔒 **{chosen['name']} locked in secretly!**", ephemeral=True)

            if self.p1_choice and self.p2_choice:
                self.stop()
                await self.resolve_pvp()

        select.callback = sel_callback
        view.add_item(select)
        await interaction.response.send_message("Select your champion secretly:", view=view, ephemeral=True)

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

        # Award winner
        await self.cog.bot.db.execute(
            """
            UPDATE game_anime_profiles
            SET wins = wins + 1, win_streak = win_streak + 1, gold = gold + $1, chests_silver = chests_silver + 1
            WHERE user_id = $2;
            """,
            gold_win,
            win_user.id,
        )
        # Update loser
        await self.cog.bot.db.execute(
            "UPDATE game_anime_profiles SET losses = losses + 1, win_streak = 0 WHERE user_id = $1;",
            lose_user.id,
        )

        card_buf = await asyncio.to_thread(
            render_battle_clash,
            player1_name=self.p1.display_name,
            player1_hero=h1,
            player2_name=self.p2.display_name,
            player2_hero=h2,
            winner_num=winner,
            p1_advantage=p1_adv,
            p2_advantage=p2_adv,
            chest_reward="Silver Cursed Chest",
            gold_reward=gold_win,
        )

        file = discord.File(card_buf, filename="pvp_clash.png")
        container = KyroContainer(accent_color=0x22C55E)
        container.add_section(
            content=(
                f"### 🏆 DUEL RESOLVED!\n"
                f"> **{win_user.mention}** emerges victorious over **{lose_user.mention}**!\n"
                f"> **Rewards:** `+{gold_win} Gold` and `🔷 Silver Cursed Chest` awarded to {win_user.mention}."
            )
        )
        await send_container_response(self.ctx, container, file=file)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(AnimeClash(bot))
