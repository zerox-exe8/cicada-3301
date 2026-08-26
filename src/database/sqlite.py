"""
Cicada 3301 Discord Bot - Local SQLite Database Driver
High-performance asynchronous local SQLite database connector using aiosqlite.
Provides automatic fallback when Supabase / PostgreSQL cloud connection is not configured.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
import aiosqlite

from src.database.base import BaseDatabase

logger = logging.getLogger("Cicada.Database.SQLite")


class SqliteDatabase(BaseDatabase):
    """Local SQLite async database connector."""

    def __init__(self, db_path: str = "data/cicada.db") -> None:
        self.db_path = db_path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Create a local SQLite database connection."""
        try:
            path = Path(self.db_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.conn = await aiosqlite.connect(self.db_path)
            self.conn.row_factory = aiosqlite.Row
            logger.info(f"Connected to local SQLite database: {self.db_path}")
            await self.initialize_tables()
        except Exception as e:
            logger.critical(f"Failed to connect to local SQLite database: {e}", exc_info=e)
            raise

    async def close(self) -> None:
        """Close SQLite database connection."""
        if self.conn:
            await self.conn.close()
            logger.info("SQLite database connection closed.")

    async def initialize_tables(self) -> None:
        """Initialize SQLite tables matching bot schemas."""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT DEFAULT '?',
                language TEXT DEFAULT 'en',
                log_channel_id INTEGER,
                mod_role_id INTEGER,
                disabled_commands TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS system_developers (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS system_blacklists (
                target_id INTEGER PRIMARY KEY,
                target_type TEXT DEFAULT 'user',
                reason TEXT DEFAULT 'Violation of bot rules',
                added_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id INTEGER,
                guild_id INTEGER,
                balance INTEGER DEFAULT 0,
                bank INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, guild_id)
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS guild_logs (
                guild_id INTEGER PRIMARY KEY,
                all_channel_id INTEGER,
                mod_channel_id INTEGER,
                message_channel_id INTEGER,
                member_channel_id INTEGER,
                server_channel_id INTEGER,
                voice_channel_id INTEGER
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS premium_keys (
                key TEXT PRIMARY KEY,
                duration_days INTEGER NOT NULL,
                target_type TEXT DEFAULT 'guild',
                created_by INTEGER NOT NULL,
                is_used INTEGER DEFAULT 0,
                redeemed_by INTEGER,
                redeemed_target_id INTEGER,
                redeemed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS guild_premium (
                guild_id INTEGER PRIMARY KEY,
                tier TEXT DEFAULT 'pro',
                activated_by INTEGER,
                key_used TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS user_premium (
                user_id INTEGER PRIMARY KEY,
                tier TEXT DEFAULT 'pro',
                key_used TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS premium_customers (
                target_id INTEGER PRIMARY KEY,
                target_type TEXT DEFAULT 'user',
                total_redemptions INTEGER DEFAULT 1,
                total_days_purchased INTEGER DEFAULT 0,
                first_redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS payment_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                razorpay_order_id TEXT,
                razorpay_payment_id TEXT UNIQUE,
                razorpay_payment_link_id TEXT,
                discord_user_id INTEGER NOT NULL,
                guild_id INTEGER,
                target_type TEXT NOT NULL,
                duration_days INTEGER NOT NULL,
                plan_tier TEXT DEFAULT 'pro',
                amount_smallest_unit INTEGER NOT NULL,
                currency TEXT DEFAULT 'INR',
                status TEXT DEFAULT 'created',
                is_trial INTEGER DEFAULT 0,
                last_reminder_sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP
            );
            """,
        ]

        for query in queries:
            await self.execute(query)

        logger.info("Initialized local SQLite schemas successfully.")

    async def execute(self, query: str, *args: Any) -> None:
        """Execute query on SQLite database."""
        if not self.conn:
            raise RuntimeError("Database is not connected. Call connect() first.")
        # Replace $1, $2 with ? for SQLite compatibility if needed
        import re
        sqlite_query = re.sub(r"\$\d+", "?", query)
        async with self.conn.cursor() as cursor:
            await cursor.execute(sqlite_query, args)
        await self.conn.commit()

    async def fetch_one(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Fetch single record as dictionary."""
        if not self.conn:
            raise RuntimeError("Database is not connected. Call connect() first.")
        import re
        sqlite_query = re.sub(r"\$\d+", "?", query)
        async with self.conn.cursor() as cursor:
            await cursor.execute(sqlite_query, args)
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def fetch_all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Fetch all records as list of dictionaries."""
        if not self.conn:
            raise RuntimeError("Database is not connected. Call connect() first.")
        import re
        sqlite_query = re.sub(r"\$\d+", "?", query)
        async with self.conn.cursor() as cursor:
            await cursor.execute(sqlite_query, args)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
