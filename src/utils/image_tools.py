"""
Cicada 3301 Discord Bot - Image Processing & Slim Banner Tools
Converts tall / oversized images into slim, widescreen Discord header banners using transparent canvas fitting or smart cropping.
"""

from __future__ import annotations

import io
import aiohttp

try:
    from PIL import Image
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
    target_height: int = 280,
    mode: str = "cover",
) -> io.BytesIO:
    """
    Transform image into a full-bleed widescreen Discord header banner (1000x280px).
    - 'cover' (default): Stretches image to 100% full width with 0 empty margins on left/right.
    - 'contain': Fits the image centered inside a transparent canvas.
    """
    if not HAS_PIL:
        return io.BytesIO(image_bytes)

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    if mode == "contain":
        canvas = Image.new("RGBA", (target_width, target_height), (0, 0, 0, 0))
        img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
        offset_x = (target_width - img.width) // 2
        offset_y = (target_height - img.height) // 2
        canvas.paste(img, (offset_x, offset_y), img)

        output = io.BytesIO()
        canvas.save(output, format="PNG", optimize=True)
        output.seek(0)
        return output
    else:
        # Full-width edge-to-edge cover mode (fills the entire 1000px width with 0 side padding)
        ratio = target_width / target_height
        img_ratio = img.width / img.height
        if img_ratio > ratio:
            new_w = int(img.height * ratio)
            left = (img.width - new_w) // 2
            img = img.crop((left, 0, left + new_w, img.height))
        else:
            new_h = int(img.width / ratio)
            top = (img.height - new_h) // 2
            img = img.crop((0, top, img.width, top + new_h))

        img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        img.save(output, format="PNG", optimize=True)
        output.seek(0)
        return output
