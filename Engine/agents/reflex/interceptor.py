import re
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, List, Dict
from schemas.events import BaseEvent, MessageEvent, AuditEvent

@dataclass
class ReflexVerdict:
    is_threat: bool
    reason: Optional[str] = None
    action_suggested: Optional[str] = None
    execution_time_us: float = 0.0  # Microseconds


class ReflexInterceptor:
    """Stage 1: Ultra-fast compiled heuristic & rate-limiting reflex engine.
    Target SLA: < 500 microseconds execution time.
    """

    def __init__(self) -> None:
        # Pre-compile common malicious patterns
        self._invite_pattern = re.compile(
            r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/[a-zA-Z0-9]+",
            re.IGNORECASE
        )
        self._token_pattern = re.compile(r"[\w-]{24,26}\.[\w-]{6}\.[\w-]{27,38}")
        self._suspicious_phishing = re.compile(r"(?:nitro|steam|gift|airdrop|free-nitro)\w*\.(?:ru|xyz|gift|click|top)", re.IGNORECASE)

        # Sliding window trackers: guild_id:actor_id -> list of timestamps
        self._user_msg_timestamps: Dict[str, List[float]] = defaultdict(list)
        self._guild_audit_timestamps: Dict[str, List[float]] = defaultdict(list)

    def inspect_message(self, event: MessageEvent) -> ReflexVerdict:
        start = time.perf_counter_ns()
        actor_id = event.actor.id if event.actor else "unknown"
        key = f"{event.guild_id}:{actor_id}"
        now = time.time()

        # 1. Message Burst Detection (5 messages in 2 seconds)
        timestamps = self._user_msg_timestamps[key]
        timestamps.append(now)
        # Prune older than 2s
        cutoff = now - 2.0
        self._user_msg_timestamps[key] = [t for t in timestamps if t > cutoff]
        if len(self._user_msg_timestamps[key]) > 5:
            elapsed_us = (time.perf_counter_ns() - start) / 1000.0
            return ReflexVerdict(
                is_threat=True,
                reason="EXCESSIVE_MESSAGE_BURST",
                action_suggested="TIMEOUT_USER",
                execution_time_us=elapsed_us
            )

        # 2. Token Leak Scraper
        if self._token_pattern.search(event.content):
            elapsed_us = (time.perf_counter_ns() - start) / 1000.0
            return ReflexVerdict(
                is_threat=True,
                reason="TOKEN_LEAK_DETECTED",
                action_suggested="DELETE_AND_QUARANTINE",
                execution_time_us=elapsed_us
            )

        # 3. Phishing Links
        if self._suspicious_phishing.search(event.content):
            elapsed_us = (time.perf_counter_ns() - start) / 1000.0
            return ReflexVerdict(
                is_threat=True,
                reason="PHISHING_DOMAIN_DETECTED",
                action_suggested="DELETE_AND_BAN",
                execution_time_us=elapsed_us
            )

        elapsed_us = (time.perf_counter_ns() - start) / 1000.0
        return ReflexVerdict(is_threat=False, execution_time_us=elapsed_us)

    def inspect_audit(self, event: AuditEvent) -> ReflexVerdict:
        start = time.perf_counter_ns()
        now = time.time()
        actor_id = event.actor.id if event.actor else "unknown"
        key = f"{event.guild_id}:{actor_id}:{event.action_type}"

        # Track dangerous mass actions (e.g. 3 bans or kicks in 3 seconds)
        dangerous_actions = {"MEMBER_BAN_ADD", "MEMBER_KICK", "CHANNEL_DELETE", "ROLE_DELETE"}
        if event.action_type in dangerous_actions:
            timestamps = self._guild_audit_timestamps[key]
            timestamps.append(now)
            cutoff = now - 3.0
            self._guild_audit_timestamps[key] = [t for t in timestamps if t > cutoff]
            if len(self._guild_audit_timestamps[key]) >= 3:
                elapsed_us = (time.perf_counter_ns() - start) / 1000.0
                return ReflexVerdict(
                    is_threat=True,
                    reason=f"MASS_{event.action_type}_DETECTED",
                    action_suggested="STRIP_PERMISSIONS_AND_LOCK",
                    execution_time_us=elapsed_us
                )

        elapsed_us = (time.perf_counter_ns() - start) / 1000.0
        return ReflexVerdict(is_threat=False, execution_time_us=elapsed_us)
