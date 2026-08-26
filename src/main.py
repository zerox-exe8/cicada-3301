"""
Hertz Discord Bot - Main Entry Point
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.bot import HertzBot
from src.core.config import Config
from src.utils.logger import setup_logger

logger = setup_logger("Hertz")


async def main() -> None:
    """Validate configs and launch Hertz Bot."""
    try:
        Config.validate()
    except ValueError as e:
        logger.critical(f"Configuration error: {e}")
        return

    bot = HertzBot()
    async with bot:
        logger.info(f"Starting {Config.BOT_NAME} in [{Config.ENVIRONMENT.upper()}] mode...")
        await bot.start(Config.TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot execution interrupted by user.")
