"""
Hertz Discord Bot - Configuration Module
Loads and validates environment variables and provides theme colors and emojis.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


@dataclass(frozen=True)
class ThemeColors:
    """Standardized color palette for premium embeds."""
    PRIMARY: int = 0x5865F2      # Discord Blurple
    SUCCESS: int = 0x2ECC71      # Mint Green
    ERROR: int = 0xED4245        # Crimson Coral
    WARNING: int = 0xFEE75C      # Amber Gold
    INFO: int = 0x3498DB         # Deep Sky Blue
    DARK: int = 0x2B2D31         # Midnight Velvet
    SECONDARY: int = 0x7289DA    # Soft Indigo


@dataclass(frozen=True)
class ThemeEmojis:
    """Standardized system emojis for embeds and messages."""
    SUCCESS: str = "✅"
    ERROR: str = "❌"
    WARNING: str = "⚠️"
    INFO: str = "ℹ️"
    LOADING: str = "⏳"
    SHIELD: str = "🛡️"
    SPARKLES: str = "✨"
    SETTINGS: str = "⚙️"
    PING: str = "🏓"
    DATABASE: str = "🗄️"
    BOT: str = "🤖"


class Config:
    """Bot global configuration."""
    
    # Discord Bot Token
    TOKEN: str = (
        os.getenv("DISCORD_TOKEN")
        or os.getenv("BOT_TOKEN")
        or os.getenv("TOKEN")
        or ""
    ).strip()
    CLIENT_ID: int = int(os.getenv("CLIENT_ID", "0"))
    
    # Prefixes
    DEFAULT_PREFIX: str = os.getenv("BOT_PREFIX", "?")
    
    # Environment & Dev Settings
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development").lower()
    DEV_GUILD_ID: int | None = (
        int(os.getenv("DEV_GUILD_ID")) if os.getenv("DEV_GUILD_ID") else None
    )
    
    # PostgreSQL / Supabase Database Settings
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

    # Razorpay Payment Gateway Settings
    RAZORPAY_KEY_ID: str = os.getenv("RAZORPAY_KEY_ID", "").strip()
    RAZORPAY_KEY_SECRET: str = os.getenv("RAZORPAY_KEY_SECRET", "").strip()
    RAZORPAY_WEBHOOK_SECRET: str = os.getenv("RAZORPAY_WEBHOOK_SECRET", "").strip()
    
    # Aesthetics
    COLORS: ThemeColors = ThemeColors()
    EMOJIS: ThemeEmojis = ThemeEmojis()
    
    # Bot Branding
    BOT_NAME: str = "Hertz"
    FOOTER_TEXT: str = "⚡ Hertz Core System"

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration values."""
        if not cls.TOKEN:
            raise ValueError(
                "DISCORD_TOKEN is missing! Please set your bot token in the .env file."
            )
        if not cls.DATABASE_URL:
            raise ValueError(
                "DATABASE_URL is missing! Please set your Supabase connection string in the .env file."
            )
