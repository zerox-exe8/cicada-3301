"""
Kyro Discord Bot - Dynamic Real-Time Canvas Rendering Pipeline
Renders high-resolution, anti-aliased dynamic graphic cards (Profile/Rank cards, Audio Waveforms)
directly in memory using Pillow C-extensions with zero external API dependencies.
"""

from __future__ import annotations

import io
import math
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import discord


def render_profile_card(
    avatar_bytes: bytes | None,
    username: str,
    display_name: str,
    standing: str,
    tier: str,
    playlists_count: int,
    is_owner: bool = False,
    is_dev: bool = False,
) -> io.BytesIO | None:
    """
    Render a high-resolution dark mode Kyro Passport / Identity Card (800x240px).
    """
    if not HAS_PIL:
        return None

    w, h = 800, 240
    # Create base dark slate canvas
    im = Image.new("RGBA", (w, h), (14, 17, 23, 255))
    draw = ImageDraw.Draw(im)

    # 1. Subtle Background Accents & Glass Glow
    # Accent color: Violet/Cyan gradient accent
    accent_rgb = (147, 51, 234) if is_owner else ((59, 130, 246) if is_dev else (99, 102, 241))
    
    # Outer rounded border
    draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=18, outline=(40, 46, 58, 255), width=2)
    # Top accent line
    draw.rounded_rectangle([(18, 12), (w - 18, 14)], radius=2, fill=accent_rgb)

    # 2. Avatar rendering (Anti-aliased circle with outer glow ring)
    avatar_size = 120
    av_x, av_y = 30, 45

    # Draw avatar outer ring
    draw.ellipse([(av_x - 4, av_y - 4), (av_x + avatar_size + 4, av_y + avatar_size + 4)], outline=accent_rgb, width=3)

    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av = av.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)

            # Circular mask with anti-aliasing
            mask = Image.new("L", (avatar_size * 4, avatar_size * 4), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([(0, 0), (avatar_size * 4, avatar_size * 4)], fill=255)
            mask = mask.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)

            im.paste(av, (av_x, av_y), mask)
        except Exception:
            # Fallback circle
            draw.ellipse([(av_x, av_y), (av_x + avatar_size, av_y + avatar_size)], fill=(30, 35, 45, 255))
    else:
        draw.ellipse([(av_x, av_y), (av_x + avatar_size, av_y + avatar_size)], fill=(30, 35, 45, 255))

    # 3. Typography & Info Placement
    # Text positioning
    text_x = av_x + avatar_size + 30
    curr_y = 45

    # Fonts: Use default or clean bitmap font
    try:
        font_title = ImageFont.truetype("arial.ttf", 26)
        font_sub = ImageFont.truetype("arial.ttf", 16)
        font_badge = ImageFont.truetype("arial.ttf", 13)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_badge = ImageFont.load_default()

    # Display Name
    display_clean = display_name[:20]
    draw.text((text_x, curr_y), display_clean, fill=(255, 255, 255, 255), font=font_title)

    # Username tag
    user_tag = f"@{username[:22]}"
    draw.text((text_x, curr_y + 32), user_tag, fill=(148, 163, 184, 255), font=font_sub)

    # Badges
    badge_x = text_x
    badge_y = curr_y + 60

    # Standing badge
    badge_w = 110
    draw.rounded_rectangle([(badge_x, badge_y), (badge_x + badge_w, badge_y + 24)], radius=6, fill=(30, 41, 59, 255), outline=accent_rgb, width=1)
    draw.text((badge_x + 10, badge_y + 4), standing[:14], fill=(241, 245, 249, 255), font=font_badge)

    # Tier badge
    badge_x2 = badge_x + badge_w + 12
    badge_w2 = 120
    draw.rounded_rectangle([(badge_x2, badge_y), (badge_x2 + badge_w2, badge_y + 24)], radius=6, fill=(24, 24, 27, 255), outline=(71, 85, 105, 255), width=1)
    draw.text((badge_x2 + 10, badge_y + 4), f"Tier: {tier[:10]}", fill=(203, 213, 225, 255), font=font_badge)

    # Playlists counter
    badge_x3 = badge_x2 + badge_w2 + 12
    badge_w3 = 110
    draw.rounded_rectangle([(badge_x3, badge_y), (badge_x3 + badge_w3, badge_y + 24)], radius=6, fill=(24, 24, 27, 255), outline=(71, 85, 105, 255), width=1)
    draw.text((badge_x3 + 10, badge_y + 4), f"Playlists: {playlists_count}", fill=(203, 213, 225, 255), font=font_badge)

    # 4. Bottom Activity Bar (Simulated Dynamic Energy/Progress Bar)
    bar_x = text_x
    bar_y = 175
    bar_w = w - text_x - 35
    bar_h = 8

    # Background bar
    draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)], radius=4, fill=(30, 41, 59, 255))
    # Filled bar (75% width with gradient)
    fill_w = int(bar_w * 0.85)
    draw.rounded_rectangle([(bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h)], radius=4, fill=accent_rgb)

    # Bottom footer text
    footer_text = "Kyro Network Passport • High-Fidelity Ecosystem Active"
    draw.text((bar_x, bar_y + 16), footer_text, fill=(100, 116, 139, 255), font=font_badge)

    # Output buffer
    out = io.BytesIO()
    im.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out
