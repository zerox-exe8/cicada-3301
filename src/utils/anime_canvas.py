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

# Theme Color Palettes (Background base, Card surface, Accent RGB, Accent Hex)
THEMES: dict[str, dict[str, Any]] = {
    "shadow": {
        "bg": (12, 10, 20, 255),
        "surface": (22, 18, 36, 255),
        "surface_card": (26, 21, 42, 255),
        "border": (58, 48, 85, 255),
        "accent": (168, 85, 247),  # Neon Purple
        "accent_glow": (147, 51, 234, 70),
        "highlight": (216, 180, 254),
        "name": "Shadow Realm",
    },
    "crimson": {
        "bg": (20, 9, 14, 255),
        "surface": (34, 15, 24, 255),
        "surface_card": (42, 19, 30, 255),
        "border": (85, 40, 55, 255),
        "accent": (239, 68, 68),  # Blood Red
        "accent_glow": (220, 38, 38, 70),
        "highlight": (252, 165, 165),
        "name": "Blood Moon",
    },
    "cyber": {
        "bg": (8, 16, 28, 255),
        "surface": (15, 26, 45, 255),
        "surface_card": (22, 38, 65, 255),
        "border": (40, 68, 100, 255),
        "accent": (6, 182, 212),  # Cyber Cyan
        "accent_glow": (14, 165, 233, 70),
        "highlight": (165, 243, 252),
        "name": "Neon Cyber",
    },
    "gold": {
        "bg": (20, 17, 8, 255),
        "surface": (34, 28, 14, 255),
        "surface_card": (48, 40, 20, 255),
        "border": (85, 70, 40, 255),
        "accent": (234, 179, 8),  # Solar Gold
        "accent_glow": (202, 138, 4, 70),
        "highlight": (253, 224, 71),
        "name": "Monarch Sun",
    },
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
    w, h = 900, 390
    theme = THEMES.get(theme_key, THEMES["shadow"])
    accent = theme["accent"]

    im = Image.new("RGBA", (w, h), theme["bg"])

    # Ambient glows
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([(-60, -60), (320, 320)], fill=(accent[0], accent[1], accent[2], 40))
    gdraw.ellipse([(w - 380, 20), (w + 60, h + 80)], fill=(accent[0], accent[1], accent[2], 45))
    im = Image.alpha_composite(im, glow)
    draw = ImageDraw.Draw(im)

    # Frame
    draw.rounded_rectangle([(8, 8), (w - 8, h - 8)], radius=20, outline=(55, 45, 75, 255), width=2)
    draw.rounded_rectangle([(10, 10), (w - 10, h - 10)], radius=18, outline=accent, width=1)

    # Top Header strip
    draw.rounded_rectangle([(24, 18), (w - 24, 22)], radius=2, fill=accent)

    # Player Avatar
    av_size = 96
    av_x, av_y = 35, 45
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
        draw.text((av_x + 32, av_y + 30), username[:1].upper(), fill=(255, 255, 255, 255), font=_get_font(36, bold=True))


    user_x = av_x + av_size + 20
    draw.text((user_x, av_y + 4), username[:18], fill=(255, 255, 255, 255), font=_get_font(26, bold=True))
    draw.text((user_x, av_y + 38), f"[ {title[:28]} ]", fill=theme["highlight"], font=_get_font(15))

    # Rank Badge
    badge_y = av_y + 64
    rank_color = (234, 179, 8) if "S" in rank else ((168, 85, 247) if "A" in rank else (59, 130, 246))
    draw.rounded_rectangle([(user_x, badge_y), (user_x + 155, badge_y + 26)], radius=6, fill=(28, 22, 42, 255), outline=rank_color, width=1)
    draw.text((user_x + 14, badge_y + 5), f"{rank.upper()} HUNTER", fill=rank_color, font=_get_font(12, bold=True))

    # Level Badge
    lvl_x = user_x + 168
    draw.rounded_rectangle([(lvl_x, badge_y), (lvl_x + 85, badge_y + 26)], radius=6, fill=(35, 30, 52, 255), outline=(90, 80, 120, 255), width=1)
    draw.text((lvl_x + 14, badge_y + 5), f"LVL {level}", fill=(240, 240, 255, 255), font=_get_font(12, bold=True))

    # Middle Stats Grid
    stats_y = 170
    total_battles = wins + losses
    win_rate = round((wins / total_battles * 100), 1) if total_battles > 0 else 0.0

    stat_cards = [
        ("WIN RATE", f"{win_rate}%", f"{wins}W / {losses}L"),
        ("STREAK", f"{streak}", "Unbroken Record"),
        ("GOLD", f"{gold:,}", "Treasury"),
        ("VAULT", f"{chests_count}", "Chests Ready"),
    ]

    pill_w = 120
    start_x = 35
    for i, (lbl, val, sub) in enumerate(stat_cards):
        cx = start_x + (i * (pill_w + 14))
        draw.rounded_rectangle([(cx, stats_y), (cx + pill_w, stats_y + 72)], radius=10, fill=theme["surface"], outline=(55, 45, 75, 255), width=1)
        draw.text((cx + 12, stats_y + 10), lbl, fill=(160, 150, 185, 255), font=_get_font(11, bold=True))
        draw.text((cx + 12, stats_y + 28), val, fill=(255, 255, 255, 255), font=_get_font(19, bold=True))
        draw.text((cx + 12, stats_y + 52), sub, fill=(130, 120, 150, 255), font=_get_font(10))

    # XP Progress Bar
    xp_bar_y = 275
    bar_w = 522
    draw.text((35, xp_bar_y - 18), f"HUNTER PROGRESSION • {xp} / {xp_needed} XP", fill=(175, 165, 200, 255), font=_get_font(11, bold=True))
    draw.rounded_rectangle([(35, xp_bar_y), (35 + bar_w, xp_bar_y + 12)], radius=6, fill=(35, 30, 52, 255))
    progress = min(1.0, max(0.05, (xp / xp_needed) if xp_needed > 0 else 1.0))
    fill_w = int(bar_w * progress)
    draw.rounded_rectangle([(35, xp_bar_y), (35 + fill_w, xp_bar_y + 12)], radius=6, fill=accent)

    # Footer Branding
    draw.text((35, h - 35), "KYRO ANIME BATTLE ARENA • OFFICIAL HUNTER LICENSE", fill=(95, 85, 120, 255), font=_get_font(11, bold=True))

    # --- RIGHT SHOWCASE: EQUIPPED HERO CARD ---
    hero_card_x = 585
    hero_card_y = 35
    hero_card_w = 280
    hero_card_h = 320

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
        radius=16,
        fill=theme["surface_card"],
        outline=h_color,
        width=2,
    )

    # Anime Series Title Header Box
    draw.rounded_rectangle(
        [(hero_card_x + 10, hero_card_y + 10), (hero_card_x + hero_card_w - 10, hero_card_y + 36)],
        radius=6,
        fill=(18, 14, 28, 255),
    )
    draw.text((hero_card_x + 18, hero_card_y + 14), f"« {h_anime.upper()} »", fill=h_color, font=_get_font(11, bold=True))
    draw.text((hero_card_x + hero_card_w - 85, hero_card_y + 14), f"[{elem_info['symbol']}]", fill=elem_info["color"], font=_get_font(11, bold=True))

    # Character Artwork
    art_w, art_h = 130, 160
    art_x, art_y = hero_card_x + 14, hero_card_y + 44
    draw.rounded_rectangle(
        [(art_x - 2, art_y - 2), (art_x + art_w + 2, art_y + art_h + 2)],
        radius=10,
        outline=h_color,
        width=1,
    )
    hero_art = _load_hero_image(h_id, (art_w, art_h), corner_radius=8)
    im.paste(hero_art, (art_x, art_y), hero_art)

    # Info to right of artwork
    info_x = art_x + art_w + 14
    info_y = art_y + 4
    draw.text((info_x, info_y), h_name.split()[0], fill=(255, 255, 255, 255), font=_get_font(18, bold=True))
    if len(h_name.split()) > 1:
        draw.text((info_x, info_y + 22), " ".join(h_name.split()[1:])[:12], fill=(210, 200, 230, 255), font=_get_font(14, bold=True))

    # Rarity Pill
    draw.rounded_rectangle([(info_x, info_y + 48), (info_x + 95, info_y + 68)], radius=5, fill=(18, 14, 28, 255), outline=h_color, width=1)
    draw.text((info_x + 8, info_y + 52), h_rarity.upper(), fill=h_color, font=_get_font(10, bold=True))

    # Power Pill
    draw.rounded_rectangle([(info_x, info_y + 74), (info_x + 105, info_y + 104)], radius=6, fill=(35, 26, 52, 255), outline=(80, 65, 110, 255), width=1)
    draw.text((info_x + 8, info_y + 78), "COMBAT POWER", fill=(160, 150, 185, 255), font=_get_font(9, bold=True))
    draw.text((info_x + 8, info_y + 89), f"{h_power}", fill=(255, 255, 255, 255), font=_get_font(13, bold=True))

    # Signature Move Box below artwork
    move_y = art_y + art_h + 12
    draw.rounded_rectangle(
        [(hero_card_x + 12, move_y), (hero_card_x + hero_card_w - 12, move_y + 42)],
        radius=8,
        fill=(18, 14, 28, 255),
        outline=(50, 40, 70, 255),
        width=1,
    )
    draw.text((hero_card_x + 20, move_y + 6), "SIGNATURE TECHNIQUE", fill=(140, 130, 165, 255), font=_get_font(9, bold=True))
    draw.text((hero_card_x + 20, move_y + 20), f"» {h_move[:30]}", fill=theme["highlight"], font=_get_font(11, bold=True))

    # Card Footer Status
    draw.text((hero_card_x + 55, move_y + 50), "EQUIPPED MAIN FIGHTER", fill=(120, 110, 145, 255), font=_get_font(10, bold=True))

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
) -> io.BytesIO:
    """
    Renders a dramatic 940x440 Anime Clash Arena Card with both fighters' high-res portraits and live HP bars.
    """
    w, h = 940, 440
    im = Image.new("RGBA", (w, h), (12, 10, 22, 255))

    # Glows
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([(-50, -50), (320, 320)], fill=(59, 130, 246, 45))  # Left Blue
    gdraw.ellipse([(w - 320, -50), (w + 50, 320)], fill=(239, 68, 68, 45))  # Right Red
    im = Image.alpha_composite(im, glow)
    draw = ImageDraw.Draw(im)

    # Frame
    draw.rounded_rectangle([(8, 8), (w - 8, h - 8)], radius=20, outline=(55, 45, 75, 255), width=2)

    # Top arena header
    draw.rounded_rectangle([(24, 16), (w - 24, 20)], radius=2, fill=(168, 85, 247))
    draw.text((w // 2 - 90, 26), "SHADOW DUEL ARENA", fill=(216, 180, 254, 255), font=_get_font(13, bold=True))

    card_w, card_h = 390, 290

    # ------------------ LEFT FIGHTER (Player 1) ------------------
    p1_x, p1_y = 35, 60
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
    art_w, art_h = 115, 140
    art1 = _load_hero_image(player1_hero.get("id", "tanjiro"), (art_w, art_h), corner_radius=10)
    im.paste(art1, (p1_x + 16, p1_y + 46), art1)
    draw.rounded_rectangle([(p1_x + 15, p1_y + 45), (p1_x + 16 + art_w, p1_y + 46 + art_h)], radius=10, outline=p1_color, width=1)

    # Info Left
    p1_info_x = p1_x + art_w + 28
    draw.text((p1_info_x, p1_y + 48), player1_hero.get("name", "Fighter")[:14], fill=(255, 255, 255, 255), font=_get_font(19, bold=True))
    draw.text((p1_info_x, p1_y + 74), f"Master: {player1_name[:12]}", fill=(160, 150, 185, 255), font=_get_font(12))

    # Power
    p1_power = player1_hero.get("power", 500) + player1_hero.get("power_bonus", 0)
    draw.rounded_rectangle([(p1_info_x, p1_y + 98), (p1_info_x + 120, p1_y + 126)], radius=6, fill=(32, 24, 52, 255), outline=(75, 60, 105, 255), width=1)
    draw.text((p1_info_x + 10, p1_y + 104), f"POWER: {p1_power}", fill=(255, 255, 255, 255), font=_get_font(12, bold=True))

    # HP Bar Left
    hp1_pct = max(0.0, min(1.0, p1_hp / p1_max_hp if p1_max_hp > 0 else 0.0))
    bar1_w = card_w - 32
    bar1_y = p1_y + card_h - 60
    draw.text((p1_x + 16, bar1_y - 18), f"HEALTH: {max(0, p1_hp)} / {p1_max_hp} HP", fill=(210, 200, 230, 255), font=_get_font(11, bold=True))
    draw.rounded_rectangle([(p1_x + 16, bar1_y), (p1_x + 16 + bar1_w, bar1_y + 12)], radius=6, fill=(35, 28, 52, 255))
    hp_fill1_w = int(bar1_w * hp1_pct)
    hp_color1 = (34, 197, 94) if hp1_pct > 0.4 else ((234, 179, 8) if hp1_pct > 0.2 else (239, 68, 68))
    if hp_fill1_w > 0:
        draw.rounded_rectangle([(p1_x + 16, bar1_y), (p1_x + 16 + hp_fill1_w, bar1_y + 12)], radius=6, fill=hp_color1)

    # Signature Move
    draw.text((p1_x + 16, bar1_y + 20), f"MOVE: {player1_hero.get('move', 'Strike')[:32]}", fill=(150, 140, 175, 255), font=_get_font(11))

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
    im.paste(art2, (p2_x + 16, p2_y + 46), art2)
    draw.rounded_rectangle([(p2_x + 15, p2_y + 45), (p2_x + 16 + art_w, p2_y + 46 + art_h)], radius=10, outline=p2_color, width=1)

    # Info Right
    p2_info_x = p2_x + art_w + 28
    draw.text((p2_info_x, p2_y + 48), player2_hero.get("name", "Fighter")[:14], fill=(255, 255, 255, 255), font=_get_font(19, bold=True))
    draw.text((p2_info_x, p2_y + 74), f"Master: {player2_name[:12]}", fill=(160, 150, 185, 255), font=_get_font(12))

    # Power
    p2_power = player2_hero.get("power", 500) + player2_hero.get("power_bonus", 0)
    draw.rounded_rectangle([(p2_info_x, p2_y + 98), (p2_info_x + 120, p2_y + 126)], radius=6, fill=(32, 24, 52, 255), outline=(75, 60, 105, 255), width=1)
    draw.text((p2_info_x + 10, p2_y + 104), f"POWER: {p2_power}", fill=(255, 255, 255, 255), font=_get_font(12, bold=True))

    # HP Bar Right
    hp2_pct = max(0.0, min(1.0, p2_hp / p2_max_hp if p2_max_hp > 0 else 0.0))
    bar2_y = p2_y + card_h - 60
    draw.text((p2_x + 16, bar2_y - 18), f"HEALTH: {max(0, p2_hp)} / {p2_max_hp} HP", fill=(210, 200, 230, 255), font=_get_font(11, bold=True))
    draw.rounded_rectangle([(p2_x + 16, bar2_y), (p2_x + 16 + bar1_w, bar2_y + 12)], radius=6, fill=(35, 28, 52, 255))
    hp_fill2_w = int(bar1_w * hp2_pct)
    hp_color2 = (34, 197, 94) if hp2_pct > 0.4 else ((234, 179, 8) if hp2_pct > 0.2 else (239, 68, 68))
    if hp_fill2_w > 0:
        draw.rounded_rectangle([(p2_x + 16, bar2_y), (p2_x + 16 + hp_fill2_w, bar2_y + 12)], radius=6, fill=hp_color2)

    # Signature Move
    draw.text((p2_x + 16, bar2_y + 20), f"MOVE: {player2_hero.get('move', 'Strike')[:32]}", fill=(150, 140, 175, 255), font=_get_font(11))

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
    unlocked_hero: dict[str, Any],
    is_duplicate: bool = False,
    gold_reward: int = 100,
) -> io.BytesIO:
    """
    Renders an exhilarating 880x400 Chest Opening & Hero Unlock Card.
    """
    w, h = 880, 400
    rarity = unlocked_hero.get("rarity", "Common")
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

    # Top Header
    draw.rounded_rectangle([(24, 16), (w - 24, 20)], radius=2, fill=r_color)
    draw.text((w // 2 - 110, 26), f"{chest_type.upper()} UNBOXED!", fill=r_color, font=_get_font(13, bold=True))

    # Left: Character Artwork Showcase Card
    art_x, art_y = 60, 65
    art_w, art_h = 210, 260
    hero_art = _load_hero_image(unlocked_hero.get("id", "tanjiro"), (art_w, art_h), corner_radius=14)
    im.paste(hero_art, (art_x, art_y), hero_art)
    draw.rounded_rectangle([(art_x - 3, art_y - 3), (art_x + art_w + 3, art_y + art_h + 3)], radius=16, outline=r_color, width=2)

    # Right: Hero Unlocked Details
    rx = art_x + art_w + 40
    anime_title = unlocked_hero.get("anime", "Anime Series").upper()
    draw.rounded_rectangle([(rx, 65), (rx + 240, 92)], radius=6, fill=(28, 20, 44, 255), outline=r_color, width=1)
    draw.text((rx + 14, 71), f"« {anime_title} »", fill=r_color, font=_get_font(12, bold=True))

    hero_name = unlocked_hero.get("name", "Unknown Hero")
    draw.text((rx, 105), hero_name, fill=(255, 255, 255, 255), font=_get_font(28, bold=True))

    # Rarity & Element Tags
    elem = unlocked_hero.get("element", "Water")
    elem_info = ELEMENT_DATA.get(elem, {"symbol": elem, "color": (168, 85, 247)})
    draw.rounded_rectangle([(rx, 150), (rx + 130, 176)], radius=6, fill=(35, 26, 52, 255), outline=r_color, width=1)
    draw.text((rx + 14, 155), f"{rarity.upper()}", fill=r_color, font=_get_font(12, bold=True))

    draw.rounded_rectangle([(rx + 145, 150), (rx + 295, 176)], radius=6, fill=(35, 26, 52, 255), outline=(70, 60, 95, 255), width=1)
    draw.text((rx + 158, 155), f"ELEMENT: {elem.upper()}", fill=elem_info["color"], font=_get_font(11, bold=True))

    # Power & Technique
    p_box_y = 190
    draw.rounded_rectangle([(rx, p_box_y), (w - 60, p_box_y + 60)], radius=10, fill=(22, 17, 36, 255), outline=(55, 45, 75, 255), width=1)
    power_val = unlocked_hero.get("power", 500)
    draw.text((rx + 16, p_box_y + 10), "BASE POWER", fill=(160, 150, 185, 255), font=_get_font(10, bold=True))
    draw.text((rx + 16, p_box_y + 26), f"{power_val} COMBAT RATING", fill=(255, 255, 255, 255), font=_get_font(15, bold=True))

    move_val = unlocked_hero.get("move", "Special Hit")
    draw.text((rx + 240, p_box_y + 10), "SIGNATURE MOVE", fill=(160, 150, 185, 255), font=_get_font(10, bold=True))
    draw.text((rx + 240, p_box_y + 26), f"» {move_val[:24]}", fill=(216, 180, 254, 255), font=_get_font(13, bold=True))

    # Status / Duplicate banner
    status_y = 265
    if is_duplicate:
        draw.rounded_rectangle([(rx, status_y), (w - 60, status_y + 44)], radius=8, fill=(38, 28, 18, 255), outline=(234, 179, 8), width=1)
        draw.text((rx + 16, status_y + 14), f"DUPLICATE FIGHTER: Upgraded combat power by +25! (+{gold_reward} Gold)", fill=(253, 224, 71), font=_get_font(12, bold=True))
    else:
        draw.rounded_rectangle([(rx, status_y), (w - 60, status_y + 44)], radius=8, fill=(18, 38, 24, 255), outline=(34, 197, 94), width=1)
        draw.text((rx + 16, status_y + 14), f"NEW CHAMPION UNLOCKED! Added to {user_name}'s Battle Roster.", fill=(134, 239, 172), font=_get_font(12, bold=True))

    # Bottom Footer
    draw.text((60, h - 35), "KYRO SHADOW VAULT • CHEST REVEAL RECORD", fill=(110, 100, 135, 255), font=_get_font(11, bold=True))

    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out
