"""
Cicada 3301 Discord Bot - Main Entry Point
Production Cloud Engine with 24/7 Web Server and Resilient Rate-Limit Backoff.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import discord
from src.core.bot import CicadaBot
from src.core.config import Config
from src.core.server import HealthServer
from src.utils.logger import setup_logger

logger = setup_logger("Cicada")

active_bot: CicadaBot | None = None


def get_current_bot() -> CicadaBot | None:
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
            bot = CicadaBot()
            active_bot = bot
            logger.info(f"Connecting {Config.BOT_NAME} in [{Config.ENVIRONMENT.upper()}] mode to Discord Gateway...")
            async with bot:
                await bot.start(Config.TOKEN)
            delay = 15.0
            await asyncio.sleep(5)
        except discord.HTTPException as e:
            if e.status == 429:
                logger.warning(f"Discord 429 Rate Limit encountered. Cooling down for {delay:.0f}s before retrying...")
                await asyncio.sleep(delay)
                delay = min(delay * 2.0, 300.0)
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
    server = HealthServer(bot=None)  # type: ignore
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
