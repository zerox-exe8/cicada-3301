"""
Cicada 3301 Discord Bot - 24/7 Keep-Alive Web Server & Razorpay Webhook Receiver
Provides HTTP endpoints for Render uptime health checks and automated payment webhook fulfillment.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from typing import TYPE_CHECKING, Any
from aiohttp import web

from src.core.config import Config
from src.utils.containers import CicadaContainer

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("Cicada.Server")


class HealthServer:
    """Async web server for hosting health checks and Razorpay webhooks."""

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self.app.router.add_get("/", self._handle_home)
        self.app.router.add_get("/health", self._handle_health)
        self.app.router.add_post("/webhook/razorpay", self._handle_razorpay_webhook)

    async def _handle_home(self, request: web.Request) -> web.Response:
        """Root endpoint returning basic status."""
        return web.Response(
            text="⚡ Cicada 3301 Discord Bot is Online & Running 24/7!",
            content_type="text/plain",
            status=200,
        )

    async def _handle_health(self, request: web.Request) -> web.Response:
        """Detailed health check endpoint."""
        ws_ping = round(self.bot.latency * 1000) if self.bot.latency else 0
        data = {
            "status": "healthy",
            "bot": "Cicada 3301",
            "guilds": len(self.bot.guilds),
            "ping_ms": ws_ping,
        }
        return web.json_response(data, status=200)

    async def _send_receipt_dm(
        self,
        user_id: int,
        guild_id: int,
        duration_days: int,
        payment_id: str,
        amount_smallest: int,
    ) -> None:
        """Deliver rich Components V2 payment receipt card to the customer's DM in the background."""
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            if not user:
                return

            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else f"Server ID {guild_id}"
            dur_str = "Lifetime / Permanent" if duration_days == 0 else f"{duration_days} Days"
            amount_inr = amount_smallest // 100

            container = CicadaContainer(accent_color=None)
            e_reg = self.bot.custom_emojis
            sparkle = e_reg.get("icons_star", "")
            sparkle_prefix = f"{sparkle} " if sparkle else ""

            container.add_text(
                f"{sparkle_prefix}**Payment Successful — Cicada Pro Activated!**\n\n"
                f"> Thank you for upgrading **{guild_name}** to Cicada Pro.\n"
                f"> All enterprise superpowers and server protection features are now active!\n\n"
                f"• **Target Server:** **{guild_name}**\n"
                f"• **Duration:** `{dur_str}`\n"
                f"• **Amount Paid:** `₹{amount_inr}`\n"
                f"• **Payment ID:** `{payment_id}`\n\n"
                f"• Your server's Pro status has been automatically updated in memory & database."
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Cicada 3301 Enterprise Subscription • Transaction ID: {payment_id}")

            await user.send(embed=container.build())
            logger.info(f"Payment receipt DM sent to user ID {user_id} for payment {payment_id}.")
        except Exception as e:
            logger.warning(f"Could not send receipt DM to user {user_id}: {e}")

    async def _send_refund_dm(self, user_id: int, guild_id: int, payment_id: str) -> None:
        """Notify user that a refund was processed and Pro status revoked in background."""
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            if not user:
                return

            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else f"Server ID {guild_id}"

            container = CicadaContainer(accent_color=None)
            container.add_text(
                f"**Cicada Pro Subscription Refunded**\n\n"
                f"> A refund was processed for **{guild_name}** (Payment ID: `{payment_id}`).\n"
                f"> The Pro superpowers for this server have been automatically revoked.\n"
                f"> Core free features remain active and unaffected."
            )
            container.add_separator(divider=True)
            container.add_text("-# Cicada 3301 Infrastructure")

            await user.send(embed=container.build())
        except Exception as e:
            logger.warning(f"Could not send refund DM to user {user_id}: {e}")

    async def _handle_razorpay_webhook(self, request: web.Request) -> web.Response:
        """
        Razorpay Webhook receiver for automated subscription fulfillment.
        Verifies HMAC-SHA256 signature and enforces race-condition-free atomic DB updates.
        """
        # 1. Verify Webhook Signature
        signature = request.headers.get("X-Razorpay-Signature", "")
        if not signature:
            logger.warning("Razorpay webhook rejected: Missing X-Razorpay-Signature header.")
            return web.Response(status=400, text="Missing signature header")

        webhook_secret = Config.RAZORPAY_WEBHOOK_SECRET
        if not webhook_secret:
            logger.error("RAZORPAY_WEBHOOK_SECRET is not configured on bot instance.")
            return web.Response(status=500, text="Webhook secret unconfigured")

        body_bytes = await request.read()
        expected_sig = hmac.new(
            webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_sig, signature):
            logger.warning("Razorpay webhook rejected: Invalid signature.")
            return web.Response(status=400, text="Invalid webhook signature")

        # 2. Parse Event Payload
        try:
            data: dict[str, Any] = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return web.Response(status=400, text="Invalid JSON payload")

        event = data.get("event", "")
        logger.info(f"Received verified Razorpay webhook event: {event}")

        # 3. Handle Payment Captures & Link Paid Events
        if event in ["payment.captured", "payment_link.paid", "order.paid"]:
            payload_data = data.get("payload", {})
            payment_entity = payload_data.get("payment", {}).get("entity", {})
            link_entity = payload_data.get("payment_link", {}).get("entity", {})

            payment_id = payment_entity.get("id") or link_entity.get("payment_id") or ""
            link_id = link_entity.get("id") or payment_entity.get("notes", {}).get("payment_link_id") or ""
            notes = payment_entity.get("notes", {}) or link_entity.get("notes", {})

            # A. Atomic claim via conditional UPDATE (Eliminates Race Conditions)
            claimed_row = await self.bot.db.fetch_one(
                """
                UPDATE payment_transactions 
                SET status = 'paid', razorpay_payment_id = ?, paid_at = CURRENT_TIMESTAMP
                WHERE (razorpay_payment_id = ? OR razorpay_payment_link_id = ?)
                  AND status != 'paid'
                RETURNING id, guild_id, discord_user_id, duration_days, target_type, amount_smallest_unit, currency;
                """,
                payment_id,
                payment_id,
                link_id,
            )

            # B. If no row was claimed, check if it was already fulfilled (Idempotency Guard)
            if not claimed_row:
                already_paid = await self.bot.db.fetch_one(
                    """
                    SELECT id FROM payment_transactions 
                    WHERE (razorpay_payment_id = ? OR razorpay_payment_link_id = ?) AND status = 'paid';
                    """,
                    payment_id,
                    link_id,
                )
                if already_paid:
                    logger.info(f"Payment {payment_id} was already fulfilled. Concurrency skip.")
                    return web.json_response({"status": "already_processed"}, status=200)

                # Fallback: Insert direct unlinked payments
                target_id = int(notes.get("guild_id") or notes.get("discord_user_id") or 0)
                target_type = notes.get("target_type", "guild")
                duration_days = int(notes.get("duration_days", 30))
                user_id = int(notes.get("discord_user_id", 0))
                amount_smallest = payment_entity.get("amount", 0)

                if not target_id:
                    logger.error(f"Cannot fulfill payment {payment_id}: No target ID found in DB or notes.")
                    return web.json_response({"error": "Missing target ID"}, status=200)

                await self.bot.db.execute(
                    """
                    INSERT INTO payment_transactions (
                        razorpay_payment_id, razorpay_payment_link_id, discord_user_id, guild_id, target_type, duration_days, plan_tier, amount_smallest_unit, currency, status, paid_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'pro', ?, 'INR', 'paid', CURRENT_TIMESTAMP);
                    """,
                    payment_id,
                    link_id,
                    user_id,
                    target_id if target_type == "guild" else None,
                    target_type,
                    duration_days,
                    amount_smallest,
                )
            else:
                target_id = int(claimed_row["guild_id"] or claimed_row["discord_user_id"])
                target_type = claimed_row["target_type"]
                duration_days = int(claimed_row["duration_days"])
                user_id = int(claimed_row["discord_user_id"])
                amount_smallest = int(claimed_row["amount_smallest_unit"])

            # C. Atomic Grant via Premium Manager
            await self.bot.premium_mgr.grant_premium(
                target_id=target_id,
                duration_days=duration_days,
                target_type=target_type,
                admin_id=user_id,
            )
            logger.info(f"Successfully fulfilled payment {payment_id} -> Granted {duration_days}d to {target_type} {target_id}.")

            # D. Dispatch Receipt DM asynchronously (Zero HTTP Webhook Latency)
            if user_id:
                asyncio.create_task(
                    self._send_receipt_dm(
                        user_id=user_id,
                        guild_id=target_id if target_type == "guild" else 0,
                        duration_days=duration_days,
                        payment_id=payment_id,
                        amount_smallest=amount_smallest,
                    )
                )

            # E. Instant Webhook Acknowledge (<20ms)
            return web.json_response({"status": "fulfilled", "payment_id": payment_id}, status=200)

        # 4. Handle Payment Failures
        elif event in ["payment.failed"]:
            payment_entity = data.get("payload", {}).get("payment", {}).get("entity", {})
            payment_id = payment_entity.get("id", "")
            await self.bot.db.execute(
                "UPDATE payment_transactions SET status = 'failed' WHERE razorpay_payment_id = ?;",
                payment_id,
            )
            logger.info(f"Payment marked as failed: {payment_id}")
            return web.json_response({"status": "marked_failed"}, status=200)

        # 5. Handle Refunds
        elif event in ["refund.processed", "payment.refunded"]:
            refund_entity = data.get("payload", {}).get("refund", {}).get("entity", {})
            payment_id = refund_entity.get("payment_id", "")
            
            tx_row = await self.bot.db.fetch_one(
                "SELECT * FROM payment_transactions WHERE razorpay_payment_id = ?;",
                payment_id,
            )
            if tx_row:
                target_id = int(tx_row["guild_id"] or tx_row["discord_user_id"])
                target_type = tx_row["target_type"]
                user_id = int(tx_row["discord_user_id"])

                await self.bot.premium_mgr.revoke_premium(target_id=target_id, target_type=target_type)
                await self.bot.db.execute(
                    "UPDATE payment_transactions SET status = 'refunded' WHERE id = ?;",
                    tx_row["id"],
                )
                logger.info(f"Refund processed for payment {payment_id} -> Revoked {target_type} {target_id}.")

                if user_id:
                    asyncio.create_task(
                        self._send_refund_dm(
                            user_id=user_id,
                            guild_id=target_id if target_type == "guild" else 0,
                            payment_id=payment_id,
                        )
                    )

            return web.json_response({"status": "refund_processed"}, status=200)

        return web.json_response({"status": "ignored"}, status=200)

    async def start(self) -> None:
        """Start the async HTTP server."""
        port = int(os.getenv("PORT", 8080))
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Keep-Alive Health & Webhook Server listening on http://0.0.0.0:{port}")

    async def stop(self) -> None:
        """Gracefully stop the web server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Keep-Alive Health & Webhook Server stopped.")
