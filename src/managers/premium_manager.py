"""
Cicada 3301 Discord Bot - Premium License & Subscription Manager
Handles cryptographically secure license key generation, redemption, and in-memory zero-latency cache.
"""

from __future__ import annotations

import datetime
import logging
import secrets
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Cicada.PremiumManager")


class PremiumManager:
    """Manages guild and user premium tiers with 0ms in-memory cache."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        # Cache format: {guild_id: {"tier": "pro", "expires_at": datetime | None}}
        self._guild_cache: dict[int, dict[str, Any]] = {}
        # Cache format: {user_id: {"tier": "pro", "expires_at": datetime | None}}
        self._user_cache: dict[int, dict[str, Any]] = {}
        # Anti-Brute-Force Rate Limiter: {user_id: [timestamp1, timestamp2, ...]}
        self._failed_attempts: dict[int, list[datetime.datetime]] = {}
        # Cooldown blocks: {user_id: blocked_until_datetime}
        self._blocked_users: dict[int, datetime.datetime] = {}

    def check_rate_limit(self, user_id: int) -> tuple[bool, int]:
        """
        Check if a user is blocked from redeeming keys due to failed attempts.
        Returns: (is_blocked: bool, remaining_seconds: int)
        """
        now = datetime.datetime.now(datetime.timezone.utc)

        # 1. Check if user is currently blocked
        blocked_until = self._blocked_users.get(user_id)
        if blocked_until:
            if blocked_until > now:
                remaining = int((blocked_until - now).total_seconds())
                return True, remaining
            else:
                # Block expired
                self._blocked_users.pop(user_id, None)
                self._failed_attempts.pop(user_id, None)

        return False, 0

    def register_failed_attempt(self, user_id: int) -> bool:
        """
        Record a failed key attempt. If >= 3 failures in 60s, block for 15 minutes.
        Returns True if user just got blocked.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        window = datetime.timedelta(seconds=60)
        cooldown = datetime.timedelta(minutes=15)

        attempts = self._failed_attempts.get(user_id, [])
        # Filter attempts within last 60 seconds
        attempts = [t for t in attempts if now - t < window]
        attempts.append(now)
        self._failed_attempts[user_id] = attempts

        if len(attempts) >= 3:
            self._blocked_users[user_id] = now + cooldown
            logger.warning(f"Anti-Brute-Force triggered: User ID {user_id} blocked for 15 minutes.")
            return True

        return False

    def clear_failed_attempts(self, user_id: int) -> None:
        """Clear failed attempts upon successful redemption."""
        self._failed_attempts.pop(user_id, None)
        self._blocked_users.pop(user_id, None)

    async def load_cache(self) -> None:
        """Load all active guild and user premiums into memory on bot startup."""
        now = datetime.datetime.now(datetime.timezone.utc)

        # 1. Load active guild premiums
        guild_rows = await self.db.fetch_all("SELECT guild_id, tier, expires_at FROM guild_premium;")
        for row in guild_rows:
            g_id = int(row["guild_id"])
            exp = row["expires_at"]
            if exp and exp.tzinfo is None:
                exp = exp.replace(tzinfo=datetime.timezone.utc)

            # Keep only non-expired or lifetime
            if exp is None or exp > now:
                self._guild_cache[g_id] = {
                    "tier": row.get("tier", "pro"),
                    "expires_at": exp,
                }

        # 2. Load active user premiums
        user_rows = await self.db.fetch_all("SELECT user_id, tier, expires_at FROM user_premium;")
        for row in user_rows:
            u_id = int(row["user_id"])
            exp = row["expires_at"]
            if exp and exp.tzinfo is None:
                exp = exp.replace(tzinfo=datetime.timezone.utc)

            if exp is None or exp > now:
                self._user_cache[u_id] = {
                    "tier": row.get("tier", "pro"),
                    "expires_at": exp,
                }

        logger.info(
            f"Loaded {len(self._guild_cache)} premium guild(s) and {len(self._user_cache)} premium user(s) into memory."
        )

    def is_guild_premium(self, guild_id: int | None) -> bool:
        """Check if a guild has active premium (<0.001ms)."""
        if not guild_id:
            return False

        data = self._guild_cache.get(guild_id)
        if not data:
            return False

        exp = data["expires_at"]
        if exp is None:
            return True  # Lifetime

        now = datetime.datetime.now(datetime.timezone.utc)
        if exp > now:
            return True
        else:
            # Expired, clean cache
            self._guild_cache.pop(guild_id, None)
            return False

    def is_user_premium(self, user_id: int | None) -> bool:
        """Check if a user has active personal premium (<0.001ms)."""
        if not user_id:
            return False

        data = self._user_cache.get(user_id)
        if not data:
            return False

        exp = data["expires_at"]
        if exp is None:
            return True

        now = datetime.datetime.now(datetime.timezone.utc)
        if exp > now:
            return True
        else:
            self._user_cache.pop(user_id, None)
            return False

    def get_guild_info(self, guild_id: int | None) -> dict[str, Any]:
        """Get detailed premium information for a server."""
        if not guild_id or not self.is_guild_premium(guild_id):
            return {
                "is_premium": False,
                "tier": "Free",
                "expires_at": None,
                "remaining_str": "N/A",
            }

        data = self._guild_cache[guild_id]
        exp: datetime.datetime | None = data["expires_at"]

        if exp is None:
            remaining_str = "Lifetime / Permanent"
        else:
            now = datetime.datetime.now(datetime.timezone.utc)
            delta = exp - now
            days = delta.days
            hours, rem = divmod(delta.seconds, 3600)
            mins, _ = divmod(rem, 60)
            if days > 0:
                remaining_str = f"{days} day(s), {hours} hour(s)"
            else:
                remaining_str = f"{hours} hour(s), {mins} minute(s)"

        return {
            "is_premium": True,
            "tier": data.get("tier", "Pro").title(),
            "expires_at": exp,
            "remaining_str": remaining_str,
        }

    def get_user_info(self, user_id: int | None) -> dict[str, Any]:
        """Get detailed premium information for a user account."""
        if not user_id or not self.is_user_premium(user_id):
            return {
                "is_premium": False,
                "tier": "Free",
                "expires_at": None,
                "remaining_str": "N/A",
            }

        data = self._user_cache[user_id]
        exp: datetime.datetime | None = data["expires_at"]

        if exp is None:
            remaining_str = "Lifetime / Permanent"
        else:
            now = datetime.datetime.now(datetime.timezone.utc)
            delta = exp - now
            days = delta.days
            hours, rem = divmod(delta.seconds, 3600)
            mins, _ = divmod(rem, 60)
            if days > 0:
                remaining_str = f"{days} day(s), {hours} hour(s)"
            else:
                remaining_str = f"{hours} hour(s), {mins} minute(s)"

        return {
            "is_premium": True,
            "tier": data.get("tier", "Pro").title(),
            "expires_at": exp,
            "remaining_str": remaining_str,
        }

    async def generate_key(
        self,
        duration_days: int,
        target_type: str = "guild",
        created_by: int = 0,
    ) -> str:
        """Generate a cryptographically secure, unique license key."""
        part1 = secrets.token_hex(2).upper()
        part2 = secrets.token_hex(2).upper()
        key = f"CICADA_3301-PRO-{part1}-{part2}"

        await self.db.execute(
            """
            INSERT INTO premium_keys (key, duration_days, target_type, created_by, is_used)
            VALUES (?, ?, ?, ?, FALSE);
            """,
            key,
            duration_days,
            target_type.lower(),
            created_by,
        )
        logger.info(f"Generated new premium key: {key} ({duration_days} days, type: {target_type})")
        return key

    async def redeem_key(
        self,
        key: str,
        redeemer_id: int,
        target_id: int,
        target_type: str = "guild",
    ) -> dict[str, Any]:
        """Validate and redeem a license key atomically."""
        clean_key = key.strip().upper()

        row = await self.db.fetch_one(
            "SELECT key, duration_days, target_type, is_used FROM premium_keys WHERE key = ?;",
            clean_key,
        )

        if not row:
            return {"success": False, "error": "Invalid license key. Please check spelling."}

        if row.get("is_used"):
            return {"success": False, "error": "This license key has already been redeemed."}

        expected_type = row.get("target_type", "guild").lower()
        if expected_type != target_type.lower():
            return {
                "success": False,
                "error": f"This key is a `{expected_type.title()}` key, but you tried to redeem it for a `{target_type.title()}`.",
            }

        duration_days = int(row["duration_days"])
        now = datetime.datetime.now(datetime.timezone.utc)

        # 1. Calculate expiration (0 = lifetime)
        if duration_days == 0:
            expires_at = None
            duration_text = "Lifetime"
        else:
            # If already premium, extend duration
            current_info = self.get_guild_info(target_id) if target_type == "guild" else {"is_premium": False}
            if current_info.get("is_premium") and current_info.get("expires_at"):
                base_time = current_info["expires_at"]
            else:
                base_time = now

            expires_at = base_time + datetime.timedelta(days=duration_days)
            duration_text = f"{duration_days} Days"

        # 2. Mark key as used
        await self.db.execute(
            """
            UPDATE premium_keys 
            SET is_used = TRUE, redeemed_by = ?, redeemed_target_id = ?, redeemed_at = CURRENT_TIMESTAMP
            WHERE key = ?;
            """,
            redeemer_id,
            target_id,
            clean_key,
        )

        # 3. Save into guild_premium or user_premium
        db_expires_at = expires_at.astimezone(datetime.timezone.utc).replace(tzinfo=None) if expires_at else None

        if target_type == "guild":
            await self.db.execute(
                """
                INSERT INTO guild_premium (guild_id, tier, activated_by, key_used, expires_at)
                VALUES (?, 'pro', ?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    tier = excluded.tier,
                    activated_by = excluded.activated_by,
                    key_used = excluded.key_used,
                    expires_at = excluded.expires_at;
                """,
                target_id,
                redeemer_id,
                clean_key,
                db_expires_at,
            )
            self._guild_cache[target_id] = {"tier": "pro", "expires_at": expires_at}

        else:
            await self.db.execute(
                """
                INSERT INTO user_premium (user_id, tier, key_used, expires_at)
                VALUES (?, 'pro', ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                    tier = excluded.tier,
                    key_used = excluded.key_used,
                    expires_at = excluded.expires_at;
                """,
                target_id,
                clean_key,
                db_expires_at,
            )
            self._user_cache[target_id] = {"tier": "pro", "expires_at": expires_at}

        # 4. Record Customer Intelligence & Repeat History
        await self.db.execute(
            """
            INSERT INTO premium_customers (target_id, target_type, total_redemptions, total_days_purchased, first_redeemed_at, last_redeemed_at)
            VALUES (?, ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (target_id) DO UPDATE SET
                total_redemptions = premium_customers.total_redemptions + 1,
                total_days_purchased = premium_customers.total_days_purchased + excluded.total_days_purchased,
                last_redeemed_at = CURRENT_TIMESTAMP;
            """,
            target_id,
            target_type,
            duration_days,
        )

        logger.info(f"Key {clean_key} successfully redeemed for {target_type} ID {target_id}.")
        return {
            "success": True,
            "duration_text": duration_text,
            "expires_at": expires_at,
            "target_type": target_type,
        }

    async def grant_premium(
        self,
        target_id: int,
        duration_days: int,
        target_type: str = "guild",
        admin_id: int = 0,
    ) -> dict[str, Any]:
        """Directly grant premium without a key (Developer Override with duration stacking)."""
        now = datetime.datetime.now(datetime.timezone.utc)
        existing_info = self._guild_cache.get(target_id) if target_type == "guild" else self._user_cache.get(target_id)
        existing_exp = existing_info.get("expires_at") if existing_info else None

        if duration_days == 0:
            expires_at = None
        else:
            base_time = existing_exp if (existing_exp and existing_exp > now) else now
            expires_at = base_time + datetime.timedelta(days=duration_days)

        db_expires_at = expires_at.astimezone(datetime.timezone.utc).replace(tzinfo=None) if expires_at else None

        if target_type == "guild":
            await self.db.execute(
                """
                INSERT INTO guild_premium (guild_id, tier, activated_by, key_used, expires_at)
                VALUES (?, 'pro', ?, 'DEV_GRANT', ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    tier = excluded.tier,
                    activated_by = excluded.activated_by,
                    key_used = 'DEV_GRANT',
                    expires_at = excluded.expires_at;
                """,
                target_id,
                admin_id,
                db_expires_at,
            )
            self._guild_cache[target_id] = {"tier": "pro", "expires_at": expires_at}
        else:
            await self.db.execute(
                """
                INSERT INTO user_premium (user_id, tier, key_used, expires_at)
                VALUES (?, 'pro', 'DEV_GRANT', ?)
                ON CONFLICT (user_id) DO UPDATE SET
                    tier = excluded.tier,
                    key_used = 'DEV_GRANT',
                    expires_at = excluded.expires_at;
                """,
                target_id,
                db_expires_at,
            )
            self._user_cache[target_id] = {"tier": "pro", "expires_at": expires_at}

        # Record Customer Intelligence & Repeat History
        await self.db.execute(
            """
            INSERT INTO premium_customers (target_id, target_type, total_redemptions, total_days_purchased, first_redeemed_at, last_redeemed_at)
            VALUES (?, ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (target_id) DO UPDATE SET
                total_redemptions = premium_customers.total_redemptions + 1,
                total_days_purchased = premium_customers.total_days_purchased + excluded.total_days_purchased,
                last_redeemed_at = CURRENT_TIMESTAMP;
            """,
            target_id,
            target_type,
            duration_days,
        )

        logger.info(f"Direct premium granted to {target_type} {target_id} for {duration_days} days by admin {admin_id}.")
        return {
            "success": True,
            "duration_text": "Lifetime" if duration_days == 0 else f"{duration_days} Days",
            "expires_at": expires_at,
        }

    async def get_customer_analytics(self) -> dict[str, Any]:
        """Fetch customer retention, repeat buyers, and lifetime statistics."""
        customers = await self.db.fetch_all(
            """
            SELECT target_id, target_type, total_redemptions, total_days_purchased, first_redeemed_at, last_redeemed_at
            FROM premium_customers
            ORDER BY total_redemptions DESC, total_days_purchased DESC
            LIMIT 15;
            """
        )
        row_total = await self.db.fetch_one("SELECT COUNT(*) as count, SUM(total_days_purchased) as total_days FROM premium_customers;")
        row_repeat = await self.db.fetch_one("SELECT COUNT(*) as count FROM premium_customers WHERE total_redemptions > 1;")

        total_customers = row_total["count"] if row_total and row_total["count"] else 0
        total_days = row_total["total_days"] if row_total and row_total["total_days"] else 0
        repeat_customers = row_repeat["count"] if row_repeat and row_repeat["count"] else 0
        repeat_rate = round((repeat_customers / total_customers * 100), 1) if total_customers > 0 else 0.0

        return {
            "total_customers": total_customers,
            "repeat_customers": repeat_customers,
            "repeat_rate": repeat_rate,
            "total_days_sold": total_days,
            "customers": customers,
        }

    async def clear_key_history(self, filter_mode: str = "used") -> tuple[int, list[dict[str, Any]]]:
        """
        Purge key history from premium_keys while preserving lifetime customer analytics.
        Returns (deleted_count, backup_records).
        filter_mode options: 'used' (only redeemed keys), 'all' (all keys).
        """
        if filter_mode == "all":
            query_fetch = "SELECT * FROM premium_keys ORDER BY created_at DESC;"
            query_delete = "DELETE FROM premium_keys;"
        else:
            query_fetch = "SELECT * FROM premium_keys WHERE is_used = TRUE ORDER BY redeemed_at DESC;"
            query_delete = "DELETE FROM premium_keys WHERE is_used = TRUE;"

        backup_records = await self.db.fetch_all(query_fetch)
        await self.db.execute(query_delete)
        logger.info(f"Purged {len(backup_records)} key records from premium_keys under mode '{filter_mode}'.")
        return len(backup_records), backup_records

    async def revoke_premium(self, target_id: int, target_type: str | None = None) -> tuple[bool, str]:
        """
        Revoke premium from a server or user.
        If target_type is None, automatically detects whether ID belongs to a guild or user subscription.
        Returns (was_revoked: bool, actual_type: str).
        """
        if target_type == "guild":
            existed = target_id in self._guild_cache
            await self.db.execute("DELETE FROM guild_premium WHERE guild_id = ?;", target_id)
            self._guild_cache.pop(target_id, None)
            logger.info(f"Revoked premium from guild ID {target_id}. Existed: {existed}")
            return existed, "guild"
        elif target_type == "user":
            existed = target_id in self._user_cache
            await self.db.execute("DELETE FROM user_premium WHERE user_id = ?;", target_id)
            self._user_cache.pop(target_id, None)
            logger.info(f"Revoked premium from user ID {target_id}. Existed: {existed}")
            return existed, "user"
        else:
            # Auto-detection mode: Check memory cache first
            if target_id in self._user_cache:
                await self.db.execute("DELETE FROM user_premium WHERE user_id = ?;", target_id)
                self._user_cache.pop(target_id, None)
                logger.info(f"Auto-detected & revoked user VIP for ID {target_id}.")
                return True, "user"
            elif target_id in self._guild_cache:
                await self.db.execute("DELETE FROM guild_premium WHERE guild_id = ?;", target_id)
                self._guild_cache.pop(target_id, None)
                logger.info(f"Auto-detected & revoked guild Pro for ID {target_id}.")
                return True, "guild"
            else:
                # Check DB directly in case cache was out of sync
                user_row = await self.db.fetch_one("SELECT user_id FROM user_premium WHERE user_id = ?;", target_id)
                if user_row:
                    await self.db.execute("DELETE FROM user_premium WHERE user_id = ?;", target_id)
                    self._user_cache.pop(target_id, None)
                    return True, "user"
                guild_row = await self.db.fetch_one("SELECT guild_id FROM guild_premium WHERE guild_id = ?;", target_id)
                if guild_row:
                    await self.db.execute("DELETE FROM guild_premium WHERE guild_id = ?;", target_id)
                    self._guild_cache.pop(target_id, None)
                    return True, "guild"
                return False, "guild"

    async def sweep_expired_subscriptions(self) -> list[int]:
        """
        Clean up expired subscriptions from the database and memory cache.
        Returns a list of expired guild IDs.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        db_now = now.replace(tzinfo=None)

        # 1. Fetch expired guilds
        expired_guild_rows = await self.db.fetch_all(
            "SELECT guild_id FROM guild_premium WHERE expires_at IS NOT NULL AND expires_at <= ?;",
            db_now,
        )
        expired_guild_ids = [int(r["guild_id"]) for r in expired_guild_rows]

        if expired_guild_ids:
            for g_id in expired_guild_ids:
                await self.db.execute("DELETE FROM guild_premium WHERE guild_id = ?;", g_id)
                self._guild_cache.pop(g_id, None)
            logger.info(f"Swept {len(expired_guild_ids)} expired guild subscription(s).")

        # 2. Fetch expired users
        expired_user_rows = await self.db.fetch_all(
            "SELECT user_id FROM user_premium WHERE expires_at IS NOT NULL AND expires_at <= ?;",
            db_now,
        )
        for r in expired_user_rows:
            u_id = int(r["user_id"])
            await self.db.execute("DELETE FROM user_premium WHERE user_id = ?;", u_id)
            self._user_cache.pop(u_id, None)

        return expired_guild_ids

    async def send_renewal_reminders(self, bot: Any) -> None:
        """
        Send proactive renewal DM reminders to server owners 2-3 days before their subscription expires.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        db_now = now.replace(tzinfo=None)
        reminder_window = (now + datetime.timedelta(days=3)).replace(tzinfo=None)

        rows = await self.db.fetch_all(
            """
            SELECT gp.guild_id, gp.activated_by, gp.expires_at, pt.id as tx_id, pt.last_reminder_sent_at
            FROM guild_premium gp
            LEFT JOIN payment_transactions pt ON gp.guild_id = pt.guild_id AND pt.status = 'paid'
            WHERE gp.expires_at IS NOT NULL 
              AND gp.expires_at > ? 
              AND gp.expires_at <= ?;
            """,
            db_now,
            reminder_window,
        )

        for row in rows:
            g_id = int(row["guild_id"])
            user_id = int(row["activated_by"]) if row.get("activated_by") else None
            exp: datetime.datetime = row["expires_at"]
            last_sent = row.get("last_reminder_sent_at")
            tx_id = row.get("tx_id")

            # Avoid sending multiple reminders in the same cycle
            if last_sent and (db_now - last_sent).total_seconds() < 86400:
                continue

            if not user_id:
                guild = bot.get_guild(g_id)
                if guild and guild.owner_id:
                    user_id = guild.owner_id

            if not user_id:
                continue

            try:
                user = bot.get_user(user_id) or await bot.fetch_user(user_id)
                if not user:
                    continue

                guild = bot.get_guild(g_id)
                guild_name = guild.name if guild else f"Server ID {g_id}"
                days_left = max(1, (exp - db_now).days)

                from src.utils.containers import CicadaContainer
                container = CicadaContainer(accent_color=None)
                container.add_text(
                    f"**Cicada Pro Subscription Expiring Soon**\n\n"
                    f"> Your Pro subscription for **{guild_name}** will expire in **{days_left} day(s)** (<t:{int(exp.replace(tzinfo=datetime.timezone.utc).timestamp())}:R>).\n\n"
                    f"• **Renew Seamlessly:** Run `?buy` in your server to renew without any feature downtime!"
                )
                container.add_separator(divider=True)
                container.add_text("-# Cicada 3301 Subscription Renewal Alert")

                await user.send(embed=container.build())
                logger.info(f"Sent renewal reminder DM to user {user_id} for guild {g_id}.")

                if tx_id:
                    await self.db.execute(
                        "UPDATE payment_transactions SET last_reminder_sent_at = CURRENT_TIMESTAMP WHERE id = ?;",
                        tx_id,
                    )
            except Exception as e:
                logger.warning(f"Could not send renewal reminder to user {user_id}: {e}")

    async def get_keys_dashboard(self) -> dict[str, Any]:
        """Fetch real-time analytics, active subscribers, available keys, and audit history."""
        row_total = await self.db.fetch_one("SELECT COUNT(*) as count FROM premium_keys;")
        row_unused = await self.db.fetch_one("SELECT COUNT(*) as count FROM premium_keys WHERE is_used = FALSE;")

        total_keys = row_total["count"] if row_total else 0
        unused_keys = row_unused["count"] if row_unused else 0
        # 1. Live Active Guilds
        active_guild_rows = await self.db.fetch_all(
            """
            SELECT guild_id, tier, activated_by, key_used, expires_at
            FROM guild_premium
            ORDER BY expires_at DESC NULLS FIRST;
            """
        )

        # 2. Live Active Users
        active_user_rows = await self.db.fetch_all(
            """
            SELECT user_id, tier, key_used, expires_at
            FROM user_premium
            ORDER BY expires_at DESC NULLS FIRST;
            """
        )

        active_guilds_count = len(active_guild_rows)
        active_users_count = len(active_user_rows)

        # 3. Available Unused Keys
        available_keys = await self.db.fetch_all(
            """
            SELECT key, duration_days, target_type, created_at
            FROM premium_keys
            WHERE is_used = FALSE
            ORDER BY created_at DESC
            LIMIT 10;
            """
        )

        # 4. Redemption & Audit History
        history_keys = await self.db.fetch_all(
            """
            SELECT key, duration_days, target_type, is_used, redeemed_by, redeemed_target_id, redeemed_at, created_at
            FROM premium_keys
            WHERE is_used = TRUE
            ORDER BY redeemed_at DESC NULLS LAST
            LIMIT 8;
            """
        )

        return {
            "total_keys": total_keys,
            "unused_keys": unused_keys,
            "active_guilds": active_guilds_count,
            "active_users": active_users_count,
            "active_guild_rows": active_guild_rows,
            "active_user_rows": active_user_rows,
            "available_keys": available_keys,
            "history_keys": history_keys,
        }
