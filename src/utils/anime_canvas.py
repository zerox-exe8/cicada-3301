"""
Kyro Discord Bot - Ultra High-Resolution Anime Canvas Graphics Pipeline
Generates aesthetic, crisp, dark-mode anime game cards:
1. Hunter Profile Cards (Stats, Equipped Hero with Real Artwork, Win-Rate, Theme Accents)
2. Battle Clash Arena Cards (Split Duel with Real Character Portraits, Live HP Bars, Element Advantage, Turn Feedback)
3. Chest Unboxing & Hero Reveal Cards (Glowing chest rays, Rarity Holo-Borders, Hero Artwork)
"""

from __future__ import annotations

import io
import math
import os
import random
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ASSETS_DIR = os.path.join(os.getcwd(), "assets", "anime")

# Hunter Profile Banners Registry (Equippable Custom Backdrops & Aesthetics)
HUNTER_BANNERS: dict[str, dict[str, Any]] = {
    "shadow_realm": {
        "id": "shadow_realm",
        "name": "Monarch's Abyss",
        "anime": "Solo Leveling",
        "rarity": "Common",
        "accent": (168, 85, 247),
        "accent_glow": (147, 51, 234, 70),
        "highlight": (216, 180, 254),
        "bg": (12, 10, 20, 255),
        "surface": (22, 18, 36, 255),
        "surface_card": (26, 21, 42, 255),
        "border": (58, 48, 85, 255),
        "desc": "Sovereign dark mist of the Shadow Monarch.",
    },
    "infinite_void": {
        "id": "infinite_void",
        "name": "Infinite Void",
        "anime": "Jujutsu Kaisen",
        "rarity": "Mythic",
        "accent": (6, 182, 212),
        "accent_glow": (14, 165, 233, 70),
        "highlight": (165, 243, 252),
        "bg": (6, 14, 26, 255),
        "surface": (14, 25, 45, 255),
        "surface_card": (18, 34, 60, 255),
        "border": (40, 68, 100, 255),
        "desc": "Cosmic domain where all perception converges.",
    },
    "malevolent_shrine": {
        "id": "malevolent_shrine",
        "name": "Malevolent Shrine",
        "anime": "Jujutsu Kaisen",
        "rarity": "Legendary",
        "accent": (239, 68, 68),
        "accent_glow": (220, 38, 38, 70),
        "highlight": (252, 165, 165),
        "bg": (20, 8, 12, 255),
        "surface": (34, 14, 22, 255),
        "surface_card": (44, 18, 28, 255),
        "border": (85, 40, 55, 255),
        "desc": "Cursed sanctuary surrounded by cleaving blades.",
    },
    "wano_sunset": {
        "id": "wano_sunset",
        "name": "Wano Blossoms",
        "anime": "One Piece",
        "rarity": "Epic",
        "accent": (244, 114, 182),
        "accent_glow": (236, 72, 153, 70),
        "highlight": (251, 207, 232),
        "bg": (22, 10, 18, 255),
        "surface": (36, 18, 30, 255),
        "surface_card": (48, 24, 40, 255),
        "border": (80, 45, 70, 255),
        "desc": "Cherry blossoms under golden sunset twilight.",
    },
    "flame_purgatory": {
        "id": "flame_purgatory",
        "name": "Flame Purgatory",
        "anime": "Demon Slayer",
        "rarity": "Epic",
        "accent": (249, 115, 22),
        "accent_glow": (234, 88, 12, 70),
        "highlight": (254, 215, 170),
        "bg": (24, 12, 6, 255),
        "surface": (38, 20, 10, 255),
        "surface_card": (52, 28, 14, 255),
        "border": (85, 60, 30, 255),
        "desc": "Blazing inferno of fiery determination.",
    },
    "godspeed_storm": {
        "id": "godspeed_storm",
        "name": "Godspeed Thunder",
        "anime": "Hunter x Hunter",
        "rarity": "Rare",
        "accent": (234, 179, 8),
        "accent_glow": (202, 138, 4, 70),
        "highlight": (253, 224, 71),
        "bg": (18, 16, 6, 255),
        "surface": (30, 26, 12, 255),
        "surface_card": (42, 36, 18, 255),
        "border": (85, 75, 40, 255),
        "desc": "Electric storm crackling with lightning aura.",
    },
    "akatsuki_eclipse": {
        "id": "akatsuki_eclipse",
        "name": "Crimson Eclipse",
        "anime": "Naruto",
        "rarity": "Rare",
        "accent": (220, 38, 38),
        "accent_glow": (185, 28, 28, 70),
        "highlight": (254, 202, 202),
        "bg": (20, 9, 14, 255),
        "surface": (34, 15, 24, 255),
        "surface_card": (42, 19, 30, 255),
        "border": (85, 40, 55, 255),
        "desc": "Blood moon eclipse with crimson cloud sigils.",
    },
}

# Theme Color Palettes (Aliased for backwards compatibility)
THEMES: dict[str, dict[str, Any]] = {
    "shadow": HUNTER_BANNERS["shadow_realm"],
    "crimson": HUNTER_BANNERS["malevolent_shrine"],
    "cyber": HUNTER_BANNERS["infinite_void"],
    "gold": HUNTER_BANNERS["godspeed_storm"],
    **HUNTER_BANNERS,
}

# Rarity Color Specs
RARITY_COLORS: dict[str, tuple[int, int, int]] = {
    "Common": (156, 163, 175),       # Slate Silver
    "Rare": (56, 189, 248),          # Ice Blue
    "Epic": (168, 85, 247),          # Mystic Purple
    "Legendary": (234, 179, 8),       # Radiant Gold
    "Mythic": (244, 63, 94),          # Cosmic Crimson
}

# Element Icons & Accent
ELEMENT_DATA: dict[str, dict[str, Any]] = {
    "Fire": {"symbol": "FLAME", "color": (239, 68, 68)},
    "Water": {"symbol": "WATER", "color": (59, 130, 246)},
    "Lightning": {"symbol": "THUNDER", "color": (234, 179, 8)},
    "Wind": {"symbol": "GALE", "color": (34, 197, 94)},
    "Shadow": {"symbol": "VOID", "color": (168, 85, 247)},
    "Physical": {"symbol": "FORCE", "color": (249, 115, 22)},
}


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Load system font with graceful fallback."""
    font_names = (
        ["arialbd.ttf", "segoeuib.ttf", "impact.ttf", "arial.ttf"]
        if bold
        else ["arial.ttf", "segoeui.ttf", "calibri.ttf"]
    )
    for name in font_names:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _load_hero_image(hero_id: str, target_size: tuple[int, int], corner_radius: int = 12) -> Image.Image:
    """Load hero artwork asset, crop to target aspect ratio and apply rounded corner mask."""
    tw, th = target_size
    img = None
    for ext in [".jpg", ".png", ".jpeg"]:
        fp = os.path.join(ASSETS_DIR, f"{hero_id}{ext}")
        if os.path.exists(fp):
            try:
                raw = Image.open(fp).convert("RGBA")
                iw, ih = raw.size
                scale = max(tw / iw, th / ih)
                nw, nh = int(iw * scale), int(ih * scale)
                raw = raw.resize((nw, nh), Image.Resampling.LANCZOS)

                left = (nw - tw) // 2
                top = max(0, (nh - th) // 4)
                if top + th > nh:
                    top = nh - th
                img = raw.crop((left, top, left + tw, top + th))
                break
            except Exception:
                pass

    if img is None:
        img = Image.new("RGBA", (tw, th), (32, 26, 48, 255))
        d = ImageDraw.Draw(img)
        d.text((tw // 2 - 30, th // 2 - 10), hero_id[:6].upper(), fill=(160, 150, 180, 255), font=_get_font(16, bold=True))

    mask = Image.new("L", (tw, th), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle([(0, 0), (tw, th)], radius=corner_radius, fill=255)

    rounded = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    rounded.paste(img, (0, 0), mask)
    return rounded


def render_hunter_profile(
    avatar_bytes: bytes | None,
    username: str,
    title: str,
    rank: str,
    level: int,
    xp: int,
    xp_needed: int,
    wins: int,
    losses: int,
    streak: int,
    gold: int,
    chests_count: int,
    hero_data: dict[str, Any],
    theme_key: str = "shadow",
) -> io.BytesIO:
    """
    Renders an authentic 900x390 Hunter License Card with the equipped character's high-res artwork.
    """
    w, h = 980, 480
    theme = THEMES.get(theme_key, THEMES["shadow"])
    accent = theme["accent"]

    im = Image.new("RGBA", (w, h), theme["bg"])

    # Ambient glows
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([(-60, -60), (380, 380)], fill=(accent[0], accent[1], accent[2], 45))
    gdraw.ellipse([(w - 420, 30), (w + 80, h + 80)], fill=(accent[0], accent[1], accent[2], 50))
    im = Image.alpha_composite(im, glow)
    draw = ImageDraw.Draw(im)

    # Frame outer & inner border
    draw.rounded_rectangle([(8, 8), (w - 8, h - 8)], radius=20, outline=(58, 48, 85, 255), width=2)
    draw.rounded_rectangle([(10, 10), (w - 10, h - 10)], radius=18, outline=accent, width=1)

    # Top accent line
    draw.rounded_rectangle([(24, 16), (w - 24, 20)], radius=2, fill=accent)

    # Player Avatar (110px High-DPI)
    av_size = 110
    av_x, av_y = 35, 35
    draw.ellipse([(av_x, av_y), (av_x + av_size, av_y + av_size)], fill=(28, 22, 40, 255))
    draw.ellipse([(av_x - 3, av_y - 3), (av_x + av_size + 3, av_y + av_size + 3)], outline=accent, width=3)

    pasted_avatar = False
    if avatar_bytes:
        try:
            av_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av_img = av_img.resize((av_size, av_size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (av_size, av_size), 0)
            ImageDraw.Draw(mask).ellipse([(0, 0), (av_size, av_size)], fill=255)
            im.paste(av_img, (av_x, av_y), mask)
            pasted_avatar = True
        except Exception:
            pass

    if not pasted_avatar:
        draw.text(
            (av_x + 36, av_y + 30),
            username[:1].upper(),
            fill=(255, 255, 255, 255),
            font=_get_font(44, bold=True),
        )

    user_x = av_x + av_size + 20
    draw.text((user_x, av_y + 4), username[:18], fill=(255, 255, 255, 255), font=_get_font(32, bold=True))
    draw.text((user_x, av_y + 42), f"[ {title[:28]} ]", fill=theme["highlight"], font=_get_font(17, bold=True))

    # Badges Row (Rank & Level)
    badge_y = av_y + 74
    rank_color = (234, 179, 8) if "S" in rank else ((168, 85, 247) if "A" in rank else (59, 130, 246))
    draw.rounded_rectangle(
        [(user_x, badge_y), (user_x + 160, badge_y + 32)],
        radius=8,
        fill=(28, 22, 42, 255),
        outline=rank_color,
        width=2,
    )
    draw.text((user_x + 18, badge_y + 6), f"{rank.upper()} HUNTER", fill=rank_color, font=_get_font(14, bold=True))

    lvl_x = user_x + 175
    draw.rounded_rectangle(
        [(lvl_x, badge_y), (lvl_x + 115, badge_y + 32)],
        radius=8,
        fill=(35, 30, 52, 255),
        outline=(100, 90, 135, 255),
        width=2,
    )
    draw.text((lvl_x + 18, badge_y + 6), f"LEVEL {level}", fill=(245, 245, 255, 255), font=_get_font(14, bold=True))

    # 2x2 Large Stats Grid (High readability on mobile screens)
    stats_y = 165
    total_battles = wins + losses
    win_rate = round((wins / total_battles * 100), 1) if total_battles > 0 else 0.0

    stat_cards = [
        (35, stats_y, "WIN RATE", f"{win_rate}%", f"{wins} Wins / {losses} Losses", (255, 255, 255)),
        (325, stats_y, "WIN STREAK", f"{streak} STREAK", "Active Unbroken Run", (250, 204, 21)),
        (35, stats_y + 92, "TREASURY", f"{gold:,} GOLD", "Hunter Coin Balance", (250, 204, 21)),
        (325, stats_y + 92, "VAULT STORAGE", f"{chests_count} CHESTS", "Ready To Unbox", (216, 180, 254)),
    ]

    card_w, card_h = 275, 80
    for cx, cy, lbl, val, sub, vc in stat_cards:
        draw.rounded_rectangle(
            [(cx, cy), (cx + card_w, cy + card_h)],
            radius=12,
            fill=theme["surface"],
            outline=(65, 52, 90, 255),
            width=1,
        )
        draw.text((cx + 16, cy + 10), lbl, fill=(170, 160, 195, 255), font=_get_font(13, bold=True))
        draw.text((cx + 16, cy + 28), val, fill=vc, font=_get_font(24, bold=True))
        draw.text((cx + 16, cy + 54), sub, fill=(135, 125, 155, 255), font=_get_font(12))

    # Hunter XP Progress Bar
    bar_w = 565
    pct = int((xp / xp_needed) * 100) if xp_needed > 0 else 100
    draw.text(
        (35, 360),
        f"HUNTER XP PROGRESSION • {xp} / {xp_needed} XP ({pct}%)",
        fill=(195, 185, 220, 255),
        font=_get_font(13, bold=True),
    )
    draw.rounded_rectangle([(35, 384), (35 + bar_w, 384 + 16)], radius=8, fill=(35, 30, 52, 255))
    progress = min(1.0, max(0.05, (xp / xp_needed) if xp_needed > 0 else 1.0))
    fill_w = int(bar_w * progress)
    draw.rounded_rectangle([(35, 384), (35 + fill_w, 384 + 16)], radius=8, fill=accent)

    # Footer Branding
    draw.text(
        (35, 430),
        "KYRO BATTLE ARENA • OFFICIAL HUNTER LICENSE",
        fill=(115, 105, 140, 255),
        font=_get_font(13, bold=True),
    )

    # --- RIGHT SHOWCASE: HERO CARD ---
    hero_card_x = 630
    hero_card_y = 25
    hero_card_w = 325
    hero_card_h = 430

    h_rarity = hero_data.get("rarity", "Common")
    h_color = RARITY_COLORS.get(h_rarity, (156, 163, 175))
    h_id = hero_data.get("id", "tanjiro")
    h_anime = hero_data.get("anime", "Anime Series")
    h_name = hero_data.get("name", "Tanjiro Kamado")
    h_elem = hero_data.get("element", "Water")
    elem_info = ELEMENT_DATA.get(h_elem, {"symbol": h_elem, "color": (168, 85, 247)})
    h_power = hero_data.get("power", 500) + hero_data.get("power_bonus", 0)
    h_move = hero_data.get("move", "Special Attack")

    # Card background & glowing rarity border
    draw.rounded_rectangle(
        [(hero_card_x, hero_card_y), (hero_card_x + hero_card_w, hero_card_y + hero_card_h)],
        radius=18,
        fill=theme["surface_card"],
        outline=h_color,
        width=2,
    )

    # Anime Series Title Header Box
    draw.rounded_rectangle(
        [(hero_card_x + 12, hero_card_y + 12), (hero_card_x + hero_card_w - 12, hero_card_y + 44)],
        radius=8,
        fill=(18, 14, 28, 255),
    )
    draw.text(
        (hero_card_x + 20, hero_card_y + 18),
        f"<< {h_anime.upper()} >>",
        fill=h_color,
        font=_get_font(13, bold=True),
    )
    draw.text(
        (hero_card_x + hero_card_w - 90, hero_card_y + 18),
        f"[{elem_info['symbol']}]",
        fill=elem_info["color"],
        font=_get_font(13, bold=True),
    )

    # Character Artwork
    art_w, art_h = 145, 185
    art_x, art_y = hero_card_x + 14, hero_card_y + 54
    draw.rounded_rectangle(
        [(art_x - 2, art_y - 2), (art_x + art_w + 2, art_y + art_h + 2)],
        radius=12,
        outline=h_color,
        width=2,
    )
    hero_art = _load_hero_image(h_id, (art_w, art_h), corner_radius=10)
    im.paste(hero_art, (art_x, art_y), hero_art)

    # Info to right of artwork
    info_x = art_x + art_w + 14
    info_y = art_y + 4
    name_parts = h_name.split()
    draw.text((info_x, info_y), name_parts[0], fill=(255, 255, 255, 255), font=_get_font(22, bold=True))
    if len(name_parts) > 1:
        draw.text(
            (info_x, info_y + 26),
            " ".join(name_parts[1:])[:14],
            fill=(215, 205, 235, 255),
            font=_get_font(16, bold=True),
        )

    # Rarity Pill
    draw.rounded_rectangle(
        [(info_x, info_y + 58), (info_x + 125, info_y + 86)],
        radius=6,
        fill=(18, 14, 28, 255),
        outline=h_color,
        width=1,
    )
    draw.text((info_x + 12, info_y + 63), h_rarity.upper(), fill=h_color, font=_get_font(13, bold=True))

    # Power Pill
    draw.rounded_rectangle(
        [(info_x, info_y + 96), (info_x + 135, info_y + 150)],
        radius=8,
        fill=(35, 26, 52, 255),
        outline=(90, 75, 125, 255),
        width=1,
    )
    draw.text((info_x + 10, info_y + 102), "COMBAT POWER", fill=(170, 160, 195, 255), font=_get_font(11, bold=True))
    draw.text((info_x + 10, info_y + 118), f"{h_power}", fill=(255, 255, 255, 255), font=_get_font(22, bold=True))

    # Signature Move Box below artwork
    move_y = art_y + art_h + 14
    draw.rounded_rectangle(
        [(hero_card_x + 14, move_y), (hero_card_x + hero_card_w - 14, move_y + 64)],
        radius=10,
        fill=(18, 14, 28, 255),
        outline=(60, 50, 85, 255),
        width=1,
    )
    draw.text(
        (hero_card_x + 24, move_y + 10),
        "SIGNATURE TECHNIQUE",
        fill=(160, 150, 185, 255),
        font=_get_font(12, bold=True),
    )
    draw.text(
        (hero_card_x + 24, move_y + 30),
        f"> {h_move[:30]}",
        fill=theme["highlight"],
        font=_get_font(15, bold=True),
    )

    # Card Footer Status
    draw.text(
        (hero_card_x + 60, move_y + 76),
        "EQUIPPED MAIN FIGHTER",
        fill=(160, 150, 185, 255),
        font=_get_font(13, bold=True),
    )

    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out


def render_battle_clash(
    player1_name: str,
    player1_hero: dict[str, Any],
    p1_hp: int,
    p1_max_hp: int,
    player2_name: str,
    player2_hero: dict[str, Any],
    p2_hp: int,
    p2_max_hp: int,
    winner_num: int = 0,  # 0: in progress / duel, 1: p1 won, 2: p2 won
    turn_action_text: str | None = None,
    chest_reward: str | None = None,
    gold_reward: int = 50,
    p1_energy: int = 0,
    p2_energy: int = 0,
    domain_active: str | None = None,
    p1_energy_name: str = "CURSED ENERGY",
    p2_energy_name: str = "CURSED ENERGY",
) -> io.BytesIO:
    """
    Renders a dramatic 940x440 Anime Clash Arena Card with both fighters' portraits,
    live HP bars, Universe-specific Energy meters, and Climax Awakening effects.
    """
    w, h = 940, 440
    im = Image.new("RGBA", (w, h), (12, 10, 22, 255))

    # Glows
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    if domain_active:
        gdraw.ellipse([(w // 4, -80), (3 * w // 4, 320)], fill=(244, 63, 94, 60))
    else:
        gdraw.ellipse([(-50, -50), (320, 320)], fill=(59, 130, 246, 45))  # Left Blue
        gdraw.ellipse([(w - 320, -50), (w + 50, 320)], fill=(239, 68, 68, 45))  # Right Red
    im = Image.alpha_composite(im, glow)
    draw = ImageDraw.Draw(im)

    # Frame
    outline_col = (244, 63, 94) if domain_active else (55, 45, 75, 255)
    draw.rounded_rectangle([(8, 8), (w - 8, h - 8)], radius=20, outline=outline_col, width=2)

    # Top arena header
    if domain_active:
        draw.rounded_rectangle([(24, 16), (w - 24, 20)], radius=2, fill=(244, 63, 94))
        domain_title = domain_active.upper()
        draw.text((w // 2 - 160, 26), domain_title[:45], fill=(255, 255, 255, 255), font=_get_font(13, bold=True))
    else:
        draw.rounded_rectangle([(24, 16), (w - 24, 20)], radius=2, fill=(168, 85, 247))
        draw.text((w // 2 - 90, 26), "SHADOW DUEL ARENA", fill=(216, 180, 254, 255), font=_get_font(13, bold=True))

    card_w, card_h = 390, 295

    # ------------------ LEFT FIGHTER (Player 1) ------------------
    p1_x, p1_y = 35, 58
    p1_rarity = player1_hero.get("rarity", "Common")
    p1_color = RARITY_COLORS.get(p1_rarity, (156, 163, 175))
    p1_outline = (234, 179, 8) if winner_num == 1 else (p1_color if winner_num == 0 else (60, 50, 80))

    draw.rounded_rectangle([(p1_x, p1_y), (p1_x + card_w, p1_y + card_h)], radius=16, fill=(22, 17, 36, 255), outline=p1_outline, width=3 if winner_num == 1 else 1)

    # Top banner in card
    draw.rounded_rectangle([(p1_x + 12, p1_y + 12), (p1_x + card_w - 12, p1_y + 36)], radius=6, fill=(16, 12, 26, 255))
    draw.text((p1_x + 20, p1_y + 15), f"« {player1_hero.get('anime', 'Anime').upper()} »", fill=p1_color, font=_get_font(11, bold=True))
    p1_elem = player1_hero.get("element", "Water")
    draw.text((p1_x + card_w - 95, p1_y + 15), f"[{p1_elem.upper()}]", fill=ELEMENT_DATA.get(p1_elem, {}).get("color", (200, 200, 200)), font=_get_font(11, bold=True))

    # Art Left
    art_w, art_h = 115, 130
    art1 = _load_hero_image(player1_hero.get("id", "tanjiro"), (art_w, art_h), corner_radius=10)
    im.paste(art1, (p1_x + 16, p1_y + 44), art1)
    draw.rounded_rectangle([(p1_x + 15, p1_y + 43), (p1_x + 16 + art_w, p1_y + 44 + art_h)], radius=10, outline=p1_color, width=1)

    # Info Left
    p1_info_x = p1_x + art_w + 26
    draw.text((p1_info_x, p1_y + 45), player1_hero.get("name", "Fighter")[:14], fill=(255, 255, 255, 255), font=_get_font(18, bold=True))
    draw.text((p1_info_x, p1_y + 70), f"Master: {player1_name[:12]}", fill=(160, 150, 185, 255), font=_get_font(11))

    # Power & Tech
    p1_power = player1_hero.get("power", 500) + player1_hero.get("power_bonus", 0)
    draw.rounded_rectangle([(p1_info_x, p1_y + 92), (p1_info_x + 120, p1_y + 118)], radius=6, fill=(32, 24, 52, 255), outline=(75, 60, 105, 255), width=1)
    draw.text((p1_info_x + 10, p1_y + 97), f"POWER: {p1_power}", fill=(255, 255, 255, 255), font=_get_font(11, bold=True))
    draw.text((p1_info_x, p1_y + 126), f"MOVE: {player1_hero.get('move', 'Strike')[:18]}", fill=(216, 180, 254), font=_get_font(10, bold=True))

    # HP Bar Left
    hp1_pct = max(0.0, min(1.0, p1_hp / p1_max_hp if p1_max_hp > 0 else 0.0))
    bar1_w = card_w - 32
    bar1_y = p1_y + card_h - 75
    draw.text((p1_x + 16, bar1_y - 17), f"HEALTH: {max(0, p1_hp)} / {p1_max_hp} HP", fill=(210, 200, 230, 255), font=_get_font(11, bold=True))
    draw.rounded_rectangle([(p1_x + 16, bar1_y), (p1_x + 16 + bar1_w, bar1_y + 9)], radius=5, fill=(35, 28, 52, 255))
    hp_fill1_w = int(bar1_w * hp1_pct)
    hp_color1 = (34, 197, 94) if hp1_pct > 0.4 else ((234, 179, 8) if hp1_pct > 0.2 else (239, 68, 68))
    if hp_fill1_w > 0:
        draw.rounded_rectangle([(p1_x + 16, bar1_y), (p1_x + 16 + hp_fill1_w, bar1_y + 9)], radius=5, fill=hp_color1)

    # Cursed Energy / Ultimate Bar Left
    ce1_pct = max(0.0, min(1.0, p1_energy / 100.0))
    ce1_y = bar1_y + 28
    ce1_label = "CLIMAX READY (100%)" if p1_energy >= 100 else f"{p1_energy_name.upper()}: {p1_energy}%"
    ce1_col = (250, 204, 21) if p1_energy >= 100 else (165, 243, 252)
    draw.text((p1_x + 16, ce1_y - 14), ce1_label, fill=ce1_col, font=_get_font(10, bold=True))
    draw.rounded_rectangle([(p1_x + 16, ce1_y), (p1_x + 16 + bar1_w, ce1_y + 8)], radius=4, fill=(28, 22, 42, 255))
    ce_fill1_w = int(bar1_w * ce1_pct)
    ce_color1 = (234, 179, 8) if p1_energy >= 100 else (6, 182, 212)
    if ce_fill1_w > 0:
        draw.rounded_rectangle([(p1_x + 16, ce1_y), (p1_x + 16 + ce_fill1_w, ce1_y + 8)], radius=4, fill=ce_color1)

    # ------------------ RIGHT FIGHTER (Player 2 / Rival) ------------------
    p2_x = w - card_w - 35
    p2_y = p1_y
    p2_rarity = player2_hero.get("rarity", "Common")
    p2_color = RARITY_COLORS.get(p2_rarity, (156, 163, 175))
    p2_outline = (234, 179, 8) if winner_num == 2 else (p2_color if winner_num == 0 else (60, 50, 80))

    draw.rounded_rectangle([(p2_x, p2_y), (p2_x + card_w, p2_y + card_h)], radius=16, fill=(22, 17, 36, 255), outline=p2_outline, width=3 if winner_num == 2 else 1)

    # Top banner in card
    draw.rounded_rectangle([(p2_x + 12, p2_y + 12), (p2_x + card_w - 12, p2_y + 36)], radius=6, fill=(16, 12, 26, 255))
    draw.text((p2_x + 20, p2_y + 15), f"« {player2_hero.get('anime', 'Anime').upper()} »", fill=p2_color, font=_get_font(11, bold=True))
    p2_elem = player2_hero.get("element", "Fire")
    draw.text((p2_x + card_w - 95, p2_y + 15), f"[{p2_elem.upper()}]", fill=ELEMENT_DATA.get(p2_elem, {}).get("color", (200, 200, 200)), font=_get_font(11, bold=True))

    # Art Right
    art2 = _load_hero_image(player2_hero.get("id", "sukuna"), (art_w, art_h), corner_radius=10)
    im.paste(art2, (p2_x + 16, p2_y + 44), art2)
    draw.rounded_rectangle([(p2_x + 15, p2_y + 43), (p2_x + 16 + art_w, p2_y + 44 + art_h)], radius=10, outline=p2_color, width=1)

    # Info Right
    p2_info_x = p2_x + art_w + 26
    draw.text((p2_info_x, p2_y + 45), player2_hero.get("name", "Fighter")[:14], fill=(255, 255, 255, 255), font=_get_font(18, bold=True))
    draw.text((p2_info_x, p2_y + 70), f"Master: {player2_name[:12]}", fill=(160, 150, 185, 255), font=_get_font(11))

    # Power & Tech
    p2_power = player2_hero.get("power", 500) + player2_hero.get("power_bonus", 0)
    draw.rounded_rectangle([(p2_info_x, p2_y + 92), (p2_info_x + 120, p2_y + 118)], radius=6, fill=(32, 24, 52, 255), outline=(75, 60, 105, 255), width=1)
    draw.text((p2_info_x + 10, p2_y + 97), f"POWER: {p2_power}", fill=(255, 255, 255, 255), font=_get_font(11, bold=True))
    draw.text((p2_info_x, p2_y + 126), f"MOVE: {player2_hero.get('move', 'Strike')[:18]}", fill=(216, 180, 254), font=_get_font(10, bold=True))

    # HP Bar Right
    hp2_pct = max(0.0, min(1.0, p2_hp / p2_max_hp if p2_max_hp > 0 else 0.0))
    bar2_y = p2_y + card_h - 75
    draw.text((p2_x + 16, bar2_y - 17), f"HEALTH: {max(0, p2_hp)} / {p2_max_hp} HP", fill=(210, 200, 230, 255), font=_get_font(11, bold=True))
    draw.rounded_rectangle([(p2_x + 16, bar2_y), (p2_x + 16 + bar1_w, bar2_y + 9)], radius=5, fill=(35, 28, 52, 255))
    hp_fill2_w = int(bar1_w * hp2_pct)
    hp_color2 = (34, 197, 94) if hp2_pct > 0.4 else ((234, 179, 8) if hp2_pct > 0.2 else (239, 68, 68))
    if hp_fill2_w > 0:
        draw.rounded_rectangle([(p2_x + 16, bar2_y), (p2_x + 16 + hp_fill2_w, bar2_y + 9)], radius=5, fill=hp_color2)

    # Cursed Energy / Ultimate Bar Right
    ce2_pct = max(0.0, min(1.0, p2_energy / 100.0))
    ce2_y = bar2_y + 28
    ce2_label = "CLIMAX READY (100%)" if p2_energy >= 100 else f"{p2_energy_name.upper()}: {p2_energy}%"
    ce2_col = (250, 204, 21) if p2_energy >= 100 else (165, 243, 252)
    draw.text((p2_x + 16, ce2_y - 14), ce2_label, fill=ce2_col, font=_get_font(10, bold=True))
    draw.rounded_rectangle([(p2_x + 16, ce2_y), (p2_x + 16 + bar1_w, ce2_y + 8)], radius=4, fill=(28, 22, 42, 255))
    ce_fill2_w = int(bar1_w * ce2_pct)
    ce_color2 = (234, 179, 8) if p2_energy >= 100 else (6, 182, 212)
    if ce_fill2_w > 0:
        draw.rounded_rectangle([(p2_x + 16, ce2_y), (p2_x + 16 + ce_fill2_w, ce2_y + 8)], radius=4, fill=ce_color2)

    # ------------------ CENTER VS EMBLEM ------------------
    vs_cx, vs_cy = w // 2, 200
    draw.ellipse([(vs_cx - 36, vs_cy - 36), (vs_cx + 36, vs_cy + 36)], fill=(24, 18, 40, 255), outline=(234, 179, 8), width=2)
    draw.text((vs_cx - 20, vs_cy - 16), "VS", fill=(255, 255, 255, 255), font=_get_font(28, bold=True))

    # ------------------ BOTTOM BATTLE STATUS BANNER ------------------
    bottom_y = 365
    draw.rounded_rectangle([(35, bottom_y), (w - 35, bottom_y + 55)], radius=12, fill=(20, 16, 32, 255), outline=(60, 50, 80, 255), width=1)

    if winner_num == 1:
        draw.text((55, bottom_y + 16), f"VICTORY: {player1_hero.get('name', 'Player 1').upper()} WINS! (+{gold_reward} Gold)", fill=(234, 179, 8), font=_get_font(16, bold=True))
        if chest_reward:
            draw.text((w - 340, bottom_y + 16), f"VAULT DROP: {chest_reward.upper()}", fill=(168, 85, 247), font=_get_font(14, bold=True))
    elif winner_num == 2:
        draw.text((55, bottom_y + 16), f"DEFEAT: {player2_hero.get('name', 'Rival').upper()} OVERPOWERED YOU!", fill=(239, 68, 68), font=_get_font(16, bold=True))
    else:
        turn_msg = turn_action_text or "ROUND IN PROGRESS • SELECT YOUR TACTICAL COMBAT MOVE"
        draw.text((55, bottom_y + 18), turn_msg[:75], fill=(220, 210, 245, 255), font=_get_font(13, bold=True))

    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out


def render_chest_open_card(
    user_name: str,
    chest_type: str,
    unlocked_hero: dict[str, Any] | None = None,
    is_duplicate: bool = False,
    gold_reward: int = 100,
    reward_type: str = "hero",
    reward_data: dict[str, Any] | None = None,
) -> io.BytesIO:
    """
    Renders an exhilarating 880x400 Chest Opening Card supporting all loot types:
    Champions, Cursed Relics/Weapons, Profile Banners, Battle Potions, and Gold Jackpots.
    """
    data = reward_data or unlocked_hero or {}
    w, h = 880, 400
    rarity = data.get("rarity", "Common")
    r_color = RARITY_COLORS.get(rarity, (156, 163, 175))

    im = Image.new("RGBA", (w, h), (14, 11, 24, 255))

    # Sunburst rays in center
    rays = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    rdraw = ImageDraw.Draw(rays)
    cx, cy = w // 2, h // 2
    for angle in range(0, 360, 20):
        rad = math.radians(angle)
        rad2 = math.radians(angle + 10)
        x1 = cx + int(480 * math.cos(rad))
        y1 = cy + int(480 * math.sin(rad))
        x2 = cx + int(480 * math.cos(rad2))
        y2 = cy + int(480 * math.sin(rad2))
        rdraw.polygon([(cx, cy), (x1, y1), (x2, y2)], fill=(r_color[0], r_color[1], r_color[2], 22))

    im = Image.alpha_composite(im, rays)
    draw = ImageDraw.Draw(im)

    # Frame
    draw.rounded_rectangle([(8, 8), (w - 8, h - 8)], radius=20, outline=r_color, width=2)
    draw.rounded_rectangle([(24, 16), (w - 24, 20)], radius=2, fill=r_color)
    draw.text((w // 2 - 120, 26), f"{chest_type.upper()} UNBOXED!", fill=r_color, font=_get_font(13, bold=True))

    art_x, art_y = 60, 65
    art_w, art_h = 210, 260
    rx = art_x + art_w + 40

    if reward_type == "relic":
        # Left Relic Icon Card
        draw.rounded_rectangle([(art_x, art_y), (art_x + art_w, art_y + art_h)], radius=16, fill=(26, 20, 40, 255), outline=r_color, width=2)
        draw.ellipse([(art_x + 35, art_y + 35), (art_x + art_w - 35, art_y + art_h - 75)], fill=(38, 28, 58, 255), outline=r_color, width=2)
        draw.text((art_x + 55, art_y + 80), "[RELIC]", fill=r_color, font=_get_font(24, bold=True))
        draw.text((art_x + 38, art_y + art_h - 55), "ANIME WEAPON", fill=(170, 160, 200, 255), font=_get_font(13, bold=True))

        anime_title = data.get("anime", "Anime").upper()
        draw.rounded_rectangle([(rx, 65), (rx + 240, 92)], radius=6, fill=(28, 20, 44, 255), outline=r_color, width=1)
        draw.text((rx + 14, 71), f"<< {anime_title} >>", fill=r_color, font=_get_font(12, bold=True))
        draw.text((rx, 105), data.get("name", "Relic")[:22], fill=(255, 255, 255, 255), font=_get_font(26, bold=True))

        draw.rounded_rectangle([(rx, 150), (rx + 130, 176)], radius=6, fill=(35, 26, 52, 255), outline=r_color, width=1)
        draw.text((rx + 14, 155), rarity.upper(), fill=r_color, font=_get_font(12, bold=True))

        draw.rounded_rectangle([(rx + 145, 150), (rx + 335, 176)], radius=6, fill=(35, 26, 52, 255), outline=(70, 60, 95, 255), width=1)
        draw.text((rx + 158, 155), "TYPE: CURSED ARTIFACT", fill=(216, 180, 254, 255), font=_get_font(11, bold=True))

        p_box_y = 190
        draw.rounded_rectangle([(rx, p_box_y), (w - 60, p_box_y + 60)], radius=10, fill=(22, 17, 36, 255), outline=(55, 45, 75, 255), width=1)
        draw.text((rx + 16, p_box_y + 10), "POWER BONUS", fill=(160, 150, 185, 255), font=_get_font(10, bold=True))
        draw.text((rx + 16, p_box_y + 26), f"+{data.get('power', 100)} COMBAT POWER", fill=(250, 204, 21), font=_get_font(15, bold=True))
        draw.text((rx + 240, p_box_y + 10), "SPECIAL PERK", fill=(160, 150, 185, 255), font=_get_font(10, bold=True))
        draw.text((rx + 240, p_box_y + 26), f"> {data.get('effect', 'Bonus')[:24]}", fill=(216, 180, 254, 255), font=_get_font(13, bold=True))

        status_y = 265
        draw.rounded_rectangle([(rx, status_y), (w - 60, status_y + 44)], radius=8, fill=(38, 28, 18, 255), outline=(234, 179, 8), width=1)
        draw.text((rx + 16, status_y + 14), f"EQUIPPED! Boosted all your champions' combat power (+{gold_reward} Gold).", fill=(253, 224, 71), font=_get_font(12, bold=True))

    elif reward_type == "banner":
        # Left Banner Preview Card
        draw.rounded_rectangle([(art_x, art_y), (art_x + art_w, art_y + art_h)], radius=16, fill=(18, 25, 45, 255), outline=r_color, width=2)
        draw.rounded_rectangle([(art_x + 15, art_y + 40), (art_x + art_w - 15, art_y + 140)], radius=10, fill=(30, 45, 80, 255), outline=r_color, width=1)
        draw.text((art_x + 24, art_y + 80), "[BANNER PREVIEW]", fill=r_color, font=_get_font(14, bold=True))
        draw.text((art_x + 35, art_y + art_h - 55), "PROFILE THEME", fill=(170, 200, 240, 255), font=_get_font(13, bold=True))

        anime_title = data.get("anime", "Anime").upper()
        draw.rounded_rectangle([(rx, 65), (rx + 240, 92)], radius=6, fill=(28, 20, 44, 255), outline=r_color, width=1)
        draw.text((rx + 14, 71), f"<< {anime_title} >>", fill=r_color, font=_get_font(12, bold=True))
        draw.text((rx, 105), data.get("name", "Banner")[:22], fill=(255, 255, 255, 255), font=_get_font(28, bold=True))

        draw.rounded_rectangle([(rx, 150), (rx + 130, 176)], radius=6, fill=(35, 26, 52, 255), outline=r_color, width=1)
        draw.text((rx + 14, 155), rarity.upper(), fill=r_color, font=_get_font(12, bold=True))

        draw.rounded_rectangle([(rx + 145, 150), (rx + 335, 176)], radius=6, fill=(35, 26, 52, 255), outline=(70, 60, 95, 255), width=1)
        draw.text((rx + 158, 155), "TYPE: PROFILE BANNER", fill=(165, 243, 252, 255), font=_get_font(11, bold=True))

        p_box_y = 190
        draw.rounded_rectangle([(rx, p_box_y), (w - 60, p_box_y + 60)], radius=10, fill=(22, 17, 36, 255), outline=(55, 45, 75, 255), width=1)
        draw.text((rx + 16, p_box_y + 10), "BANNER THEME", fill=(160, 150, 185, 255), font=_get_font(10, bold=True))
        draw.text((rx + 16, p_box_y + 26), f"{data.get('name', 'Banner').upper()}", fill=(255, 255, 255, 255), font=_get_font(15, bold=True))
        draw.text((rx + 240, p_box_y + 10), "PALETTE AESTHETIC", fill=(160, 150, 185, 255), font=_get_font(10, bold=True))
        draw.text((rx + 240, p_box_y + 26), f"> {data.get('desc', 'Aesthetic')[:26]}", fill=(165, 243, 252, 255), font=_get_font(12, bold=True))

        status_y = 265
        draw.rounded_rectangle([(rx, status_y), (w - 60, status_y + 44)], radius=8, fill=(18, 32, 45, 255), outline=(6, 182, 212), width=1)
        draw.text((rx + 16, status_y + 14), f"BANNER UNLOCKED! Set as your active Hunter Profile Banner (+{gold_reward} Gold).", fill=(165, 243, 252), font=_get_font(12, bold=True))

    elif reward_type == "consumable":
        # Left Consumable Card
        draw.rounded_rectangle([(art_x, art_y), (art_x + art_w, art_y + art_h)], radius=16, fill=(20, 35, 30, 255), outline=(34, 197, 94), width=2)
        draw.ellipse([(art_x + 35, art_y + 35), (art_x + art_w - 35, art_y + art_h - 75)], fill=(28, 52, 42, 255), outline=(34, 197, 94), width=2)
        draw.text((art_x + 50, art_y + 80), "[POTION]", fill=(34, 197, 94), font=_get_font(22, bold=True))
        draw.text((art_x + 30, art_y + art_h - 55), "BATTLE SUPPLIES", fill=(134, 239, 172), font=_get_font(13, bold=True))

        draw.rounded_rectangle([(rx, 65), (rx + 240, 92)], radius=6, fill=(20, 35, 30, 255), outline=(34, 197, 94), width=1)
        draw.text((rx + 14, 71), "<< COMBAT ELIXIR >>", fill=(134, 239, 172), font=_get_font(12, bold=True))
        draw.text((rx, 105), "2x Healing Potions", fill=(255, 255, 255, 255), font=_get_font(28, bold=True))

        p_box_y = 175
        draw.rounded_rectangle([(rx, p_box_y), (w - 60, p_box_y + 65)], radius=10, fill=(22, 17, 36, 255), outline=(55, 45, 75, 255), width=1)
        draw.text((rx + 16, p_box_y + 10), "CONSUMABLE EFFECT", fill=(160, 150, 185, 255), font=_get_font(10, bold=True))
        draw.text((rx + 16, p_box_y + 26), "RECOVERS +35 HP IN DUELS", fill=(34, 197, 94), font=_get_font(15, bold=True))

        status_y = 265
        draw.rounded_rectangle([(rx, status_y), (w - 60, status_y + 44)], radius=8, fill=(18, 38, 24, 255), outline=(34, 197, 94), width=1)
        draw.text((rx + 16, status_y + 14), f"STOCKED! 2x Potions added to your Hunter Pouch (+{gold_reward} Gold).", fill=(134, 239, 172), font=_get_font(12, bold=True))

    elif reward_type == "jackpot":
        # Left Jackpot Card
        draw.rounded_rectangle([(art_x, art_y), (art_x + art_w, art_y + art_h)], radius=16, fill=(35, 30, 15, 255), outline=(234, 179, 8), width=2)
        draw.ellipse([(art_x + 35, art_y + 35), (art_x + art_w - 35, art_y + art_h - 75)], fill=(50, 42, 20, 255), outline=(234, 179, 8), width=2)
        draw.text((art_x + 40, art_y + 80), "[JACKPOT]", fill=(234, 179, 8), font=_get_font(22, bold=True))
        draw.text((art_x + 38, art_y + art_h - 55), "ROYAL BOUNTY", fill=(253, 224, 71), font=_get_font(13, bold=True))

        draw.rounded_rectangle([(rx, 65), (rx + 240, 92)], radius=6, fill=(35, 30, 15, 255), outline=(234, 179, 8), width=1)
        draw.text((rx + 14, 71), "<< MONARCH TREASURY >>", fill=(250, 204, 21), font=_get_font(12, bold=True))
        draw.text((rx, 105), f"+{gold_reward:,} Gold Jackpot!", fill=(255, 255, 255, 255), font=_get_font(28, bold=True))

        p_box_y = 175
        draw.rounded_rectangle([(rx, p_box_y), (w - 60, p_box_y + 65)], radius=10, fill=(22, 17, 36, 255), outline=(55, 45, 75, 255), width=1)
        draw.text((rx + 16, p_box_y + 10), "EXPEDITION SURGE", fill=(160, 150, 185, 255), font=_get_font(10, bold=True))
        draw.text((rx + 16, p_box_y + 26), "+150 HUNTER XP BONUS", fill=(216, 180, 254), font=_get_font(15, bold=True))

        status_y = 265
        draw.rounded_rectangle([(rx, status_y), (w - 60, status_y + 44)], radius=8, fill=(38, 28, 18, 255), outline=(234, 179, 8), width=1)
        draw.text((rx + 16, status_y + 14), f"GOLD SURGE! Massive bounty deposited directly into your Treasury.", fill=(253, 224, 71), font=_get_font(12, bold=True))

    else:
        # Default: Champion Hero Unlock
        hero_art = _load_hero_image(data.get("id", "tanjiro"), (art_w, art_h), corner_radius=14)
        im.paste(hero_art, (art_x, art_y), hero_art)
        draw.rounded_rectangle([(art_x - 3, art_y - 3), (art_x + art_w + 3, art_y + art_h + 3)], radius=16, outline=r_color, width=2)

        anime_title = data.get("anime", "Anime Series").upper()
        draw.rounded_rectangle([(rx, 65), (rx + 240, 92)], radius=6, fill=(28, 20, 44, 255), outline=r_color, width=1)
        draw.text((rx + 14, 71), f"<< {anime_title} >>", fill=r_color, font=_get_font(12, bold=True))

        hero_name = data.get("name", "Unknown Hero")
        draw.text((rx, 105), hero_name, fill=(255, 255, 255, 255), font=_get_font(28, bold=True))

        # Rarity & Element Tags
        elem = data.get("element", "Water")
        elem_info = ELEMENT_DATA.get(elem, {"symbol": elem, "color": (168, 85, 247)})
        draw.rounded_rectangle([(rx, 150), (rx + 130, 176)], radius=6, fill=(35, 26, 52, 255), outline=r_color, width=1)
        draw.text((rx + 14, 155), f"{rarity.upper()}", fill=r_color, font=_get_font(12, bold=True))

        draw.rounded_rectangle([(rx + 145, 150), (rx + 295, 176)], radius=6, fill=(35, 26, 52, 255), outline=(70, 60, 95, 255), width=1)
        draw.text((rx + 158, 155), f"ELEMENT: {elem.upper()}", fill=elem_info["color"], font=_get_font(11, bold=True))

        # Power & Technique
        p_box_y = 190
        draw.rounded_rectangle([(rx, p_box_y), (w - 60, p_box_y + 60)], radius=10, fill=(22, 17, 36, 255), outline=(55, 45, 75, 255), width=1)
        power_val = data.get("power", 500)
        draw.text((rx + 16, p_box_y + 10), "BASE POWER", fill=(160, 150, 185, 255), font=_get_font(10, bold=True))
        draw.text((rx + 16, p_box_y + 26), f"{power_val} COMBAT RATING", fill=(255, 255, 255, 255), font=_get_font(15, bold=True))

        move_val = data.get("move", "Special Hit")
        draw.text((rx + 240, p_box_y + 10), "SIGNATURE MOVE", fill=(160, 150, 185, 255), font=_get_font(10, bold=True))
        draw.text((rx + 240, p_box_y + 26), f"> {move_val[:24]}", fill=(216, 180, 254, 255), font=_get_font(13, bold=True))

        # Status / Duplicate banner
        status_y = 265
        if is_duplicate:
            draw.rounded_rectangle([(rx, status_y), (w - 60, status_y + 44)], radius=8, fill=(38, 28, 18, 255), outline=(234, 179, 8), width=1)
            draw.text((rx + 16, status_y + 14), f"DUPLICATE FIGHTER: Upgraded combat power by +50! (+{gold_reward} Gold)", fill=(253, 224, 71), font=_get_font(12, bold=True))
        else:
            draw.rounded_rectangle([(rx, status_y), (w - 60, status_y + 44)], radius=8, fill=(18, 38, 24, 255), outline=(34, 197, 94), width=1)
            draw.text((rx + 16, status_y + 14), f"NEW CHAMPION UNLOCKED! Added to {user_name}'s Battle Roster.", fill=(134, 239, 172), font=_get_font(12, bold=True))

    # Bottom Footer
    draw.text((60, h - 35), "KYRO SHADOW VAULT • CHEST REVEAL RECORD", fill=(110, 100, 135, 255), font=_get_font(11, bold=True))

    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out
