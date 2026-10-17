from __future__ import annotations

import asyncio
import datetime
import logging
import random
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyro.Managers.Giveaway")


class GiveawayManager:
    """
    Manages active server giveaways, fair participant tracking,
    anti-race database persistence, and automated winner selection.
    """

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # message_id -> giveaway dict
        self._active_giveaways: dict[int, dict[str, Any]] = {}
        # giveaway_id -> message_id index
        self._id_to_message_id: dict[int, int] = {}
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load all currently active (unended) giveaways into memory cache."""
        try:
            rows = await self.db.fetch_all(
                "SELECT * FROM giveaways WHERE is_ended = FALSE ORDER BY ends_at ASC;"
            )
            async with self._lock:
                self._active_giveaways.clear()
                self._id_to_message_id.clear()
                for r in rows:
                    mid = int(r["message_id"])
                    gid = int(r["id"])
                    data = {
                        "id": gid,
                        "guild_id": int(r["guild_id"]),
                        "channel_id": int(r["channel_id"]),
                        "message_id": mid,
                        "host_id": int(r["host_id"]),
                        "prize": str(r["prize"]),
                        "winner_count": int(r.get("winner_count", 1)),
                        "ends_at": r["ends_at"],
                        "required_role_id": int(r["required_role_id"]) if r.get("required_role_id") else None,
                        "is_ended": False,
                    }
                    self._active_giveaways[mid] = data
                    self._id_to_message_id[gid] = mid

            logger.info(f"Loaded {len(self._active_giveaways)} active giveaway(s) into memory cache.")
        except Exception as e:
            logger.error(f"Failed to load active giveaways cache: {e}", exc_info=e)

    def get_giveaway_by_message_id(self, message_id: int) -> Optional[dict[str, Any]]:
        """Retrieve giveaway data by Discord message ID."""
        return self._active_giveaways.get(message_id)

    def get_giveaway_by_id(self, giveaway_id: int) -> Optional[dict[str, Any]]:
        """Retrieve giveaway data by database ID."""
        mid = self._id_to_message_id.get(giveaway_id)
        if mid:
            return self._active_giveaways.get(mid)
        return None

    def get_active_giveaways_for_guild(self, guild_id: int) -> list[dict[str, Any]]:
        """Return all ongoing giveaways within a specific server."""
        return [g for g in self._active_giveaways.values() if g["guild_id"] == guild_id]

    def get_due_giveaways(self) -> list[dict[str, Any]]:
        """Return all giveaways whose duration has expired and need winner determination."""
        now = datetime.datetime.now(datetime.timezone.utc)
        due = []
        for g in self._active_giveaways.values():
            end_t = g["ends_at"]
            if end_t.tzinfo is None:
                end_t = end_t.replace(tzinfo=datetime.timezone.utc)
            if end_t <= now:
                due.append(g)
        return due

    async def create_giveaway(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        host_id: int,
        prize: str,
        winner_count: int,
        ends_at: datetime.datetime,
        required_role_id: Optional[int] = None,
    ) -> int:
        """Register a new giveaway in the database and activate it in memory."""
        row = await self.db.fetch_one(
            """
            INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, prize, winner_count, ends_at, required_role_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id;
            """,
            guild_id,
            channel_id,
            message_id,
            host_id,
            prize,
            winner_count,
            ends_at,
            required_role_id,
        )
        giveaway_id = int(row["id"])

        data = {
            "id": giveaway_id,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
            "host_id": host_id,
            "prize": prize,
            "winner_count": winner_count,
            "ends_at": ends_at,
            "required_role_id": required_role_id,
            "is_ended": False,
        }

        async with self._lock:
            self._active_giveaways[message_id] = data
            self._id_to_message_id[giveaway_id] = message_id

        return giveaway_id

    async def toggle_participant(self, giveaway_id: int, user_id: int) -> tuple[bool, str, int]:
        """
        Atomically add or remove a participant from a giveaway.
        Returns: (success: bool, action: 'entered' | 'left', total_entries: int)
        """
        # Check existing entry
        existing = await self.db.fetch_one(
            "SELECT 1 FROM giveaway_participants WHERE giveaway_id = $1 AND user_id = $2;",
            giveaway_id,
            user_id,
        )

        if existing:
            # Withdraw user
            await self.db.execute(
                "DELETE FROM giveaway_participants WHERE giveaway_id = $1 AND user_id = $2;",
                giveaway_id,
                user_id,
            )
            count = await self.get_participant_count(giveaway_id)
            return True, "left", count
        else:
            # Enter user
            await self.db.execute(
                """
                INSERT INTO giveaway_participants (giveaway_id, user_id)
                VALUES ($1, $2)
                ON CONFLICT (giveaway_id, user_id) DO NOTHING;
                """,
                giveaway_id,
                user_id,
            )
            count = await self.get_participant_count(giveaway_id)
            return True, "entered", count

    async def get_participant_count(self, giveaway_id: int) -> int:
        """Fetch total unique participants currently entered in this giveaway."""
        row = await self.db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM giveaway_participants WHERE giveaway_id = $1;",
            giveaway_id,
        )
        return int(row["cnt"]) if row else 0

    async def get_participants(self, giveaway_id: int) -> list[int]:
        """Fetch all user IDs entered into the giveaway."""
        rows = await self.db.fetch_all(
            "SELECT user_id FROM giveaway_participants WHERE giveaway_id = $1;",
            giveaway_id,
        )
        return [int(r["user_id"]) for r in rows]

    async def end_giveaway(self, message_id: int) -> Optional[dict[str, Any]]:
        """
        Finalize giveaway: select random winner(s), update PostgreSQL state,
        and evict from in-memory active cache.
        """
        # Fetch from active cache or DB if already evicted
        gw = self.get_giveaway_by_message_id(message_id)
        if not gw:
            gw_row = await self.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", message_id)
            if not gw_row:
                return None
            gw = {
                "id": int(gw_row["id"]),
                "guild_id": int(gw_row["guild_id"]),
                "channel_id": int(gw_row["channel_id"]),
                "message_id": int(gw_row["message_id"]),
                "host_id": int(gw_row["host_id"]),
                "prize": str(gw_row["prize"]),
                "winner_count": int(gw_row.get("winner_count", 1)),
                "ends_at": gw_row["ends_at"],
                "required_role_id": int(gw_row["required_role_id"]) if gw_row.get("required_role_id") else None,
                "is_ended": bool(gw_row.get("is_ended", False)),
            }

        giveaway_id = gw["id"]

        # Mark ended in DB
        await self.db.execute(
            "UPDATE giveaways SET is_ended = TRUE WHERE id = $1;",
            giveaway_id,
        )

        async with self._lock:
            self._active_giveaways.pop(message_id, None)
            self._id_to_message_id.pop(giveaway_id, None)

        # Draw winners
        participants = await self.get_participants(giveaway_id)
        winner_count = gw["winner_count"]

        if not participants:
            winners = []
        elif len(participants) <= winner_count:
            winners = participants
            random.shuffle(winners)
        else:
            winners = random.sample(participants, winner_count)

        result = dict(gw)
        result["is_ended"] = True
        result["winners"] = winners
        result["total_entries"] = len(participants)
        return result

    async def reroll_giveaway(self, message_id: int, count: int = 1) -> Optional[tuple[dict[str, Any], list[int]]]:
        """Select new random winner(s) from participants of an existing giveaway."""
        gw_row = await self.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", message_id)
        if not gw_row:
            return None

        giveaway_id = int(gw_row["id"])
        participants = await self.get_participants(giveaway_id)

        if not participants:
            return gw_row, []

        pick_count = min(count, len(participants))
        new_winners = random.sample(participants, pick_count)
        return dict(gw_row), new_winners
