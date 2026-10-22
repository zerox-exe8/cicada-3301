from __future__ import annotations

from typing import Any, Optional
from src.repositories.base import BaseRepository


class TicketRepository(BaseRepository):
    """Repository managing ticket panels, active tickets, and sequential counters in PostgreSQL."""

    # ─── BULK HYDRATION ────────────────────────────────────────────────────────

    async def get_all_panels(self) -> list[dict[str, Any]]:
        """Fetch all panels ordered by id."""
        return await self.fetch_all("SELECT * FROM ticket_panels ORDER BY id ASC;")

    async def get_all_open_tickets(self) -> list[dict[str, Any]]:
        """Fetch all open tickets."""
        return await self.fetch_all("SELECT * FROM active_tickets WHERE status = 'open';")

    # ─── PANEL OPERATIONS ─────────────────────────────────────────────────────

    async def upsert_panel(
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
    ) -> Optional[dict[str, Any]]:
        """Insert or update a ticket panel configuration and return the record."""
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
        return await self.fetch_one(
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

    async def get_panel(self, guild_id: int, panel_name: str) -> Optional[dict[str, Any]]:
        """Fetch panel by guild and panel name."""
        clean_name = panel_name.lower().strip()
        return await self.fetch_one(
            "SELECT * FROM ticket_panels WHERE guild_id = $1 AND panel_name = $2;",
            guild_id,
            clean_name,
        )

    async def get_panel_by_id(self, panel_id: int) -> Optional[dict[str, Any]]:
        """Fetch panel by its primary key ID."""
        return await self.fetch_one("SELECT * FROM ticket_panels WHERE id = $1;", panel_id)

    async def get_panel_by_message(self, guild_id: int, message_id: int) -> Optional[dict[str, Any]]:
        """Fetch panel by deployed message ID."""
        return await self.fetch_one(
            "SELECT * FROM ticket_panels WHERE guild_id = $1 AND message_id = $2;",
            guild_id,
            message_id,
        )

    async def list_panels(self, guild_id: int) -> list[dict[str, Any]]:
        """List all configured panels for a guild."""
        return await self.fetch_all(
            "SELECT * FROM ticket_panels WHERE guild_id = $1 ORDER BY id ASC;",
            guild_id,
        )

    async def delete_panel(self, guild_id: int, panel_name: str) -> None:
        """Delete a ticket panel."""
        clean_name = panel_name.lower().strip()
        await self.execute(
            "DELETE FROM ticket_panels WHERE guild_id = $1 AND panel_name = $2;",
            guild_id,
            clean_name,
        )

    # ─── TICKET COUNTERS ──────────────────────────────────────────────────────

    async def get_next_ticket_number(self, guild_id: int) -> int:
        """Increment and return next sequential ticket counter for a guild."""
        query = """
        INSERT INTO guild_ticket_counters (guild_id, total_tickets)
        VALUES ($1, 1)
        ON CONFLICT (guild_id) DO UPDATE SET total_tickets = guild_ticket_counters.total_tickets + 1
        RETURNING total_tickets;
        """
        row = await self.fetch_one(query, guild_id)
        return int(row["total_tickets"]) if row else 1

    # ─── ACTIVE TICKETS ───────────────────────────────────────────────────────

    async def create_ticket(
        self,
        guild_id: int,
        panel_id: int,
        channel_id: int,
        user_id: int,
        ticket_number: int,
    ) -> Optional[dict[str, Any]]:
        """Insert open ticket and return record."""
        query = """
        INSERT INTO active_tickets (guild_id, panel_id, channel_id, user_id, ticket_number, status)
        VALUES ($1, $2, $3, $4, $5, 'open')
        RETURNING *;
        """
        return await self.fetch_one(query, guild_id, panel_id, channel_id, user_id, ticket_number)

    async def get_ticket(self, channel_id: int) -> Optional[dict[str, Any]]:
        """Fetch active ticket by channel ID."""
        return await self.fetch_one(
            "SELECT * FROM active_tickets WHERE channel_id = $1;",
            channel_id,
        )

    async def get_active_ticket_for_user(
        self, guild_id: int, user_id: int, panel_id: int | None = None
    ) -> Optional[dict[str, Any]]:
        """Query if user has an existing open ticket."""
        query = "SELECT * FROM active_tickets WHERE guild_id = $1 AND user_id = $2 AND status = 'open'"
        args: list[Any] = [guild_id, user_id]
        if panel_id is not None:
            query += " AND panel_id = $3"
            args.append(panel_id)
        query += " LIMIT 1;"
        return await self.fetch_one(query, *args)

    async def claim_ticket(self, channel_id: int, claimed_by: int) -> None:
        """Set claiming staff ID for open ticket."""
        await self.execute(
            "UPDATE active_tickets SET claimed_by = $1 WHERE channel_id = $2 AND status = 'open';",
            claimed_by,
            channel_id,
        )

    async def close_ticket(self, channel_id: int, closed_by: int) -> None:
        """Set status = closed for ticket."""
        query = """
        UPDATE active_tickets
        SET status = 'closed', closed_at = CURRENT_TIMESTAMP, closed_by = $1
        WHERE channel_id = $2;
        """
        await self.execute(query, closed_by, channel_id)
