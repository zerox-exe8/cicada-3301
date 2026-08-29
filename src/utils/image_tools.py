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
    - 'seamless' (default): Automatically covers 100% of the 1000x300 canvas with the original background,
      keeping centered text/graphics large and crisp with NO frames, NO borders, and NO dark boxes around it.
    """
    if not HAS_PIL:
        return io.BytesIO(image_bytes)

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    orig_w, orig_h = img.size

    # Smart scale & fill: Scale so that image completely covers the 1000x300 canvas
    scale = max(target_width / orig_w, target_height / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)

    scaled = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Center crop to exact 1000x300
    left = (new_w - target_width) // 2
    top = (new_h - target_height) // 2

    result = scaled.crop((left, top, left + target_width, top + target_height))

    output = io.BytesIO()
    result.save(output, format="PNG", optimize=True)
    output.seek(0)
    return output
