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
from src.utils.logger import setup_logger

logger = setup_logger("Cicada")


async def run_bot_loop() -> None:
    """Run bot with smart exponential backoff for Cloudflare / Discord 429 rate limits."""
    try:
        Config.validate()
    except ValueError as e:
        logger.critical(f"Configuration error: {e}")
        return

    delay = 15.0

    while True:
        try:
            bot = CicadaBot()
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


async def main() -> None:
    """Launch resilient bot loop."""
    await run_bot_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot execution interrupted by user.")
