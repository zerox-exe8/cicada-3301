from enum import StrEnum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class PlatformSource(StrEnum):
    DISCORD = "discord"
    TELEGRAM = "telegram"
    WEB = "web"
    WHATSAPP = "whatsapp"
    INTERNAL = "internal"

class UserEntity(BaseModel):
    id: str = Field(description="Platform-specific or UUID string identifier")
    source: PlatformSource
    username: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_bot: bool = False
    is_admin: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

class RoleEntity(BaseModel):
    id: str
    name: str
    permissions: int = 0
    position: int = 0
    color: int = 0

class ChannelEntity(BaseModel):
    id: str
    name: str
    is_voice: bool = False
    parent_id: Optional[str] = None

class GuildEntity(BaseModel):
    id: str = Field(description="Unique Guild or Community/Group ID")
    source: PlatformSource
    name: str
    owner_id: str
    member_count: int = 0
    icon_url: Optional[str] = None
    features: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
