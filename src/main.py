"""
Kyro Discord Bot - Main Entry Point
Production Cloud Engine with 24/7 Web Server and Resilient Rate-Limit Backoff.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Ensure static FFmpeg binaries are registered on PATH
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass

import discord
import discord.opus
from src.core.bot import KyroBot
from src.core.config import Config
from src.core.server import HealthServer
from src.utils.logger import setup_logger

logger = setup_logger("Kyro")

# Ensure Opus library is loaded across Windows, Linux, and Cloud Hosting
if not discord.opus.is_loaded():
    import ctypes.util
    opus_lib = ctypes.util.find_library("opus")
    if opus_lib:
        try:
            discord.opus.load_opus(opus_lib)
            logger.info(f"Loaded Opus library from system: {opus_lib}")
        except Exception:
            pass

    if not discord.opus.is_loaded():
        for lib_name in ["libopus.so.0", "libopus.so", "opus.dll", "libopus-0.dll", "libopus.dll"]:
            dll_path = BASE_DIR / lib_name
            target = str(dll_path) if dll_path.exists() else lib_name
            try:
                discord.opus.load_opus(target)
                logger.info(f"Loaded Opus library from: {target}")
                break
            except Exception as e:
                logger.debug(f"Notice loading {lib_name}: {e}")

active_bot: KyroBot | None = None


def get_current_bot() -> KyroBot | None:
    return active_bot


async def run_bot_loop() -> None:
    """Run bot with smart exponential backoff for Cloudflare / Discord 429 rate limits."""
    global active_bot

    try:
        Config.validate()
    except ValueError as e:
        logger.critical(f"Configuration error: {e}")
        return

    delay = 15.0

    while True:
        try:
            bot = KyroBot()
            active_bot = bot
            logger.info(f"Connecting {Config.BOT_NAME} in [{Config.ENVIRONMENT.upper()}] mode to Discord Gateway...")
            async with bot:
                await bot.start(Config.TOKEN)
            delay = 15.0
            await asyncio.sleep(5)
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", None)
                response_text = getattr(e, "text", str(e))
                if retry_after is None and hasattr(e, "response") and e.response is not None:
                    retry_header = getattr(e.response, "headers", {}).get("Retry-After")
                    if retry_header:
                        try:
                            retry_after = float(retry_header)
                        except ValueError:
                            pass
                wait_time = max(retry_after if retry_after else delay, 45.0)
                logger.warning(
                    f"Discord Gateway Rate Limit (429) active: {response_text}. "
                    f"Cooling down for {wait_time:.0f}s before reconnecting to allow Discord rate-limit window to reset..."
                )
                await asyncio.sleep(wait_time)
                delay = min(max(delay * 2.0, wait_time), 300.0)
            else:
                logger.error(f"Discord HTTP Exception ({e.status}): {e}. Retrying in 15s...")
                await asyncio.sleep(15)
        except discord.LoginFailure as e:
            logger.critical(f"FATAL: Discord Login Failure (Invalid Token): {e}")
            break
        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info("Bot execution cancelled.")
            break
        except Exception as e:
            logger.error(f"Connection glitch: {e}. Retrying in 10s...", exc_info=e)
            await asyncio.sleep(10)
        finally:
            active_bot = None


async def main() -> None:
    """Launch 24/7 Web Server and resilient bot loop."""
    # 1. Start Web Server first so Render Port Scan passes immediately (<1s)
    server = HealthServer(bot_getter=get_current_bot)
    await server.start()

    # 2. Run bot loop
    try:
        await run_bot_loop()
    finally:
        await server.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot execution interrupted by user.")
