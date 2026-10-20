import time
import uuid
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from config.constants import EventPriority, OpCode
from schemas.entities import PlatformSource, UserEntity

class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = Field(default_factory=time.time)
    opcode: OpCode = OpCode.EVENT_DISPATCH
    priority: EventPriority = EventPriority.NORMAL
    source: PlatformSource = PlatformSource.INTERNAL
    guild_id: str = Field(description="Tenant or Guild ID for actor partitioning")
    actor: Optional[UserEntity] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class MessageEvent(BaseEvent):
    channel_id: str
    content: str
    attachments: List[str] = Field(default_factory=list)
    mentions: List[str] = Field(default_factory=list)
    is_edited: bool = False

class AuditEvent(BaseEvent):
    action_type: str = Field(description="e.g. MEMBER_BAN, CHANNEL_DELETE, ROLE_CREATE")
    target_id: str
    reason: Optional[str] = None
    changes: Dict[str, Any] = Field(default_factory=dict)

class ActionRequest(BaseEvent):
    action_name: str = Field(description="e.g. BAN_MEMBER, QUARANTINE, MUTE, PLAY_TRACK")
    target_id: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
