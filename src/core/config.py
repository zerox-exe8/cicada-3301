"""
Kyro Discord Bot - Configuration Module
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
    """Standardized color palette for Kyro cryptographic cyber theme."""
    PRIMARY: int = 0x00FF66      # Kyro Titanium Neon Green
    SUCCESS: int = 0x00E676      # Neon Emerald
    ERROR: int = 0xFF3366        # Laser Crimson
    WARNING: int = 0xFFB300      # Cyber Amber
    INFO: int = 0x00E5FF         # Electric Cyan
    DARK: int = 0x0A0E14         # Deep Cyber Void
    SECONDARY: int = 0x10B981    # Dark Matrix Green
    ACCENT: int = 0x76FF03       # Bright Lime


@dataclass(frozen=True)
class ThemeEmojis:
    """Standardized system emojis for Kyro embeds."""
    SUCCESS: str = ""
    ERROR: str = ""
    WARNING: str = ""
    INFO: str = ""
    LOADING: str = ""
    SHIELD: str = ""
    SPARKLES: str = ""
    SETTINGS: str = ""
    PING: str = ""
    DATABASE: str = ""
    BOT: str = ""
    KYRO: str = ""


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
    
    # Prefixes & Identity
    BOT_NAME: str = os.getenv("BOT_NAME", "Kyro")
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
    
    # Lavalink / Audio Settings
    LAVALINK_URI: str = os.getenv("LAVALINK_URI", "http://fi15.bot-hosting.net:26267").strip()
    LAVALINK_PASSWORD: str = os.getenv("LAVALINK_PASSWORD", "NfJXUsGSO4tVI1LDl7v3XPYZ").strip()

    # Aesthetics
    COLORS: ThemeColors = ThemeColors()
    EMOJIS: ThemeEmojis = ThemeEmojis()
    
    # Bot Branding
    BOT_NAME: str = "Kyro"
    FOOTER_TEXT: str = "◈ KYRO • Autonomous Studio System"

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

