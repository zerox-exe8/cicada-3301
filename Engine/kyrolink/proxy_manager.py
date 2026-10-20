import time
import random
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger("kyro.engine.kyrolink.proxy")

@dataclass
class ProxyNode:
    url: str
    failures: int = 0
    quarantined_until: float = 0.0
    total_requests: int = 0


class ProxyPoolManager:
    """Enterprise Rotating Proxy Pool with Self-Healing Quarantine.
    Rotates through Datacenter/Residential/SOCKS5 proxies and auto-heals blocked IPs.
    """

    def __init__(self, proxy_list: Optional[List[str]] = None) -> None:
        self._nodes: List[ProxyNode] = []
        if proxy_list:
            for p in proxy_list:
                self.add_proxy(p)
        self._current_index: int = 0

    def load_from_csv(self, proxy_csv: str) -> None:
        """Load multiple proxies from comma or newline separated string."""
        if not proxy_csv:
            return
        delimiters = [",", "\n", "\r\n"]
        raw_items = [proxy_csv]
        for d in delimiters:
            temp = []
            for item in raw_items:
                temp.extend(item.split(d))
            raw_items = temp
        for item in raw_items:
            self.add_proxy(item)

    def add_proxy(self, proxy_url: str) -> None:
        cleaned = proxy_url.strip()
        if cleaned and not any(n.url == cleaned for n in self._nodes):
            self._nodes.append(ProxyNode(url=cleaned))
            logger.info("[PROXY POOL] Added proxy node: %s", cleaned.split("@")[-1])

    def get_proxy(self) -> Optional[str]:
        """Returns the next healthy proxy using weighted round-robin."""
        if not self._nodes:
            return None

        now = time.time()
        # Filter healthy, unquarantined proxies
        healthy = [n for n in self._nodes if n.quarantined_until <= now]
        if not healthy:
            logger.warning("[PROXY POOL] All proxies quarantined! Resetting oldest proxy...")
            oldest = min(self._nodes, key=lambda n: n.quarantined_until)
            oldest.quarantined_until = 0.0
            return oldest.url

        node = healthy[self._current_index % len(healthy)]
        self._current_index += 1
        node.total_requests += 1
        return node.url

    def report_failure(self, proxy_url: str, is_ban: bool = True) -> None:
        """Report a 429/403 block to quarantine the proxy for 5 minutes."""
        now = time.time()
        for node in self._nodes:
            if node.url == proxy_url:
                node.failures += 1
                quarantine_duration = 300.0 if is_ban else 30.0
                node.quarantined_until = now + quarantine_duration
                logger.warning(
                    "[PROXY QUARANTINE] Proxy %s quarantined for %.0fs (Total Failures: %d)",
                    proxy_url.split("@")[-1], quarantine_duration, node.failures
                )
                break

    def report_success(self, proxy_url: str) -> None:
        for node in self._nodes:
            if node.url == proxy_url:
                if node.failures > 0:
                    node.failures -= 1
                break

    @property
    def total_proxies(self) -> int:
        return len(self._nodes)

    def stats(self) -> Dict[str, Any]:
        now = time.time()
        active = sum(1 for n in self._nodes if n.quarantined_until <= now)
        quarantined = len(self._nodes) - active
        return {
            "total": len(self._nodes),
            "active": active,
            "quarantined": quarantined,
            "nodes": [
                {
                    "host": n.url.split("@")[-1],
                    "failures": n.failures,
                    "is_quarantined": n.quarantined_until > now,
                    "quarantine_remaining_sec": max(0.0, round(n.quarantined_until - now, 1)),
                    "total_requests": n.total_requests
                }
                for n in self._nodes
            ]
        }
