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
    mode: str = "seamless",
) -> io.BytesIO:
    """
    Transform image into a seamless, edge-to-edge widescreen Discord header banner (1000x300px).
    - Ensures all text/graphics fit comfortably with safe vertical padding so NO letters/headers are cut.
    - Seamlessly extends the image's own matching background color across the full 1000px width.
    - 0% text cuts, 0% squishing, 0% dark frames.
    """
    if not HAS_PIL:
        return io.BytesIO(image_bytes)

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    orig_w, orig_h = img.size

    # 1. Background: Stretch image to 1000x300 and apply a gentle blur so the exact background color/hue matches
    bg = img.resize((target_width, target_height), Image.Resampling.BILINEAR).convert("RGBA")
    bg = bg.filter(ImageFilter.GaussianBlur(radius=16))

    # 2. Crisp artwork: Scale to fit inside target_height with safe vertical padding (265px)
    safe_h = max(100, target_height - 30)
    scale = safe_h / orig_h
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)

    if new_w > target_width - 32:
        scale = (target_width - 32) / orig_w
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)

    crisp_art = img.resize((new_w, new_h), Image.Resampling.LANCZOS).convert("RGBA")

    # 3. Apply soft horizontal feathering to melt center card smoothly into background
    feather_w = min(40, new_w // 8)
    if feather_w > 5:
        mask = Image.new("L", (new_w, new_h), 255)
        m_draw = ImageDraw.Draw(mask)
        for x in range(feather_w):
            alpha = int(255 * (x / feather_w))
            m_draw.line([(x, 0), (x, new_h)], fill=alpha)
            m_draw.line([(new_w - 1 - x, 0), (new_w - 1 - x, new_h)], fill=alpha)
        crisp_art.putalpha(mask)

    # 4. Paste the crisp artwork in the center
    offset_x = (target_width - new_w) // 2
    offset_y = (target_height - new_h) // 2

    bg.paste(crisp_art, (offset_x, offset_y), crisp_art)

    output = io.BytesIO()
    bg.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output
