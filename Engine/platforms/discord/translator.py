from typing import Dict, Any, Optional
from schemas.entities import PlatformSource, UserEntity, GuildEntity, RoleEntity, ChannelEntity
from schemas.events import MessageEvent, AuditEvent, ActionRequest

class DiscordTranslator:
    """Translates between Discord-specific payloads and universal Engine schemas.
    Maintains clean boundary so Engine core never imports or depends on Discord.py.
    """

    @staticmethod
    def parse_user(raw_user: Dict[str, Any]) -> UserEntity:
        return UserEntity(
            id=str(raw_user.get("id")),
            source=PlatformSource.DISCORD,
            username=raw_user.get("username", "Unknown"),
            display_name=raw_user.get("global_name") or raw_user.get("display_name"),
            avatar_url=raw_user.get("avatar_url"),
            is_bot=bool(raw_user.get("bot", False)),
            metadata={
                "discriminator": raw_user.get("discriminator", "0"),
                "flags": raw_user.get("public_flags", 0)
            }
        )

    @staticmethod
    def parse_guild(raw_guild: Dict[str, Any]) -> GuildEntity:
        return GuildEntity(
            id=str(raw_guild.get("id")),
            source=PlatformSource.DISCORD,
            name=raw_guild.get("name", "Unknown Server"),
            owner_id=str(raw_guild.get("owner_id", "")),
            member_count=int(raw_guild.get("member_count", 0)),
            icon_url=raw_guild.get("icon_url"),
            features=raw_guild.get("features", []),
            metadata={"preferred_locale": raw_guild.get("preferred_locale", "en-US")}
        )

    @staticmethod
    def to_message_event(payload: Dict[str, Any]) -> MessageEvent:
        actor_data = payload.get("actor") or payload.get("author") or {}
        actor = DiscordTranslator.parse_user(actor_data) if actor_data else None

        return MessageEvent(
            source=PlatformSource.DISCORD,
            guild_id=str(payload.get("guild_id")),
            channel_id=str(payload.get("channel_id")),
            content=payload.get("content", ""),
            actor=actor,
            attachments=payload.get("attachments", []),
            mentions=payload.get("mentions", []),
            is_edited=bool(payload.get("is_edited", False)),
            metadata=payload.get("metadata", {})
        )

    @staticmethod
    def to_audit_event(payload: Dict[str, Any]) -> AuditEvent:
        actor_data = payload.get("actor") or payload.get("user") or {}
        actor = DiscordTranslator.parse_user(actor_data) if actor_data else None

        return AuditEvent(
            source=PlatformSource.DISCORD,
            guild_id=str(payload.get("guild_id")),
            action_type=payload.get("action_type", "UNKNOWN"),
            target_id=str(payload.get("target_id", "")),
            actor=actor,
            reason=payload.get("reason"),
            changes=payload.get("changes", {}),
            metadata=payload.get("metadata", {})
        )
