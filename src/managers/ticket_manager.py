from __future__ import annotations

import logging
from typing import Any
from src.database.base import BaseDatabase
from src.repositories.ticket_repo import TicketRepository

logger = logging.getLogger("Kyro.Managers.Ticket")


class TicketManager:
    """Manager for modular ticket panels and active ticket sessions via TicketRepository."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        self.repo: TicketRepository = TicketRepository(db)
        # guild_id -> list of panel dicts
        self._panels_cache: dict[int, list[dict[str, Any]]] = {}
        # channel_id -> ticket dict
        self._active_tickets_cache: dict[int, dict[str, Any]] = {}

    async def load_cache(self) -> None:
        """Load all active ticket panels and open tickets into memory via repository."""
        try:
            panels = await self.repo.get_all_panels()
            self._panels_cache.clear()
            for p in panels:
                gid = int(p["guild_id"])
                if gid not in self._panels_cache:
                    self._panels_cache[gid] = []
                self._panels_cache[gid].append(p)

            tickets = await self.repo.get_all_open_tickets()
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
        """Create or update a ticket panel configuration via repository."""
        clean_name = panel_name.lower().strip()
        row = await self.repo.upsert_panel(
            guild_id=guild_id,
            panel_name=clean_name,
            embed_name=embed_name,
            channel_id=channel_id,
            message_id=message_id,
            category_id=category_id,
            support_role_id=support_role_id,
            log_channel_id=log_channel_id,
            naming_format=naming_format,
            button_label=button_label,
            button_style=button_style,
            button_emoji=button_emoji,
            created_by=created_by,
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

        return await self.repo.get_panel(guild_id, clean_name)

    async def get_panel_by_id(self, panel_id: int) -> dict[str, Any] | None:
        """Fetch a panel by panel ID across caches."""
        for g_panels in self._panels_cache.values():
            for p in g_panels:
                if p.get("id") == panel_id:
                    return p

        return await self.repo.get_panel_by_id(panel_id)

    async def get_panel_by_message(self, guild_id: int, message_id: int) -> dict[str, Any] | None:
        """Fetch a panel by its deployed message ID."""
        if guild_id in self._panels_cache:
            for p in self._panels_cache[guild_id]:
                if p.get("message_id") == message_id:
                    return p

        return await self.repo.get_panel_by_message(guild_id, message_id)

    async def list_panels(self, guild_id: int) -> list[dict[str, Any]]:
        """List all configured panels for a guild."""
        if guild_id in self._panels_cache:
            return list(self._panels_cache[guild_id])

        rows = await self.repo.list_panels(guild_id)
        self._panels_cache[guild_id] = rows
        return rows

    async def delete_panel(self, guild_id: int, panel_name: str) -> bool:
        """Delete a ticket panel from database and cache via repository."""
        clean_name = panel_name.lower().strip()
        await self.repo.delete_panel(guild_id, clean_name)
        if guild_id in self._panels_cache:
            self._panels_cache[guild_id] = [p for p in self._panels_cache[guild_id] if p["panel_name"] != clean_name]
        return True

    # ─── TICKET COUNTERS ──────────────────────────────────────────────────────

    async def get_next_ticket_number(self, guild_id: int) -> int:
        """Increment and return the next sequential ticket number for the guild."""
        return await self.repo.get_next_ticket_number(guild_id)

    # ─── ACTIVE TICKET OPERATIONS ─────────────────────────────────────────────

    async def create_ticket(
        self,
        guild_id: int,
        panel_id: int,
        channel_id: int,
        user_id: int,
        ticket_number: int,
    ) -> dict[str, Any]:
        """Record an open ticket in the database and cache via repository."""
        row = await self.repo.create_ticket(guild_id, panel_id, channel_id, user_id, ticket_number)
        if row:
            self._active_tickets_cache[channel_id] = row
        return row or {}

    async def get_ticket(self, channel_id: int) -> dict[str, Any] | None:
        """Get active ticket metadata by channel ID."""
        if channel_id in self._active_tickets_cache:
            return self._active_tickets_cache[channel_id]

        row = await self.repo.get_ticket(channel_id)
        if row and row.get("status") == "open":
            self._active_tickets_cache[channel_id] = row
        return row

    async def get_active_ticket_for_user(self, guild_id: int, user_id: int, panel_id: int | None = None) -> dict[str, Any] | None:
        """Check if user already has an open ticket for the specified panel or guild."""
        for t in self._active_tickets_cache.values():
            if t.get("guild_id") == guild_id and t.get("user_id") == user_id and t.get("status") == "open":
                if panel_id is None or t.get("panel_id") == panel_id:
                    return t

        return await self.repo.get_active_ticket_for_user(guild_id, user_id, panel_id)

    async def claim_ticket(self, channel_id: int, claimed_by: int) -> bool:
        """Set the claiming staff member for an active ticket."""
        await self.repo.claim_ticket(channel_id, claimed_by)
        if channel_id in self._active_tickets_cache:
            self._active_tickets_cache[channel_id]["claimed_by"] = claimed_by
        return True

    async def close_ticket(self, channel_id: int, closed_by: int) -> bool:
        """Mark an active ticket as closed."""
        await self.repo.close_ticket(channel_id, closed_by)
        if channel_id in self._active_tickets_cache:
            del self._active_tickets_cache[channel_id]
        return True
