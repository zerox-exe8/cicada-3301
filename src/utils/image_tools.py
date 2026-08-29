"""
Cicada 3301 Discord Bot - Image Processing & Slim Banner Tools
Converts tall / oversized images into slim, widescreen Discord header banners using transparent canvas fitting or smart cropping.
"""

from __future__ import annotations

import io
import aiohttp

try:
    from PIL import Image, ImageFilter, ImageEnhance, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


async def download_image_bytes(url: str, session: aiohttp.ClientSession) -> bytes | None:
    """Download image bytes safely from URL."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception:
        pass
    return None


def create_slim_banner(
    image_bytes: bytes,
    target_width: int = 1000,
    target_height: int = 300,
    mode: str = "studio",
) -> io.BytesIO:
    """
    Transform image into an automated Canva-grade widescreen Discord header banner (1000x300px).
    - 'studio' (default): Automatically creates a luxury dark ambient blurred backdrop with depth shadow,
      and places 100% of the crisp original image centered with ZERO squish, ZERO distortion, and ZERO cuts.
    - 'cover': Edge-to-edge crop.
    - 'compress': Direct scale.
    """
    if not HAS_PIL:
        return io.BytesIO(image_bytes)

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    orig_w, orig_h = img.size

    if mode == "cover":
        ratio = target_width / target_height
        img_ratio = orig_w / orig_h
        if img_ratio > ratio:
            new_w = int(orig_h * ratio)
            left = (orig_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, orig_h))
        else:
            new_h = int(orig_w / ratio)
            top = (orig_h - new_h) // 2
            img = img.crop((0, top, orig_w, top + new_h))
        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    elif mode == "compress":
        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    else:
        # Default 'studio' mode: Automated Canva-grade ambient backdrop with depth & crisp original
        # 1. Base ambient backdrop: heavily blurred + darkened for high-end look
        bg = img.resize((target_width, target_height), Image.Resampling.BILINEAR)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=35))
        enhancer = ImageEnhance.Brightness(bg)
        bg = enhancer.enhance(0.40)  # Rich dark ambient lighting

        # 2. Subtle top vignette
        overlay = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for y in range(target_height):
            alpha = int(50 * (1.0 - (y / target_height)))
            draw.line([(0, y), (target_width, y)], fill=(0, 0, 0, alpha))
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay)

        # 3. Fit original artwork crisply in the center with 0 distortion
        padding_y = 16
        padding_x = 24
        max_w = target_width - (padding_x * 2)
        max_h = target_height - (padding_y * 2)
        scale = min(max_w / orig_w, max_h / orig_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)

        crisp = img.resize((new_w, new_h), Image.Resampling.LANCZOS).convert("RGBA")

        # 4. Soft depth shadow behind the artwork
        shadow = Image.new("RGBA", (new_w + 30, new_h + 30), (0, 0, 0, 0))
        s_draw = ImageDraw.Draw(shadow)
        s_draw.rectangle([(15, 15), (new_w + 15, new_h + 15)], fill=(0, 0, 0, 160))
        shadow = shadow.filter(ImageFilter.GaussianBlur(radius=14))

        offset_x = (target_width - new_w) // 2
        offset_y = (target_height - new_h) // 2

        bg.paste(shadow, (offset_x - 15, offset_y - 15), shadow)
        bg.paste(crisp, (offset_x, offset_y), crisp)
        img = bg

    output = io.BytesIO()
    img.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output
