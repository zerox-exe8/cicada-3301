from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class IncidentSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class SubsystemType(str, Enum):
    VOICE = "VOICE"
    MUSIC = "MUSIC"
    DATABASE = "DATABASE"
    GATEWAY = "GATEWAY"
    COMMAND = "COMMAND"


@dataclass
class Incident:
    id: str
    subsystem: SubsystemType
    severity: IncidentSeverity
    title: str
    details: str
    guild_id: Optional[int] = None
    action_taken: str = ""
    resolved: bool = True
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def formatted_time(self) -> str:
        return self.timestamp.strftime("%H:%M:%S UTC")
