"""
Cicada 3301 Discord Bot - PostgreSQL / Supabase Database Driver
High-performance asynchronous PostgreSQL database connector using asyncpg connection pool.
"""

from __future__ import annotations

import logging
from typing import Any
import asyncpg

from src.database.base import BaseDatabase

logger = logging.getLogger("Cicada.Database.Postgres")


class PostgresDatabase(BaseDatabase):
    """PostgreSQL / Supabase async database connector."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create an asynchronous PostgreSQL connection pool."""
        try:
            # Strip extra driver prefixes if present
            clean_dsn = self.dsn.replace("postgresql+asyncpg://", "postgresql://")
            self.pool = await asyncpg.create_pool(
                clean_dsn,
                min_size=2,
                max_size=10,
                command_timeout=30,
                statement_cache_size=0,
            )
            logger.info("Connected to PostgreSQL / Supabase cloud database pool.")
            await self.initialize_tables()
        except Exception as e:
            logger.critical(f"Failed to connect to PostgreSQL / Supabase: {e}", exc_info=e)
            raise

    async def close(self) -> None:
        """Close connection pool gracefully."""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL database connection pool closed.")

    async def initialize_tables(self) -> None:
        """Initialize PostgreSQL schemas for Cicada 3301 modules."""
        queries = [
            # Guild settings table
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                prefix VARCHAR(10) DEFAULT '?',
                language VARCHAR(10) DEFAULT 'en',
                log_channel_id BIGINT,
                mod_role_id BIGINT,
                disabled_commands TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # System developers table
            """
            CREATE TABLE IF NOT EXISTS system_developers (
                user_id BIGINT PRIMARY KEY,
                added_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # System global blacklists table
            """
            CREATE TABLE IF NOT EXISTS system_blacklists (
                target_id BIGINT PRIMARY KEY,
                target_type VARCHAR(20) DEFAULT 'user',
                reason TEXT DEFAULT 'Violation of bot rules',
                added_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # System global state table
            """
            CREATE TABLE IF NOT EXISTS system_state (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT
            );
            """,
            # User profiles / Economy table
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id BIGINT,
                guild_id BIGINT,
                balance BIGINT DEFAULT 0,
                bank BIGINT DEFAULT 0,
                xp BIGINT DEFAULT 0,
                level INT DEFAULT 1,
                PRIMARY KEY (user_id, guild_id)
            );
            """,
            # Server modular audit logging channels
            """
            CREATE TABLE IF NOT EXISTS guild_logs (
                guild_id BIGINT PRIMARY KEY,
                all_channel_id BIGINT,
                mod_channel_id BIGINT,
                message_channel_id BIGINT,
                member_channel_id BIGINT,
                server_channel_id BIGINT,
                voice_channel_id BIGINT
            );
            """,
            # Premium License Keys table
            """
            CREATE TABLE IF NOT EXISTS premium_keys (
                key VARCHAR(64) PRIMARY KEY,
                duration_days INT NOT NULL,
                target_type VARCHAR(20) DEFAULT 'guild',
                created_by BIGINT NOT NULL,
                is_used BOOLEAN DEFAULT FALSE,
                redeemed_by BIGINT,
                redeemed_target_id BIGINT,
                redeemed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Active Guild/Server Premium table
            """
            CREATE TABLE IF NOT EXISTS guild_premium (
                guild_id BIGINT PRIMARY KEY,
                tier VARCHAR(50) DEFAULT 'pro',
                activated_by BIGINT,
                key_used VARCHAR(64),
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Active User/Personal Premium table
            """
            CREATE TABLE IF NOT EXISTS user_premium (
                user_id BIGINT PRIMARY KEY,
                tier VARCHAR(50) DEFAULT 'pro',
                key_used VARCHAR(64),
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Customer Lifetime Analytics & Repeat Buyers table
            """
            CREATE TABLE IF NOT EXISTS premium_customers (
                target_id BIGINT PRIMARY KEY,
                target_type VARCHAR(20) DEFAULT 'user',
                total_redemptions INT DEFAULT 1,
                total_days_purchased INT DEFAULT 0,
                first_redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            # Automated Payment Transactions & Webhooks table
            """
            CREATE TABLE IF NOT EXISTS payment_transactions (
                id SERIAL PRIMARY KEY,
                razorpay_order_id VARCHAR(64),
                razorpay_payment_id VARCHAR(64) UNIQUE,
                razorpay_payment_link_id VARCHAR(64),
                discord_user_id BIGINT NOT NULL,
                guild_id BIGINT,
                target_type VARCHAR(20) NOT NULL,
                duration_days INT NOT NULL,
                plan_tier VARCHAR(50) DEFAULT 'pro',
                amount_smallest_unit INT NOT NULL,
                currency VARCHAR(10) DEFAULT 'INR',
                status VARCHAR(20) DEFAULT 'created',
                is_trial BOOLEAN DEFAULT FALSE,
                last_reminder_sent_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at TIMESTAMP
            );
            """,
            # Custom Components V2 Embed / Container Templates table
            """
            CREATE TABLE IF NOT EXISTS server_embeds (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                embed_name VARCHAR(64) NOT NULL,
                container_payload TEXT NOT NULL,
                created_by BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, embed_name)
            );
            """,
            # Live Interactive Messages for Dropdown Page Switchers
            """
            CREATE TABLE IF NOT EXISTS interactive_cards (
                guild_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                template_name VARCHAR(64),
                card_payload TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, message_id)
            );
            """,
            # Server Auto-Events (Welcome, Leave, Boost) binding table
            """
            CREATE TABLE IF NOT EXISTS server_events (
                guild_id BIGINT NOT NULL,
                event_type VARCHAR(32) NOT NULL,
                channel_id BIGINT,
                embed_name VARCHAR(64),
                message_content TEXT,
                is_enabled BOOLEAN DEFAULT TRUE,
                dm_enabled BOOLEAN DEFAULT FALSE,
                dm_embed_name VARCHAR(64),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, event_type)
            );
            """,
        ]
        async with self.pool.acquire() as conn:
            for query in queries:
                await conn.execute(query)
        logger.info("PostgreSQL database schemas verified successfully.")

    def _convert_query(self, query: str) -> str:
        """Convert SQLite-specific query syntax to standard PostgreSQL."""
        converted = query
        if "INSERT OR IGNORE INTO" in converted:
            converted = converted.replace("INSERT OR IGNORE INTO", "INSERT INTO")
            if "ON CONFLICT" not in converted:
                converted = converted.rstrip(";") + " ON CONFLICT DO NOTHING;"

        if "?" not in converted:
            return converted

        parts = converted.split("?")
        result = []
        for i, part in enumerate(parts[:-1]):
            result.append(part)
            result.append(f"${i + 1}")
        result.append(parts[-1])
        return "".join(result)

    async def execute(self, query: str, *args: Any) -> None:
        """Execute a query without expecting return values."""
        pg_query = self._convert_query(query)
        async with self.pool.acquire() as conn:
            await conn.execute(pg_query, *args)

    async def fetch_one(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Fetch a single record as a dictionary."""
        pg_query = self._convert_query(query)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(pg_query, *args)
            return dict(row) if row else None

    async def fetch_all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Fetch multiple records as a list of dictionaries."""
        pg_query = self._convert_query(query)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(pg_query, *args)
            return [dict(r) for r in rows]
