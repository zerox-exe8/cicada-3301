import datetime
import logging
from enum import StrEnum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("kyro.engine.platforms.discord.actions")

class DiscordActionType(StrEnum):
    BAN_MEMBER = "BAN_MEMBER"
    KICK_MEMBER = "KICK_MEMBER"
    TIMEOUT_MEMBER = "TIMEOUT_MEMBER"
    REMOVE_TIMEOUT = "REMOVE_TIMEOUT"
    LOCK_CHANNEL = "LOCK_CHANNEL"
    UNLOCK_CHANNEL = "UNLOCK_CHANNEL"
    ASSIGN_ROLE = "ASSIGN_ROLE"
    REVOKE_ROLE = "REVOKE_ROLE"
    SEND_EMBED = "SEND_EMBED"


class DiscordActionResult(BaseModel):
    success: bool
    action: DiscordActionType
    guild_id: str
    target_id: Optional[str] = None
    discord_payload: Dict[str, Any] = Field(default_factory=dict)
    message: str = "Action prepared"


class DiscordActionExecutor:
    """Constructs and validates Discord-compliant action execution payloads."""

    @staticmethod
    def execute(
        action_name: str,
        guild_id: str,
        target_id: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> DiscordActionResult:
        params = params or {}
        action_upper = action_name.upper()

        if action_upper == DiscordActionType.BAN_MEMBER:
            delete_days = int(params.get("delete_message_days", 1))
            reason = params.get("reason", "Action enforced by Kyro Security Engine")
            return DiscordActionResult(
                success=True,
                action=DiscordActionType.BAN_MEMBER,
                guild_id=guild_id,
                target_id=target_id,
                discord_payload={
                    "user_id": target_id,
                    "delete_message_days": delete_days,
                    "reason": reason
                },
                message=f"Ban order prepared for user {target_id}"
            )

        elif action_upper == DiscordActionType.KICK_MEMBER:
            reason = params.get("reason", "Action enforced by Kyro Security Engine")
            return DiscordActionResult(
                success=True,
                action=DiscordActionType.KICK_MEMBER,
                guild_id=guild_id,
                target_id=target_id,
                discord_payload={"user_id": target_id, "reason": reason},
                message=f"Kick order prepared for user {target_id}"
            )

        elif action_upper == DiscordActionType.TIMEOUT_MEMBER:
            duration_seconds = int(params.get("duration_seconds", 300))  # Default 5 minutes
            until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=duration_seconds)
            reason = params.get("reason", "Auto-timeout by Kyro Engine")
            return DiscordActionResult(
                success=True,
                action=DiscordActionType.TIMEOUT_MEMBER,
                guild_id=guild_id,
                target_id=target_id,
                discord_payload={
                    "user_id": target_id,
                    "communication_disabled_until": until.isoformat(),
                    "reason": reason
                },
                message=f"Timeout prepared for user {target_id} until {until.isoformat()}"
            )

        elif action_upper == DiscordActionType.LOCK_CHANNEL:
            channel_id = params.get("channel_id") or target_id
            return DiscordActionResult(
                success=True,
                action=DiscordActionType.LOCK_CHANNEL,
                guild_id=guild_id,
                target_id=channel_id,
                discord_payload={
                    "channel_id": channel_id,
                    "permission_overwrites": [{"id": guild_id, "send_messages": False}]
                },
                message=f"Channel lock prepared for {channel_id}"
            )

        elif action_upper == DiscordActionType.ASSIGN_ROLE:
            role_id = params.get("role_id")
            return DiscordActionResult(
                success=True,
                action=DiscordActionType.ASSIGN_ROLE,
                guild_id=guild_id,
                target_id=target_id,
                discord_payload={"user_id": target_id, "role_id": role_id},
                message=f"Role {role_id} assignment prepared for user {target_id}"
            )

        # Fallback / Generic Action
        return DiscordActionResult(
            success=False,
            action=DiscordActionType.SEND_EMBED,
            guild_id=guild_id,
            target_id=target_id,
            message=f"Unsupported Discord action: {action_name}"
        )
