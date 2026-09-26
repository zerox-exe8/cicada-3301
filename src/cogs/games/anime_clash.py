"""
Kyro Discord Bot - Anime Clash: Shadow Arena
Next-Gen Visual Anime Battle & Collection Engine.
Features:
- Pure Battle-Driven Chest Progression (No summon clutter)
- High-Resolution Canvas Visual Cards (Media Gallery integration in Components V2)
- Zero Unicode Emoji Spam (strictly adhering to Kyro's permanent rules)
- Direct In-Channel & In-Place UI Actions (Zero annoying ephemeral popups)
- Solo Dungeon / Rival Matchmaking & 1v1 PvP Duel Challenges
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
# CURATED ANIME HERO ROSTER (Master Data)
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

THEME_ORDER = ["shadow", "crimson", "cyber", "gold"]


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
        try:
            av_bytes = await user.display_avatar.with_format("png").with_size(256).read()
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
                f"> **Champion:** **{equipped_hero['name']}** (`{equipped_hero['power'] + equipped_hero.get('power_bonus', 0)} Power`)"
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
    # COMMAND: !battle (Solo AI or 1v1 PvP)
    # ==========================================
    @commands.command(name="battle", aliases=["fight", "clash", "duel"])
    @commands.cooldown(1, 3, commands.BucketType.user)
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

        # 2. SOLO INSTANT AI ENCOUNTER
        p1_main = await self.get_equipped_hero(p1_profile)
        p1_power = p1_main["power"] + p1_main.get("power_bonus", 0)

        # Fair Matchmaking: Pick rival from player's rank pool
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

        container = KyroContainer(accent_color=0x38BDF8)
        container.add_section(
            content=(
                f"### Rival Encountered: {rival_hero['name'].upper()}!\n"
                f"> **Rival Fighter:** **{rival_hero['name']}** • `{rival_hero['power']} Power` | [{rival_hero['element']}]\n"
                f"> **Your Champion:** **{p1_main['name']}** • `{p1_power} Power` | [{p1_main['element']}]\n"
                f"> Choose your combat stance below to strike!"
            )
        )

        view = SoloSelectFighterView(self, ctx, p1, p1_main, rival_hero, p1_profile)
        await send_container_response(ctx, container, view=view)


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
        """Instantly unbox the highest available chest and display the unboxing card in the channel."""
        b = self.profile.get("chests_bronze", 0)
        s = self.profile.get("chests_silver", 0)
        e = self.profile.get("chests_epic", 0)
        m = self.profile.get("chests_monarch", 0)

        # Pick the highest available chest tier
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
                f"> **Fighter:** **{hero['name']}** (`{hero['rarity'].upper()}`)\n"
                f"> **Status:** {'Duplicate Power Up (+50 Power)!' if is_dup else 'Brand New Fighter Added!'}\n"
                f"> **Bonus:** `+{gold_reward} Gold` added to treasury."
            )
        )
        await send_container_response(interaction, container, file=file)

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

        # Re-render updated container
        container, discord_file, new_view = await self.cog.render_profile_container(self.user, self.profile)
        await interaction.response.defer()
        if interaction.message:
            await interaction.message.delete()
        await send_container_response(interaction.channel, container, file=discord_file, view=new_view)

    @discord.ui.button(label="Roster", style=discord.ButtonStyle.secondary)
    async def my_heroes_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Display list of unlocked anime fighters cleanly in channel."""
        if not self.heroes:
            await interaction.response.send_message("No heroes unlocked yet!", ephemeral=True)
            return

        lines = []
        for h in self.heroes[:12]:
            p = h["power"] + h.get("power_bonus", 0)
            lines.append(f"• **{h['name']}** ({h['rarity']}) — `{p} Power` | [{h['element']}]")

        resp = "\n".join(lines)
        container = KyroContainer(accent_color=0x9333EA)
        container.add_section(
            content=(
                f"### Unlocked Anime Fighters ({len(self.heroes)} Total)\n"
                f"{resp}\n\n"
                f"-# Win rare chests in `?battle` to unlock Epic & Mythic champions."
            )
        )
        await send_container_response(interaction, container, ephemeral=True)


class SoloSelectFighterView(discord.ui.View):
    """Let player select their combat stance to strike."""

    def __init__(
        self,
        cog: AnimeClash,
        ctx: CustomContext,
        player: discord.Member,
        my_hero: dict[str, Any],
        rival_hero: dict[str, Any],
        profile: dict[str, Any],
    ) -> None:
        super().__init__(timeout=45)
        self.cog = cog
        self.ctx = ctx
        self.player = player
        self.my_hero = my_hero
        self.rival_hero = rival_hero
        self.profile = profile

        btn_strike = discord.ui.Button(label="Balanced Strike", style=discord.ButtonStyle.primary)
        btn_slash = discord.ui.Button(label="Fierce Critical Slash", style=discord.ButtonStyle.danger)
        btn_guard = discord.ui.Button(label="Counter Guard", style=discord.ButtonStyle.secondary)

        btn_strike.callback = self.make_callback("strike")
        btn_slash.callback = self.make_callback("slash")
        btn_guard.callback = self.make_callback("counter")

        self.add_item(btn_strike)
        self.add_item(btn_slash)
        self.add_item(btn_guard)

    def make_callback(self, stance: str):
        async def callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != self.player.id:
                await interaction.response.send_message("This is not your match.", ephemeral=True)
                return

            self.stop()
            await self.resolve_battle(interaction, self.my_hero, stance)

        return callback

    async def resolve_battle(self, interaction: discord.Interaction, hero1: dict[str, Any], stance: str) -> None:
        hero2 = self.rival_hero

        e1 = hero1.get("element", "Shadow")
        e2 = hero2.get("element", "Shadow")

        p1_adv = ELEMENT_ADVANTAGE.get(e1) == e2
        p2_adv = ELEMENT_ADVANTAGE.get(e2) == e1

        p1_base = hero1["power"] + hero1.get("power_bonus", 0)
        p2_base = hero2["power"] + hero2.get("power_bonus", 0)

        # Apply tactical stance calculation
        p1_roll = random.uniform(0.96, 1.04)
        if stance == "slash":
            p1_roll = random.uniform(0.85, 1.25)
        elif stance == "counter":
            p1_base += int(p2_base * 0.12)
            p1_roll = random.uniform(0.96, 1.02)

        p1_adv_mult = 1.10 if p1_adv else 1.0
        p2_adv_mult = 1.10 if p2_adv else 1.0

        p1_eff = p1_base * p1_adv_mult * p1_roll
        p2_eff = p2_base * p2_adv_mult * random.uniform(0.95, 1.05)

        winner = 1 if p1_eff >= p2_eff else 2

        gold_win = random.randint(50, 95)
        xp_gain = 35 if winner == 1 else 12
        chest_dropped: str | None = None

        if winner == 1:
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
            elif roll < 0.80:
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
            await self.cog.bot.db.execute(
                """
                UPDATE game_anime_profiles
                SET losses = losses + 1, win_streak = 0, xp = xp + $1
                WHERE user_id = $2;
                """,
                xp_gain,
                self.player.id,
            )

        curr_lvl = self.profile.get("level", 1)
        curr_xp = self.profile.get("xp", 0) + xp_gain
        if curr_xp >= curr_lvl * 250:
            await self.cog.bot.db.execute(
                "UPDATE game_anime_profiles SET level = level + 1, xp = 0 WHERE user_id = $1;",
                self.player.id,
            )

        # Render Battle Card with Media Gallery attachment
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
        container.add_media("attachment://battle_clash.png")

        elem_recap = "Neutral element matchup"
        if p1_adv:
            elem_recap = f"{e1} countered {e2}! (+10% Power Advantage)"
        elif p2_adv:
            elem_recap = f"{e2} countered {e1}! (-10% Disadvantage)"

        stance_desc = {
            "strike": "Balanced Strike",
            "slash": "Fierce Critical Slash",
            "counter": "Counter Guard Stance",
        }.get(stance, "Attack")

        if winner == 1:
            title_text = (
                f"### Victory Over Rival!\n"
                f"> **Your Champion:** **{hero1['name']}** • `{int(p1_eff)} Combat Score` [{e1}]\n"
                f"> **Rival Fighter:** **{hero2['name']}** • `{int(p2_eff)} Combat Score` [{e2}]\n"
                f"> **Element Synergy:** {elem_recap}\n"
                f"> **Tactical Action:** Executed *{stance_desc}* and shattered rival's defense!\n"
                f"> **Spoils of War:** `+{gold_win} Gold` | `+{xp_gain} XP`"
            )
        else:
            title_text = (
                f"### Defeated By Rival!\n"
                f"> **Your Champion:** **{hero1['name']}** • `{int(p1_eff)} Combat Score` [{e1}]\n"
                f"> **Rival Fighter:** **{hero2['name']}** • `{int(p2_eff)} Combat Score` [{e2}]\n"
                f"> **Element Synergy:** {elem_recap}\n"
                f"> **Combat Turn:** Rival countered with *{hero2.get('move', 'Special Strike')}* and landed the final hit.\n"
                f"> **Consolation:** `+{xp_gain} XP` gained from experience."
            )

        container.add_section(content=title_text)
        if chest_dropped:
            container.add_separator(divider=True)
            container.add_text(f"-# Reward: {chest_dropped} added to your vault. Use `?hunter` to open.")

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
        await send_container_response(interaction, container, view=lock_view)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Only the challenged user can decline.", ephemeral=True)
            return

        self.stop()
        await interaction.response.send_message(f"**{self.opponent.display_name} declined the duel challenge.**")


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
            options.append(discord.SelectOption(label=f"{h['name']} ({p})", value=h["id"], description=f"Element: {h['element']}"))

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
