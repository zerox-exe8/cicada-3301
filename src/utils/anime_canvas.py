"""
Kyro Discord Bot - Ultra High-Resolution Anime Canvas Graphics Pipeline
Generates aesthetic, crisp, dark-mode anime game cards:
1. Hunter Profile Cards (Stats, Equipped Hero, Win-Rate, Theme Accents)
2. Battle Clash Arena Cards (Split Duel, VS Emblem, Element Advantage, Winner Trophy)
3. Chest Unboxing & Hero Reveal Cards (Glowing chest rays, Rarity Holo-Borders)
"""

from __future__ import annotations

import io
import math
import random
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# Theme Color Palettes (Background base, Card surface, Accent RGB, Accent Hex)
THEMES: dict[str, dict[str, Any]] = {
    "shadow": {
        "bg": (15, 12, 24, 255),
        "surface": (25, 20, 40, 240),
        "accent": (168, 85, 247),  # Neon Purple
        "accent_glow": (147, 51, 234, 120),
        "highlight": (216, 180, 254),
        "name": "Shadow Realm",
    },
    "crimson": {
        "bg": (24, 10, 14, 255),
        "surface": (38, 16, 22, 240),
        "accent": (239, 68, 68),  # Blood Red
        "accent_glow": (220, 38, 38, 120),
        "highlight": (252, 165, 165),
        "name": "Blood Moon",
    },
    "cyber": {
        "bg": (10, 18, 30, 255),
        "surface": (16, 28, 48, 240),
        "accent": (6, 182, 212),  # Cyber Cyan
        "accent_glow": (14, 165, 233, 120),
        "highlight": (165, 243, 252),
        "name": "Neon Cyber",
    },
    "gold": {
        "bg": (24, 20, 10, 255),
        "surface": (38, 32, 16, 240),
        "accent": (234, 179, 8),  # Solar Gold
        "accent_glow": (202, 138, 4, 120),
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
    Renders a stunning 880x360 Hunter License & Battle Profile Card.
    """
    w, h = 880, 360
    theme = THEMES.get(theme_key, THEMES["shadow"])
    accent = theme["accent"]

    # 1. Base Canvas with Deep Gradient
    im = Image.new("RGBA", (w, h), theme["bg"])
    draw = ImageDraw.Draw(im)

    # Ambient Glow Circles in Background
    glow_canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_canvas)
    glow_draw.ellipse([(-60, -60), (280, 280)], fill=(accent[0], accent[1], accent[2], 35))
    glow_draw.ellipse([(w - 320, 40), (w + 40, h + 80)], fill=(accent[0], accent[1], accent[2], 40))
    im = Image.alpha_composite(im, glow_canvas)
    draw = ImageDraw.Draw(im)

    # Outer Glass Frame & Accent Lines
    draw.rounded_rectangle([(8, 8), (w - 8, h - 8)], radius=22, outline=(60, 50, 80, 255), width=2)
    draw.rounded_rectangle([(10, 10), (w - 10, h - 10)], radius=20, outline=accent, width=1)

    # Top Header Strip
    draw.rounded_rectangle([(24, 18), (w - 24, 22)], radius=2, fill=accent)

    # 2. Left Section: Player Avatar & Identity
    av_size = 100
    av_x, av_y = 35, 45

    # Avatar Glow Ring
    draw.ellipse([(av_x - 4, av_y - 4), (av_x + av_size + 4, av_y + av_size + 4)], outline=accent, width=3)

    if avatar_bytes:
        try:
            av_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av_img = av_img.resize((av_size, av_size), Image.Resampling.LANCZOS)
            mask = Image.new("L", (av_size, av_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([(0, 0), (av_size, av_size)], fill=255)
            im.paste(av_img, (av_x, av_y), mask)
        except Exception:
            draw.ellipse([(av_x, av_y), (av_x + av_size, av_y + av_size)], fill=(40, 35, 55, 255))
    else:
        draw.ellipse([(av_x, av_y), (av_x + av_size, av_y + av_size)], fill=(40, 35, 55, 255))

    # Fonts
    font_name = _get_font(26, bold=True)
    font_title = _get_font(15, bold=False)
    font_badge = _get_font(13, bold=True)
    font_hero_name = _get_font(22, bold=True)
    font_stat_val = _get_font(18, bold=True)
    font_stat_lbl = _get_font(12, bold=False)

    # Username & Title
    user_x = av_x + av_size + 22
    draw.text((user_x, av_y + 4), username[:16], fill=(255, 255, 255, 255), font=font_name)
    draw.text((user_x, av_y + 36), f"« {title[:26]} »", fill=theme["highlight"], font=font_title)

    # Rank Badge (e.g. S-RANK HUNTER)
    badge_y = av_y + 64
    rank_color = (234, 179, 8) if "S" in rank else ((168, 85, 247) if "A" in rank else (59, 130, 246))
    rank_text = f"★ {rank.upper()} HUNTER"
    draw.rounded_rectangle([(user_x, badge_y), (user_x + 160, badge_y + 26)], radius=6, fill=(25, 20, 38, 255), outline=rank_color, width=1)
    draw.text((user_x + 14, badge_y + 5), rank_text, fill=rank_color, font=font_badge)

    # Level Badge
    lvl_x = user_x + 172
    draw.rounded_rectangle([(lvl_x, badge_y), (lvl_x + 90, badge_y + 26)], radius=6, fill=(35, 30, 50, 255), outline=(100, 90, 130, 255), width=1)
    draw.text((lvl_x + 12, badge_y + 5), f"LVL {level}", fill=(240, 240, 255, 255), font=font_badge)

    # 3. Middle Stats Bar: Win Rate, Streaks, Vault
    stats_y = 175
    total_battles = wins + losses
    win_rate = round((wins / total_battles * 100), 1) if total_battles > 0 else 0.0

    stat_cards = [
        ("WIN RATE", f"{win_rate}%", f"{wins}W / {losses}L"),
        ("STREAK", f"🔥 {streak}", "Unbroken"),
        ("GOLD", f"🪙 {gold:,}", "Treasury"),
        ("VAULT", f"📦 {chests_count}", "Chests Ready"),
    ]

    pill_w = 115
    start_x = 35
    for i, (lbl, val, sub) in enumerate(stat_cards):
        cx = start_x + (i * (pill_w + 12))
        draw.rounded_rectangle([(cx, stats_y), (cx + pill_w, stats_y + 68)], radius=10, fill=theme["surface"], outline=(55, 45, 75, 255), width=1)
        draw.text((cx + 10, stats_y + 8), lbl, fill=(160, 150, 185, 255), font=font_stat_lbl)
        draw.text((cx + 10, stats_y + 24), val, fill=(255, 255, 255, 255), font=font_stat_val)
        draw.text((cx + 10, stats_y + 48), sub, fill=(130, 120, 150, 255), font=_get_font(10))

    # 4. XP Progress Bar at Bottom-Left
    xp_bar_y = 265
    bar_w = 495
    draw.text((35, xp_bar_y - 18), f"HUNTER PROGRESSION • {xp}/{xp_needed} XP", fill=(170, 160, 195, 255), font=_get_font(11, bold=True))
    draw.rounded_rectangle([(35, xp_bar_y), (35 + bar_w, xp_bar_y + 12)], radius=6, fill=(35, 30, 50, 255))
    progress = min(1.0, max(0.05, (xp / xp_needed) if xp_needed > 0 else 1.0))
    fill_w = int(bar_w * progress)
    draw.rounded_rectangle([(35, xp_bar_y), (35 + fill_w, xp_bar_y + 12)], radius=6, fill=accent)

    # 5. Right Section: Equipped Anime Champion Showcase
    hero_card_x = 555
    hero_card_y = 35
    hero_card_w = 290
    hero_card_h = 285

    # Hero Card Base
    h_rarity = hero_data.get("rarity", "Common")
    h_color = RARITY_COLORS.get(h_rarity, (156, 163, 175))

    draw.rounded_rectangle(
        [(hero_card_x, hero_card_y), (hero_card_x + hero_card_w, hero_card_y + hero_card_h)],
        radius=16,
        fill=(22, 18, 34, 255),
        outline=h_color,
        width=2,
    )

    # Top Rarity & Element Header in Hero Card
    draw.rounded_rectangle(
        [(hero_card_x + 12, hero_card_y + 12), (hero_card_x + hero_card_w - 12, hero_card_y + 38)],
        radius=6,
        fill=(32, 26, 48, 255),
    )
    elem = hero_data.get("element", "Shadow")
    elem_info = ELEMENT_DATA.get(elem, {"symbol": elem, "color": (168, 85, 247)})
    draw.text((hero_card_x + 22, hero_card_y + 16), f"✦ {h_rarity.upper()}", fill=h_color, font=font_badge)
    draw.text((hero_card_x + hero_card_w - 100, hero_card_y + 16), f"[{elem_info['symbol']}]", fill=elem_info["color"], font=font_badge)

    # Hero Center Emblem / Box
    art_box_y = hero_card_y + 50
    draw.rounded_rectangle(
        [(hero_card_x + 16, art_box_y), (hero_card_x + hero_card_w - 16, art_box_y + 115)],
        radius=12,
        fill=(15, 12, 24, 255),
        outline=(50, 42, 70, 255),
        width=1,
    )

    # Big Stylized Hero Silhouette Text / Kanji
    hero_name = hero_data.get("name", "Unknown Hero")
    stars_count = hero_data.get("stars", 1)
    stars_str = "★ " * stars_count

    # Hero Name
    draw.text((hero_card_x + 24, art_box_y + 24), hero_name[:18], fill=(255, 255, 255, 255), font=font_hero_name)
    # Stars
    draw.text((hero_card_x + 24, art_box_y + 60), stars_str, fill=h_color, font=_get_font(16, bold=True))
    # Signature Move
    sig_move = hero_data.get("move", "Special Attack")
    draw.text((hero_card_x + 24, art_box_y + 88), f"» {sig_move[:24]}", fill=(180, 170, 210, 255), font=_get_font(12))

    # Hero Power Banner at bottom of Hero Card
    power_box_y = hero_card_y + 180
    base_power = hero_data.get("power", 500)
    bonus = hero_data.get("power_bonus", 0)
    total_power = base_power + bonus

    draw.rounded_rectangle(
        [(hero_card_x + 16, power_box_y), (hero_card_x + hero_card_w - 16, power_box_y + 44)],
        radius=8,
        fill=(32, 24, 52, 255),
        outline=h_color,
        width=1,
    )
    draw.text((hero_card_x + 28, power_box_y + 12), "COMBAT POWER", fill=(180, 170, 200, 255), font=font_badge)
    draw.text((hero_card_x + hero_card_w - 105, power_box_y + 10), f"⚡ {total_power}", fill=(255, 255, 255, 255), font=_get_font(17, bold=True))

    # Hero Card Footer Status
    draw.text((hero_card_x + 36, power_box_y + 60), "EQUIPPED MAIN FIGHTER", fill=(120, 110, 140, 255), font=_get_font(11, bold=True))

    # Bottom Legal / Branding
    draw.text((35, h - 30), "KYRO SHADOW ARENA • AUTHENTIC HUNTER DATABASE", fill=(90, 80, 115, 255), font=_get_font(10))

    # Save to buffer
    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out


def render_battle_clash(
    player1_name: str,
    player1_hero: dict[str, Any],
    player2_name: str,
    player2_hero: dict[str, Any],
    winner_num: int,  # 1 for p1, 2 for p2, 0 for tie
    p1_advantage: bool = False,
    p2_advantage: bool = False,
    chest_reward: str | None = None,
    gold_reward: int = 50,
) -> io.BytesIO:
    """
    Renders a dramatic 900x420 Anime Clash Card showing Player 1 vs Player 2/Boss.
    """
    w, h = 900, 420
    im = Image.new("RGBA", (w, h), (14, 11, 22, 255))
    draw = ImageDraw.Draw(im)

    # Ambient Glow
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([(-40, -40), (320, 320)], fill=(168, 85, 247, 45))
    gdraw.ellipse([(w - 320, -40), (w + 40, 320)], fill=(239, 68, 68, 45))
    im = Image.alpha_composite(im, glow)
    draw = ImageDraw.Draw(im)

    # Outer Border
    draw.rounded_rectangle([(8, 8), (w - 8, h - 8)], radius=20, outline=(55, 45, 75, 255), width=2)

    # Typography
    font_title = _get_font(22, bold=True)
    font_hero = _get_font(24, bold=True)
    font_sub = _get_font(14, bold=False)
    font_badge = _get_font(13, bold=True)
    font_vs = _get_font(38, bold=True)

    # Top Battle Banner
    draw.rounded_rectangle([(24, 16), (w - 24, 20)], radius=2, fill=(168, 85, 247))
    draw.text((w // 2 - 95, 28), "SHADOW DUEL ARENA", fill=(216, 180, 254, 255), font=_get_font(14, bold=True))

    # --- LEFT HERO CARD (Player 1) ---
    p1_x, p1_y, card_w, card_h = 35, 70, 360, 260
    p1_rarity = player1_hero.get("rarity", "Common")
    p1_color = RARITY_COLORS.get(p1_rarity, (156, 163, 175))
    p1_is_winner = winner_num == 1

    draw.rounded_rectangle(
        [(p1_x, p1_y), (p1_x + card_w, p1_y + card_h)],
        radius=16,
        fill=(22, 17, 34, 255),
        outline=p1_color if not p1_is_winner else (234, 179, 8),
        width=3 if p1_is_winner else 1,
    )

    # Player 1 Header
    draw.text((p1_x + 18, p1_y + 16), player1_name[:16], fill=(255, 255, 255, 255), font=font_title)
    draw.text((p1_x + 18, p1_y + 44), f"✦ {p1_rarity.upper()}", fill=p1_color, font=font_badge)

    # Hero Box Left
    draw.rounded_rectangle(
        [(p1_x + 18, p1_y + 70), (p1_x + card_w - 18, p1_y + 180)],
        radius=10,
        fill=(14, 11, 22, 255),
        outline=(50, 40, 70, 255),
    )
    p1_name = player1_hero.get("name", "Fighter")
    draw.text((p1_x + 28, p1_y + 82), p1_name[:18], fill=(255, 255, 255, 255), font=font_hero)
    p1_elem = player1_hero.get("element", "Shadow")
    draw.text((p1_x + 28, p1_y + 116), f"Element: {p1_elem}", fill=ELEMENT_DATA.get(p1_elem, {}).get("color", (200, 200, 200)), font=font_sub)
    p1_move = player1_hero.get("move", "Special Hit")
    draw.text((p1_x + 28, p1_y + 142), f"Move: {p1_move[:22]}", fill=(180, 170, 205, 255), font=_get_font(12))

    # Power Left
    p1_power = player1_hero.get("power", 500) + player1_hero.get("power_bonus", 0)
    p1_eff_power = int(p1_power * 1.08) if p1_advantage else p1_power
    draw.rounded_rectangle([(p1_x + 18, p1_y + 195), (p1_x + card_w - 18, p1_y + 240)], radius=8, fill=(35, 26, 52, 255))
    draw.text((p1_x + 28, p1_y + 208), "POWER LEVEL", fill=(170, 160, 195, 255), font=font_badge)
    draw.text((p1_x + card_w - 110, p1_y + 204), f"⚡ {p1_eff_power}", fill=(255, 255, 255, 255), font=_get_font(18, bold=True))
    if p1_advantage:
        draw.text((p1_x + 130, p1_y + 208), "[+8% ELEM ADV]", fill=(34, 197, 94), font=_get_font(11, bold=True))

    # --- RIGHT HERO CARD (Player 2 / Boss) ---
    p2_x = w - card_w - 35
    p2_y = p1_y
    p2_rarity = player2_hero.get("rarity", "Common")
    p2_color = RARITY_COLORS.get(p2_rarity, (156, 163, 175))
    p2_is_winner = winner_num == 2

    draw.rounded_rectangle(
        [(p2_x, p2_y), (p2_x + card_w, p2_y + card_h)],
        radius=16,
        fill=(22, 17, 34, 255),
        outline=p2_color if not p2_is_winner else (234, 179, 8),
        width=3 if p2_is_winner else 1,
    )

    # Player 2 Header
    draw.text((p2_x + 18, p2_y + 16), player2_name[:16], fill=(255, 255, 255, 255), font=font_title)
    draw.text((p2_x + 18, p2_y + 44), f"✦ {p2_rarity.upper()}", fill=p2_color, font=font_badge)

    # Hero Box Right
    draw.rounded_rectangle(
        [(p2_x + 18, p2_y + 70), (p2_x + card_w - 18, p2_y + 180)],
        radius=10,
        fill=(14, 11, 22, 255),
        outline=(50, 40, 70, 255),
    )
    p2_name = player2_hero.get("name", "Rival")
    draw.text((p2_x + 28, p2_y + 82), p2_name[:18], fill=(255, 255, 255, 255), font=font_hero)
    p2_elem = player2_hero.get("element", "Shadow")
    draw.text((p2_x + 28, p2_y + 116), f"Element: {p2_elem}", fill=ELEMENT_DATA.get(p2_elem, {}).get("color", (200, 200, 200)), font=font_sub)
    p2_move = player2_hero.get("move", "Special Hit")
    draw.text((p2_x + 28, p2_y + 142), f"Move: {p2_move[:22]}", fill=(180, 170, 205, 255), font=_get_font(12))

    # Power Right
    p2_power = player2_hero.get("power", 500) + player2_hero.get("power_bonus", 0)
    p2_eff_power = int(p2_power * 1.08) if p2_advantage else p2_power
    draw.rounded_rectangle([(p2_x + 18, p2_y + 195), (p2_x + card_w - 18, p2_y + 240)], radius=8, fill=(35, 26, 52, 255))
    draw.text((p2_x + 28, p2_y + 208), "POWER LEVEL", fill=(170, 160, 195, 255), font=font_badge)
    draw.text((p2_x + card_w - 110, p2_y + 204), f"⚡ {p2_eff_power}", fill=(255, 255, 255, 255), font=_get_font(18, bold=True))
    if p2_advantage:
        draw.text((p2_x + 130, p2_y + 208), "[+8% ELEM ADV]", fill=(34, 197, 94), font=_get_font(11, bold=True))

    # --- CENTER: VS EMBLEM ---
    vs_cx, vs_cy = w // 2, 190
    draw.ellipse([(vs_cx - 40, vs_cy - 40), (vs_cx + 40, vs_cy + 40)], fill=(28, 20, 44, 255), outline=(234, 179, 8), width=2)
    draw.text((vs_cx - 24, vs_cy - 24), "VS", fill=(255, 255, 255, 255), font=font_vs)

    # --- BOTTOM VICTORY / REWARD STRIP ---
    bottom_y = 345
    draw.rounded_rectangle([(35, bottom_y), (w - 35, bottom_y + 55)], radius=12, fill=(24, 18, 38, 255), outline=(70, 55, 95, 255), width=1)

    if winner_num == 1:
        win_msg = f"🏆 VICTORY: {player1_name.upper()} WINS! (+{gold_reward} Gold)"
        draw.text((55, bottom_y + 16), win_msg, fill=(234, 179, 8), font=_get_font(16, bold=True))
    elif winner_num == 2:
        win_msg = f"🏆 VICTORY: {player2_name.upper()} WINS! (+{gold_reward} Gold)"
        draw.text((55, bottom_y + 16), win_msg, fill=(239, 68, 68), font=_get_font(16, bold=True))
    else:
        draw.text((55, bottom_y + 16), "⚔️ STALEMATE: BOTH FIGHTERS TIED!", fill=(200, 200, 200), font=_get_font(16, bold=True))

    # If chest dropped, display on right side of bottom strip
    if chest_reward:
        c_text = f"🎁 {chest_reward.upper()} DROPPED!"
        c_color = (234, 179, 8) if "Monarch" in chest_reward else ((168, 85, 247) if "Shadow" in chest_reward else (56, 189, 248))
        draw.text((w - 320, bottom_y + 16), c_text, fill=c_color, font=_get_font(15, bold=True))

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
    Renders an exhilarating 840x380 Chest Opening & Hero Unlock Card.
    """
    w, h = 840, 380
    rarity = unlocked_hero.get("rarity", "Common")
    r_color = RARITY_COLORS.get(rarity, (156, 163, 175))

    im = Image.new("RGBA", (w, h), (12, 10, 20, 255))
    draw = ImageDraw.Draw(im)

    # Radiant Glow from Chest Center
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([(120, -50), (w - 120, h + 50)], fill=(r_color[0], r_color[1], r_color[2], 55))
    im = Image.alpha_composite(im, glow)
    draw = ImageDraw.Draw(im)

    # Frame
    draw.rounded_rectangle([(8, 8), (w - 8, h - 8)], radius=20, outline=r_color, width=2)

    # Top Announcement
    draw.rounded_rectangle([(24, 16), (w - 24, 20)], radius=2, fill=r_color)
    draw.text((40, 28), f"CHEST UNBOXING • {chest_type.upper()}", fill=(200, 190, 225, 255), font=_get_font(13, bold=True))
    draw.text((w - 240, 28), f"OPENED BY @{user_name[:16]}", fill=(180, 170, 205, 255), font=_get_font(13))

    # --- LEFT SIDE: THE CHEST DISPLAY ---
    cx, cy, cw, ch = 40, 65, 300, 280
    draw.rounded_rectangle([(cx, cy), (cx + cw, cy + ch)], radius=16, fill=(20, 16, 32, 255), outline=(50, 40, 70, 255))

    # Chest Icon / Graphic
    draw.ellipse([(cx + 60, cy + 30), (cx + cw - 60, cy + 150)], fill=(32, 24, 50, 255), outline=r_color, width=2)
    draw.text((cx + 90, cy + 68), "BOX", fill=(255, 255, 255, 255), font=_get_font(32, bold=True))

    draw.text((cx + 55, cy + 175), f"{chest_type.upper()}", fill=(255, 255, 255, 255), font=_get_font(16, bold=True))
    draw.text((cx + 70, cy + 205), f"Loot: +{gold_reward} Gold", fill=(234, 179, 8), font=_get_font(13, bold=True))
    status_msg = "⭐ STAR POWER UP!" if is_duplicate else "🎉 NEW CHARACTER!"
    status_col = (234, 179, 8) if is_duplicate else (34, 197, 94)
    draw.text((cx + 60, cy + 235), status_msg, fill=status_col, font=_get_font(13, bold=True))

    # --- RIGHT SIDE: THE HERO REVEAL CARD ---
    hx, hy, hw, hh = 365, 65, 435, 280
    draw.rounded_rectangle([(hx, hy), (hx + hw, hy + hh)], radius=16, fill=(24, 18, 38, 255), outline=r_color, width=2)

    # Rarity Header
    draw.rounded_rectangle([(hx + 16, hy + 16), (hx + hw - 16, hy + 46)], radius=8, fill=(35, 26, 52, 255))
    draw.text((hx + 28, hy + 22), f"✦ {rarity.upper()} FIGHTER REVEALED", fill=r_color, font=_get_font(13, bold=True))
    elem = unlocked_hero.get("element", "Shadow")
    draw.text((hx + hw - 120, hy + 22), f"[{elem.upper()}]", fill=ELEMENT_DATA.get(elem, {}).get("color", (255, 255, 255)), font=_get_font(13, bold=True))

    # Hero Details
    h_name = unlocked_hero.get("name", "Anime Hero")
    draw.text((hx + 28, hy + 64), h_name[:22], fill=(255, 255, 255, 255), font=_get_font(26, bold=True))

    stars_count = unlocked_hero.get("stars", 1)
    draw.text((hx + 28, hy + 104), "★ " * stars_count, fill=r_color, font=_get_font(18, bold=True))

    sig_move = unlocked_hero.get("move", "Special Attack")
    draw.text((hx + 28, hy + 138), f"Signature Move: {sig_move}", fill=(200, 190, 225, 255), font=_get_font(14))

    # Power Level Box
    power = unlocked_hero.get("power", 500)
    bonus = unlocked_hero.get("power_bonus", 0)
    draw.rounded_rectangle([(hx + 20, hy + 180), (hx + hw - 20, hy + 235)], radius=10, fill=(15, 12, 24, 255), outline=r_color, width=1)
    draw.text((hx + 35, hy + 196), "TOTAL COMBAT POWER", fill=(170, 160, 195, 255), font=_get_font(13, bold=True))
    draw.text((hx + hw - 130, hy + 190), f"⚡ {power + bonus}", fill=(255, 255, 255, 255), font=_get_font(22, bold=True))

    if is_duplicate:
        draw.text((hx + 30, hy + 250), "Duplicate hero converted to +50 permanent power upgrade!", fill=(234, 179, 8), font=_get_font(11))
    else:
        draw.text((hx + 30, hy + 250), "Hero successfully unlocked & added to your battle deck!", fill=(34, 197, 94), font=_get_font(11))

    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out
