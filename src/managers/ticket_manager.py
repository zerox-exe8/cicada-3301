"""
Cicada 3301 Discord Bot - Ticket Manager
Handles high-performance caching, database persistence, and lifecycle for ticket panels and active tickets.
"""

from __future__ import annotations

import logging
from typing import Any
from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Cicada.Managers.Ticket")


class TicketManager:
    """Manager for modular ticket panels and active ticket sessions."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # guild_id -> list of panel dicts
        self._panels_cache: dict[int, list[dict[str, Any]]] = {}
        # channel_id -> ticket dict
        self._active_tickets_cache: dict[int, dict[str, Any]] = {}

    async def load_cache(self) -> None:
        """Load all active ticket panels and open tickets into memory."""
        try:
            panels = await self.db.fetch_all("SELECT * FROM ticket_panels ORDER BY id ASC;")
            self._panels_cache.clear()
            for p in panels:
                gid = int(p["guild_id"])
                if gid not in self._panels_cache:
                    self._panels_cache[gid] = []
                self._panels_cache[gid].append(p)

            tickets = await self.db.fetch_all("SELECT * FROM active_tickets WHERE status = 'open';")
            self._active_tickets_cache.clear()
            for t in tickets:
                cid = int(t["channel_id"])
                self._active_tickets_cache[cid] = t

            logger.info(f"Loaded {len(panels)} ticket panels and {len(tickets)} active tickets into cache.")
        except Exception as e:
            logger.error(f"Failed to load ticket manager cache: {e}", exc_info=e)

    # ─── PANEL OPERATIONS ─────────────────────────────────────────────────────

    async def create_panel(
        self,
        guild_id: int,
        panel_name: str,
        embed_name: str,
        channel_id: int,
        message_id: int,
        category_id: int | None,
        support_role_id: int | None,
        log_channel_id: int | None,
        naming_format: str = "ticket-{count}",
        button_label: str = "Create Ticket",
        button_style: int = 1,
        button_emoji: str | None = None,
        created_by: int = 0,
    ) -> dict[str, Any]:
        """Create or update a ticket panel configuration."""
        clean_name = panel_name.lower().strip()
        query = """
        INSERT INTO ticket_panels (
            guild_id, panel_name, embed_name, channel_id, message_id,
            category_id, support_role_id, log_channel_id, naming_format,
            button_label, button_style, button_emoji, created_by
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        ON CONFLICT (guild_id, panel_name) DO UPDATE SET
            embed_name = EXCLUDED.embed_name,
            channel_id = EXCLUDED.channel_id,
            message_id = EXCLUDED.message_id,
            category_id = EXCLUDED.category_id,
            support_role_id = EXCLUDED.support_role_id,
            log_channel_id = EXCLUDED.log_channel_id,
            naming_format = EXCLUDED.naming_format,
            button_label = EXCLUDED.button_label,
            button_style = EXCLUDED.button_style,
            button_emoji = EXCLUDED.button_emoji
        RETURNING *;
        """
        row = await self.db.fetch_one(
            query,
            guild_id,
            clean_name,
            embed_name,
            channel_id,
            message_id,
            category_id,
            support_role_id,
            log_channel_id,
            naming_format,
            button_label,
            button_style,
            button_emoji,
            created_by,
        )

        if guild_id not in self._panels_cache:
            self._panels_cache[guild_id] = []
        self._panels_cache[guild_id] = [p for p in self._panels_cache[guild_id] if p["panel_name"] != clean_name]
        if row:
            self._panels_cache[guild_id].append(row)
        return row or {}

    async def get_panel(self, guild_id: int, panel_name: str) -> dict[str, Any] | None:
        """Fetch a panel by guild and panel name."""
        clean_name = panel_name.lower().strip()
        if guild_id in self._panels_cache:
            for p in self._panels_cache[guild_id]:
                if p["panel_name"] == clean_name:
                    return p

        row = await self.db.fetch_one(
            "SELECT * FROM ticket_panels WHERE guild_id = $1 AND panel_name = $2;",
            guild_id,
            clean_name,
        )
        return row

    async def get_panel_by_id(self, panel_id: int) -> dict[str, Any] | None:
        """Fetch a panel by panel ID across caches."""
        for g_panels in self._panels_cache.values():
            for p in g_panels:
                if p.get("id") == panel_id:
                    return p

        row = await self.db.fetch_one(
            "SELECT * FROM ticket_panels WHERE id = $1;",
            panel_id,
        )
        return row

    async def get_panel_by_message(self, guild_id: int, message_id: int) -> dict[str, Any] | None:
        """Fetch a panel by its deployed message ID."""
        if guild_id in self._panels_cache:
            for p in self._panels_cache[guild_id]:
                if p.get("message_id") == message_id:
                    return p

        row = await self.db.fetch_one(
            "SELECT * FROM ticket_panels WHERE guild_id = $1 AND message_id = $2;",
            guild_id,
            message_id,
        )
        return row

    async def list_panels(self, guild_id: int) -> list[dict[str, Any]]:
        """List all configured panels for a guild."""
        if guild_id in self._panels_cache:
            return list(self._panels_cache[guild_id])

        rows = await self.db.fetch_all(
            "SELECT * FROM ticket_panels WHERE guild_id = $1 ORDER BY id ASC;",
            guild_id,
        )
        self._panels_cache[guild_id] = rows
        return rows

    async def delete_panel(self, guild_id: int, panel_name: str) -> bool:
        """Delete a ticket panel from database and cache."""
        clean_name = panel_name.lower().strip()
        await self.db.execute(
            "DELETE FROM ticket_panels WHERE guild_id = $1 AND panel_name = $2;",
            guild_id,
            clean_name,
        )
        if guild_id in self._panels_cache:
            self._panels_cache[guild_id] = [p for p in self._panels_cache[guild_id] if p["panel_name"] != clean_name]
        return True

    # ─── TICKET COUNTERS ──────────────────────────────────────────────────────

    async def get_next_ticket_number(self, guild_id: int) -> int:
        """Increment and return the next sequential ticket number for the guild."""
        query = """
        INSERT INTO guild_ticket_counters (guild_id, total_tickets)
        VALUES ($1, 1)
        ON CONFLICT (guild_id) DO UPDATE SET total_tickets = guild_ticket_counters.total_tickets + 1
        RETURNING total_tickets;
        """
        row = await self.db.fetch_one(query, guild_id)
        return int(row["total_tickets"]) if row else 1

    # ─── ACTIVE TICKET OPERATIONS ─────────────────────────────────────────────

    async def create_ticket(
        self,
        guild_id: int,
        panel_id: int,
        channel_id: int,
        user_id: int,
        ticket_number: int,
    ) -> dict[str, Any]:
        """Record an open ticket in the database and cache."""
        query = """
        INSERT INTO active_tickets (guild_id, panel_id, channel_id, user_id, ticket_number, status)
        VALUES ($1, $2, $3, $4, $5, 'open')
        RETURNING *;
        """
        row = await self.db.fetch_one(query, guild_id, panel_id, channel_id, user_id, ticket_number)
        if row:
            self._active_tickets_cache[channel_id] = row
        return row or {}

    async def get_ticket(self, channel_id: int) -> dict[str, Any] | None:
        """Get active ticket metadata by channel ID."""
        if channel_id in self._active_tickets_cache:
            return self._active_tickets_cache[channel_id]

        row = await self.db.fetch_one(
            "SELECT * FROM active_tickets WHERE channel_id = $1;",
            channel_id,
        )
        if row and row.get("status") == "open":
            self._active_tickets_cache[channel_id] = row
        return row

    async def get_active_ticket_for_user(self, guild_id: int, user_id: int, panel_id: int | None = None) -> dict[str, Any] | None:
        """Check if user already has an open ticket for the specified panel or guild."""
        for t in self._active_tickets_cache.values():
            if t.get("guild_id") == guild_id and t.get("user_id") == user_id and t.get("status") == "open":
                if panel_id is None or t.get("panel_id") == panel_id:
                    return t

        query = "SELECT * FROM active_tickets WHERE guild_id = $1 AND user_id = $2 AND status = 'open'"
        args: list[Any] = [guild_id, user_id]
        if panel_id is not None:
            query += " AND panel_id = $3"
            args.append(panel_id)
        query += " LIMIT 1;"

        row = await self.db.fetch_one(query, *args)
        return row

    async def claim_ticket(self, channel_id: int, claimed_by: int) -> bool:
        """Set the claiming staff member for an active ticket."""
        await self.db.execute(
            "UPDATE active_tickets SET claimed_by = $1 WHERE channel_id = $2 AND status = 'open';",
            claimed_by,
            channel_id,
        )
        if channel_id in self._active_tickets_cache:
            self._active_tickets_cache[channel_id]["claimed_by"] = claimed_by
        return True

    async def close_ticket(self, channel_id: int, closed_by: int) -> bool:
        """Mark an active ticket as closed."""
        await self.db.execute(
            """
            UPDATE active_tickets
            SET status = 'closed', closed_at = CURRENT_TIMESTAMP, closed_by = $1
            WHERE channel_id = $2;
            """,
            closed_by,
            channel_id,
        )
        if channel_id in self._active_tickets_cache:
            del self._active_tickets_cache[channel_id]
        return True
