from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any
import discord

if TYPE_CHECKING:
    from src.database.base import BaseDatabase

logger = logging.getLogger("Kyro.AntinukeManager")

# Default modules enabled in antinuke
PROTECTION_MODULES = [
    "vanity",
    "everyone",
    "role",
    "channel",
    "ban",
    "kick",
    "bot",
    "webhook",
    "prune",
    "automod",
    "integration",
    "emoji",
    "sticker",
    "guild_update",
    "channel_create",
    "channel_delete",
    "channel_update",
    "role_create",
    "role_delete",
    "role_update",
    "webhook_create",
    "webhook_delete",
    "member_role",
]


class AntinukeManager:
    """Zero-latency in-memory security and antinuke state management."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        # guild_id -> settings dict
        self._settings: dict[int, dict[str, Any]] = {}
        # guild_id -> {user_id: {"is_extra_owner": bool, "is_full": bool, "scope": set[str]}}
        self._whitelist: dict[int, dict[int, dict[str, Any]]] = {}
        # guild_id -> {role_id: {"is_full": bool, "scope": set[str]}}
        self._role_whitelist: dict[int, dict[int, dict[str, Any]]] = {}
        # Rate-limiting sliding window: key -> list of float timestamps
        self._action_history: dict[str, list[float]] = {}
        # Channel snapshots: guild_id -> {channel_id: dict_metadata}
        self._channel_cache: dict[int, dict[int, dict[str, Any]]] = {}
        # Role snapshots: guild_id -> {role_id: dict_metadata}
        self._role_cache: dict[int, dict[int, dict[str, Any]]] = {}
        # Vanity code cache: guild_id -> vanity_str
        self._vanity_cache: dict[int, str | None] = {}

    async def load_cache(self) -> None:
        """Load all guild antinuke configurations and whitelists into memory."""
        # 1. Load settings
        settings_rows = await self.db.fetch_all("SELECT * FROM antinuke_settings;")
        for row in settings_rows:
            g_id = int(row["guild_id"])
            ch_prot = bool(row.get("channel_protection", True))
            r_prot = bool(row.get("role_protection", True))
            wh_prot = bool(row.get("webhook_protection", True))

            self._settings[g_id] = {
                "enabled": bool(row.get("enabled", False)),
                "log_channel_id": row.get("log_channel_id"),
                "punishment": row.get("punishment", "strip_roles"),
                "vanity_protection": bool(row.get("vanity_protection", True)),
                "everyone_protection": bool(row.get("everyone_protection", True)),
                "role_protection": r_prot,
                "channel_protection": ch_prot,
                "ban_protection": bool(row.get("ban_protection", True)),
                "kick_protection": bool(row.get("kick_protection", True)),
                "bot_protection": bool(row.get("bot_protection", True)),
                "webhook_protection": wh_prot,
                "prune_protection": bool(row.get("prune_protection", True)),
                "automod_protection": bool(row.get("automod_protection", True)),
                "integration_protection": bool(row.get("integration_protection", True)),
                "emoji_protection": bool(row.get("emoji_protection", True)),
                "sticker_protection": bool(row.get("sticker_protection", True)),
                "guild_update_protection": bool(row.get("guild_update_protection", True)),
                "channel_create_protection": bool(row.get("channel_create_protection", ch_prot)),
                "channel_delete_protection": bool(row.get("channel_delete_protection", ch_prot)),
                "channel_update_protection": bool(row.get("channel_update_protection", ch_prot)),
                "role_create_protection": bool(row.get("role_create_protection", r_prot)),
                "role_delete_protection": bool(row.get("role_delete_protection", r_prot)),
                "role_update_protection": bool(row.get("role_update_protection", r_prot)),
                "webhook_create_protection": bool(row.get("webhook_create_protection", wh_prot)),
                "webhook_delete_protection": bool(row.get("webhook_delete_protection", wh_prot)),
                "member_role_protection": bool(row.get("member_role_protection", True)),
            }

        # 2. Load whitelists
        wl_rows = await self.db.fetch_all("SELECT * FROM antinuke_whitelist;")
        for row in wl_rows:
            g_id = int(row["guild_id"])
            u_id = int(row["user_id"])
            if g_id not in self._whitelist:
                self._whitelist[g_id] = {}

            scope_str = row.get("scope") or ""
            scope_set = {s.strip().lower() for s in scope_str.split(",") if s.strip()}
            self._whitelist[g_id][u_id] = {
                "is_extra_owner": bool(row.get("is_extra_owner", False)),
                "is_full": bool(row.get("is_full", True)),
                "scope": scope_set,
            }

        # 3. Load role whitelists
        role_wl_rows = await self.db.fetch_all("SELECT * FROM antinuke_role_whitelist;")
        for row in role_wl_rows:
            g_id = int(row["guild_id"])
            r_id = int(row["role_id"])
            if g_id not in self._role_whitelist:
                self._role_whitelist[g_id] = {}

            scope_str = row.get("scope") or ""
            scope_set = {s.strip().lower() for s in scope_str.split(",") if s.strip()}
            self._role_whitelist[g_id][r_id] = {
                "is_full": bool(row.get("is_full", True)),
                "scope": scope_set,
            }

        logger.info(
            f"Loaded antinuke configs for {len(self._settings)} guild(s), {len(wl_rows)} whitelisted entity/entities "
            f"and {len(role_wl_rows)} whitelisted role(s) into memory."
        )

    # ------------------ SETTINGS METHODS ------------------

    def is_enabled(self, guild_id: int) -> bool:
        """Check if antinuke master switch is enabled for a guild."""
        return self._settings.get(guild_id, {}).get("enabled", False)

    def get_settings(self, guild_id: int) -> dict[str, Any]:
        """Get the configuration dictionary for a guild (defaults applied if unset)."""
        if guild_id not in self._settings:
            return {
                "enabled": False,
                "log_channel_id": None,
                "punishment": "strip_roles",
                "vanity_protection": True,
                "everyone_protection": True,
                "role_protection": True,
                "channel_protection": True,
                "ban_protection": True,
                "kick_protection": True,
                "bot_protection": True,
                "webhook_protection": True,
                "prune_protection": True,
                "automod_protection": True,
                "integration_protection": True,
                "emoji_protection": True,
                "sticker_protection": True,
                "guild_update_protection": True,
                "channel_create_protection": True,
                "channel_delete_protection": True,
                "channel_update_protection": True,
                "role_create_protection": True,
                "role_delete_protection": True,
                "role_update_protection": True,
                "webhook_create_protection": True,
                "webhook_delete_protection": True,
                "member_role_protection": True,
            }
        return self._settings[guild_id]

    def is_module_enabled(self, guild_id: int, module_name: str) -> bool:
        """Check if a specific sub-protection module is active."""
        if not self.is_enabled(guild_id):
            return False
        cfg = self.get_settings(guild_id)
        key = f"{module_name}_protection"
        if key in cfg:
            return bool(cfg[key])
        for parent in ["channel", "role", "webhook", "automod"]:
            if module_name.startswith(parent):
                return bool(cfg.get(f"{parent}_protection", True))
        return True

    def get_punishment(self, guild_id: int) -> str:
        """Get the configured punishment action ('ban', 'kick', 'strip_roles')."""
        return self.get_settings(guild_id).get("punishment", "ban")

    def get_log_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Resolve the text channel bound for antinuke security alerts."""
        cfg = self.get_settings(guild.id)
        cid = cfg.get("log_channel_id")
        if not cid:
            return None
        return guild.get_channel(cid)

    async def update_settings(self, guild_id: int, **kwargs: Any) -> None:
        """Persist updated settings to DB and memory cache."""
        if guild_id not in self._settings:
            self._settings[guild_id] = self.get_settings(guild_id)

        self._settings[guild_id].update(kwargs)
        cfg = self._settings[guild_id]

        cols = [
            "guild_id",
            "enabled",
            "log_channel_id",
            "punishment",
            "vanity_protection",
            "everyone_protection",
            "role_protection",
            "channel_protection",
            "ban_protection",
            "kick_protection",
            "bot_protection",
            "webhook_protection",
            "prune_protection",
            "automod_protection",
            "integration_protection",
            "emoji_protection",
            "sticker_protection",
            "guild_update_protection",
            "channel_create_protection",
            "channel_delete_protection",
            "channel_update_protection",
            "role_create_protection",
            "role_delete_protection",
            "role_update_protection",
            "webhook_create_protection",
            "webhook_delete_protection",
            "member_role_protection",
        ]

        vals = [guild_id] + [cfg.get(c) for c in cols[1:]]
        placeholders = ", ".join(["?"] * len(cols))
        updates = ", ".join([f"{c} = excluded.{c}" for c in cols[1:]])

        query = f"""
        INSERT INTO antinuke_settings ({', '.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(guild_id) DO UPDATE SET {updates};
        """
        await self.db.execute(query, *vals)

    # ------------------ WHITELIST & IMMUNITY METHODS ------------------

    def is_immune(self, guild: discord.Guild, user_id: int, module_name: str = "") -> bool:
        """
        Microsecond immunity evaluation:
        1. Server Owner is ALWAYS immune (hardcoded, cannot be bypassed).
        2. Bot itself is immune.
        3. Extra Owners have full immunity.
        4. Whitelisted members: full immunity or module-specific scoped immunity.
        """
        if user_id == guild.owner_id:
            return True

        if guild.me and user_id == guild.me.id:
            return True

        guild_wl = self._whitelist.get(guild.id, {})
        entry = guild_wl.get(user_id)
        if entry:
            if entry.get("is_extra_owner"):
                return True

            if entry.get("is_full"):
                return True

            if module_name:
                m_low = module_name.lower()
                scope = entry.get("scope", set())
                if m_low in scope or m_low.split("_")[0] in scope:
                    return True

        # Role-based immunity: any whitelisted role held by the member grants immunity.
        role_wl = self._role_whitelist.get(guild.id, {})
        if role_wl:
            member = guild.get_member(user_id)
            if member is not None:
                for role in member.roles:
                    r_entry = role_wl.get(role.id)
                    if not r_entry:
                        continue
                    if r_entry.get("is_full"):
                        return True
                    if module_name:
                        m_low = module_name.lower()
                        r_scope = r_entry.get("scope", set())
                        if m_low in r_scope or m_low.split("_")[0] in r_scope:
                            return True

        return False

    def is_extra_owner(self, guild_id: int, user_id: int) -> bool:
        """Check if user has Extra Owner privileges."""
        entry = self._whitelist.get(guild_id, {}).get(user_id)
        return bool(entry and entry.get("is_extra_owner"))

    def get_extra_owners(self, guild_id: int) -> list[int]:
        """List user IDs of all Extra Owners for a guild."""
        guild_wl = self._whitelist.get(guild_id, {})
        return [uid for uid, data in guild_wl.items() if data.get("is_extra_owner")]

    def get_whitelist(self, guild_id: int) -> dict[int, dict[str, Any]]:
        """Return full whitelist registry for a guild."""
        return self._whitelist.get(guild_id, {})

    async def add_extra_owner(self, guild_id: int, user_id: int, added_by: int) -> None:
        """Promote a user to Extra Owner."""
        if guild_id not in self._whitelist:
            self._whitelist[guild_id] = {}

        self._whitelist[guild_id][user_id] = {
            "is_extra_owner": True,
            "is_full": True,
            "scope": set(),
        }

        await self.db.execute(
            """
            INSERT INTO antinuke_whitelist (guild_id, user_id, is_extra_owner, is_full, scope, added_by)
            VALUES (?, ?, TRUE, TRUE, '', ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET is_extra_owner = TRUE, is_full = TRUE;
            """,
            guild_id,
            user_id,
            added_by,
        )

    async def remove_extra_owner(self, guild_id: int, user_id: int) -> None:
        """Demote an Extra Owner back to normal or remove completely."""
        if guild_id in self._whitelist and user_id in self._whitelist[guild_id]:
            entry = self._whitelist[guild_id][user_id]
            if entry.get("scope"):
                entry["is_extra_owner"] = False
                await self.db.execute(
                    "UPDATE antinuke_whitelist SET is_extra_owner = FALSE WHERE guild_id = ? AND user_id = ?;",
                    guild_id,
                    user_id,
                )
                return
            self._whitelist[guild_id].pop(user_id)

        await self.db.execute(
            "DELETE FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ?;",
            guild_id,
            user_id,
        )

    async def add_whitelist(
        self, guild_id: int, user_id: int, added_by: int, is_full: bool = True, scope: str = ""
    ) -> None:
        """Add user/bot to whitelist with either full access or granular scoped modules."""
        if guild_id not in self._whitelist:
            self._whitelist[guild_id] = {}

        clean_scope = {s.strip().lower() for s in scope.split(",") if s.strip()}
        existing = self._whitelist[guild_id].get(user_id, {})

        self._whitelist[guild_id][user_id] = {
            "is_extra_owner": existing.get("is_extra_owner", False),
            "is_full": is_full,
            "scope": clean_scope,
        }

        scope_str = ",".join(clean_scope)
        await self.db.execute(
            """
            INSERT INTO antinuke_whitelist (guild_id, user_id, is_extra_owner, is_full, scope, added_by)
            VALUES (?, ?, FALSE, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET is_full = excluded.is_full, scope = excluded.scope;
            """,
            guild_id,
            user_id,
            is_full,
            scope_str,
            added_by,
        )

    async def remove_whitelist(self, guild_id: int, user_id: int) -> None:
        """Remove a user or bot from the whitelist completely."""
        if guild_id in self._whitelist and user_id in self._whitelist[guild_id]:
            # Keep extra owner flag if they are one
            if self._whitelist[guild_id][user_id].get("is_extra_owner"):
                self._whitelist[guild_id][user_id]["is_full"] = True
                self._whitelist[guild_id][user_id]["scope"] = set()
                return
            self._whitelist[guild_id].pop(user_id)

        await self.db.execute(
            "DELETE FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ? AND is_extra_owner = FALSE;",
            guild_id,
            user_id,
        )

    def get_role_whitelist(self, guild_id: int) -> dict[int, dict[str, Any]]:
        """Return whitelisted roles registry for a guild."""
        return self._role_whitelist.get(guild_id, {})

    async def add_role_whitelist(
        self, guild_id: int, role_id: int, added_by: int, is_full: bool = True, scope: str = ""
    ) -> None:
        """Whitelist a role — every member holding it inherits immunity."""
        if guild_id not in self._role_whitelist:
            self._role_whitelist[guild_id] = {}

        clean_scope = {s.strip().lower() for s in scope.split(",") if s.strip()}
        self._role_whitelist[guild_id][role_id] = {
            "is_full": is_full,
            "scope": clean_scope,
        }

        scope_str = ",".join(clean_scope)
        await self.db.execute(
            """
            INSERT INTO antinuke_role_whitelist (guild_id, role_id, is_full, scope, added_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, role_id) DO UPDATE SET is_full = excluded.is_full, scope = excluded.scope;
            """,
            guild_id,
            role_id,
            is_full,
            scope_str,
            added_by,
        )

    async def remove_role_whitelist(self, guild_id: int, role_id: int) -> None:
        """Remove a role from the whitelist."""
        if guild_id in self._role_whitelist and role_id in self._role_whitelist[guild_id]:
            self._role_whitelist[guild_id].pop(role_id)

        await self.db.execute(
            "DELETE FROM antinuke_role_whitelist WHERE guild_id = ? AND role_id = ?;",
            guild_id,
            role_id,
        )

    # ------------------ SLIDING WINDOW RATE LIMITER ------------------

    def check_rate_limit(
        self, guild_id: int, user_id: int, action_type: str, max_allowed: int = 3, window_seconds: float = 8.0
    ) -> bool:
        """
        Sliding-window rate limiter to catch rapid mass attacks.
        Returns True if threshold is EXCEEDED (attack detected).
        """
        now = time.monotonic()
        key = f"{guild_id}:{user_id}:{action_type}"
        history = self._action_history.get(key, [])

        # Filter out timestamps outside the active window
        valid_history = [ts for ts in history if now - ts <= window_seconds]
        valid_history.append(now)
        self._action_history[key] = valid_history

        return len(valid_history) >= max_allowed

    def reset_rate_limit(self, guild_id: int, user_id: int, action_type: str) -> None:
        """Clear rate limit counter after an action is processed."""
        key = f"{guild_id}:{user_id}:{action_type}"
        self._action_history.pop(key, None)

    # ------------------ IN-MEMORY SNAPSHOTS (SELF-HEALING) ------------------

    def snapshot_guild_state(self, guild: discord.Guild) -> None:
        """Cache all channels, roles, and vanity URL in memory for instant restoration."""
        # 1. Channels snapshot
        ch_map: dict[int, dict[str, Any]] = {}
        for ch in guild.channels:
            ch_map[ch.id] = {
                "name": ch.name,
                "type": ch.type,
                "category_id": ch.category_id,
                "position": ch.position,
                "topic": getattr(ch, "topic", None),
                "nsfw": getattr(ch, "nsfw", False),
                "overwrites": {target.id: (target, ow) for target, ow in ch.overwrites.items()},
            }
        self._channel_cache[guild.id] = ch_map

        # 2. Roles snapshot
        r_map: dict[int, dict[str, Any]] = {}
        for r in guild.roles:
            if r.is_default():
                continue
            r_map[r.id] = {
                "name": r.name,
                "permissions": r.permissions,
                "color": r.color,
                "hoist": r.hoist,
                "mentionable": r.mentionable,
                "position": r.position,
            }
        self._role_cache[guild.id] = r_map

        # 3. Vanity snapshot
        self._vanity_cache[guild.id] = getattr(guild, "vanity_url_code", None)

    def get_cached_channel(self, guild_id: int, channel_id: int) -> dict[str, Any] | None:
        """Get cached channel structure prior to deletion."""
        return self._channel_cache.get(guild_id, {}).get(channel_id)

    def get_cached_role(self, guild_id: int, role_id: int) -> dict[str, Any] | None:
        """Get cached role structure prior to deletion."""
        return self._role_cache.get(guild_id, {}).get(role_id)

    def get_cached_vanity(self, guild_id: int) -> str | None:
        """Get legitimate cached vanity code."""
        return self._vanity_cache.get(guild_id)

    def update_cached_vanity(self, guild_id: int, vanity_code: str | None) -> None:
        """Update cached legitimate vanity code."""
        self._vanity_cache[guild_id] = vanity_code
