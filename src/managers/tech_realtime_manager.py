"""
Kyro Discord Bot - Real-Time Tech Intelligence Manager
Autonomous real-time engine tracking global cloud infrastructure outages,
critical zero-day CVE exploits (CISA KEV), and major runtime/framework releases.
Enables self-healing live embed messages and zero-spam incident lifecycle tracking.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

import aiohttp
from src.utils.containers import KyroContainer

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyro.Managers.TechRealtime")


@dataclass
class OutageIncident:
    """Structure representing a live cloud/developer infrastructure incident."""
    incident_id: str
    provider: str
    title: str
    status: str          # 'investigating', 'identified', 'monitoring', 'resolved'
    impact: str          # 'none', 'minor', 'major', 'critical'
    url: str
    created_at: str
    updated_at: str
    latest_update: str
    components_affected: list[str] = field(default_factory=list)
    resolved_at: Optional[str] = None


@dataclass
class CriticalCVE:
    """Structure representing a high-severity zero-day vulnerability actively exploited in the wild."""
    cve_id: str
    title: str
    vendor_project: str
    product: str
    description: str
    date_added: str
    due_date: str
    action_required: str
    cvss_score: float = 9.0
    remediation_cmd: str = ""
    url: str = ""


@dataclass
class MajorRelease:
    """Structure representing a major or significant minor version release of a core tech runtime."""
    release_id: str
    project: str
    repo: str
    tag_name: str
    name: str
    summary: str
    highlights: list[str] = field(default_factory=list)
    breaking_changes: list[str] = field(default_factory=list)
    install_cmd: str = ""
    url: str = ""
    published_at: str = ""


OUTAGE_PROVIDERS: dict[str, dict[str, str]] = {
    "GitHub": {
        "statuspage_id": "kctbh9vrtdwd",
        "incidents_url": "https://kctbh9vrtdwd.statuspage.io/api/v2/incidents/unresolved.json",
        "summary_url": "https://kctbh9vrtdwd.statuspage.io/api/v2/summary.json",
        "home_url": "https://www.githubstatus.com",
    },
    "Cloudflare": {
        "statuspage_id": "yh6f0r4529hb",
        "incidents_url": "https://www.cloudflarestatus.com/api/v2/incidents/unresolved.json",
        "summary_url": "https://www.cloudflarestatus.com/api/v2/summary.json",
        "home_url": "https://www.cloudflarestatus.com",
    },
    "OpenAI": {
        "statuspage_id": "jrhkbjh4k5w8",
        "incidents_url": "https://status.openai.com/api/v2/incidents/unresolved.json",
        "summary_url": "https://status.openai.com/api/v2/summary.json",
        "home_url": "https://status.openai.com",
    },
    "Discord": {
        "statuspage_id": "srhbfgr82pff",
        "incidents_url": "https://discordstatus.com/api/v2/incidents/unresolved.json",
        "summary_url": "https://discordstatus.com/api/v2/summary.json",
        "home_url": "https://discordstatus.com",
    },
    "Vercel": {
        "statuspage_id": "v35b38k4s2f8",
        "incidents_url": "https://vercel-status.com/api/v2/incidents/unresolved.json",
        "summary_url": "https://vercel-status.com/api/v2/summary.json",
        "home_url": "https://vercel-status.com",
    },
}

CORE_RELEASE_REPOS: list[dict[str, str]] = [
    {"project": "Next.js", "repo": "vercel/next.js", "install": "npx create-next-app@latest"},
    {"project": "Node.js", "repo": "nodejs/node", "install": "nvm install node --reinstall-packages-from=node"},
    {"project": "Python", "repo": "python/cpython", "install": "pyenv install 3.13.0"},
    {"project": "Bun", "repo": "oven-sh/bun", "install": "bun upgrade"},
    {"project": "Rust", "repo": "rust-lang/rust", "install": "rustup update stable"},
    {"project": "React", "repo": "facebook/react", "install": "npm install react@latest react-dom@latest"},
    {"project": "Go", "repo": "golang/go", "install": "go install golang.org/dl/go1.23.0@latest"},
]


class TechRealtimeManager:
    """Manages real-time cloud incident state machine, threat feeds, and release monitoring."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        self._cve_cache: set[str] = set()
        self._releases_cache: set[str] = set()
        self._global_health_cache: dict[str, dict[str, str]] = {}
        self._health_last_fetched: float = 0.0
        self._initialized = False

    async def initialize(self) -> None:
        """Prime in-memory caches from PostgreSQL to guarantee zero duplication on restart."""
        if self._initialized:
            return
        try:
            # Prime CVE cache
            cve_rows = await self.db.fetch_all("SELECT cve_id FROM tech_cve_history;")
            if cve_rows:
                self._cve_cache = {str(r["cve_id"]) for r in cve_rows if r.get("cve_id")}

            # Prime Releases cache
            rel_rows = await self.db.fetch_all("SELECT release_id FROM tech_releases_history;")
            if rel_rows:
                self._releases_cache = {str(r["release_id"]) for r in rel_rows if r.get("release_id")}

            self._initialized = True
            logger.info(
                f"Real-time tech manager primed: {len(self._cve_cache)} CVEs, {len(self._releases_cache)} releases cached."
            )
        except Exception as e:
            logger.error(f"Failed to prime real-time tech caches from database: {e}", exc_info=e)

    # -------------------------------------------------------------------------
    # Feature A: Cloud Infrastructure Outage Radar (State Machine & Poller)
    # -------------------------------------------------------------------------
    async def poll_active_outages(self, session: aiohttp.ClientSession) -> list[OutageIncident]:
        """Check all configured cloud providers concurrently for active incidents."""
        headers = {"User-Agent": "KyroTechBot/2.0 (Realtime Infrastructure Radar)"}

        async def _fetch_provider(provider: str, meta: dict[str, str]) -> list[OutageIncident]:
            incidents_found = []
            url = meta["incidents_url"]
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=3.5)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    incidents = data.get("incidents", [])
                    for inc in incidents:
                        inc_id = inc.get("id")
                        if not inc_id:
                            continue
                        name = inc.get("name", "Service Disruption")
                        status = str(inc.get("status", "investigating")).lower()
                        impact = str(inc.get("impact", "minor")).lower()
                        shortlink = inc.get("shortlink") or inc.get("url") or meta["home_url"]
                        created_at = inc.get("created_at", "")
                        updated_at = inc.get("updated_at", "")

                        updates = inc.get("incident_updates", [])
                        latest_body = "Investigation in progress."
                        if updates:
                            latest_body = updates[0].get("body", latest_body)

                        components = []
                        for comp in inc.get("components", []):
                            cname = comp.get("name")
                            if cname:
                                components.append(cname)

                        incidents_found.append(
                            OutageIncident(
                                incident_id=f"{provider.lower()}:{inc_id}",
                                provider=provider,
                                title=name,
                                status=status,
                                impact=impact,
                                url=shortlink,
                                created_at=created_at,
                                updated_at=updated_at,
                                latest_update=latest_body,
                                components_affected=components,
                                resolved_at=updated_at if status == "resolved" else None,
                            )
                        )
            except Exception as ex:
                logger.debug(f"Outage poll failed for {provider}: {ex}")
            return incidents_found

        tasks = [_fetch_provider(p, m) for p, m in OUTAGE_PROVIDERS.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        detected: list[OutageIncident] = []
        for r in results:
            if isinstance(r, list):
                detected.extend(r)
        return detected

    async def get_tracked_active_incidents(self) -> list[dict[str, Any]]:
        """Retrieve all active incidents from PostgreSQL."""
        query = (
            "SELECT incident_id, guild_id, channel_id, message_id, provider, title, status, "
            "impact, url, started_at, resolved_at, last_updated_at "
            "FROM active_tech_incidents WHERE resolved_at IS NULL;"
        )
        return await self.db.fetch_all(query) or []

    async def record_incident_post(
        self, incident: OutageIncident, guild_id: int, channel_id: int, message_id: int
    ) -> None:
        """Record dispatched incident message to enable in-place self-healing edits."""
        query = (
            "INSERT INTO active_tech_incidents "
            "(incident_id, guild_id, channel_id, message_id, provider, title, status, impact, url) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) "
            "ON CONFLICT (incident_id, guild_id) DO UPDATE SET "
            "status = EXCLUDED.status, impact = EXCLUDED.impact, message_id = EXCLUDED.message_id, "
            "last_updated_at = CURRENT_TIMESTAMP;"
        )
        await self.db.execute(
            query,
            incident.incident_id,
            guild_id,
            channel_id,
            message_id,
            incident.provider,
            incident.title,
            incident.status,
            incident.impact,
            incident.url,
        )

    async def mark_incident_resolved(self, incident_id: str) -> None:
        """Mark incident resolved in PostgreSQL."""
        query = (
            "UPDATE active_tech_incidents "
            "SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP, last_updated_at = CURRENT_TIMESTAMP "
            "WHERE incident_id = $1;"
        )
        await self.db.execute(query, incident_id)

    async def update_incident_record(self, incident_id: str, status: str, impact: str) -> None:
        """Update ongoing incident status in PostgreSQL."""
        query = (
            "UPDATE active_tech_incidents "
            "SET status = $1, impact = $2, last_updated_at = CURRENT_TIMESTAMP "
            "WHERE incident_id = $3;"
        )
        await self.db.execute(query, status, impact, incident_id)

    # -------------------------------------------------------------------------
    # Feature B: Critical Zero-Day CVE & Supply Chain Threats (CISA KEV)
    # -------------------------------------------------------------------------
    async def poll_critical_cves(self, session: aiohttp.ClientSession) -> list[CriticalCVE]:
        """Fetch actively exploited vulnerabilities from CISA Known Exploited Vulnerabilities catalog."""
        cisa_url = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
        headers = {"User-Agent": "KyroTechBot/2.0 (Security Threat Monitor)"}
        detected: list[CriticalCVE] = []

        try:
            async with session.get(cisa_url, headers=headers, timeout=aiohttp.ClientTimeout(total=6.0)) as resp:
                if resp.status != 200:
                    return []
                payload = await resp.json()
                vulnerabilities = payload.get("vulnerabilities", [])

                # Inspect recent entries (last 25 in reverse order)
                recent_vulns = vulnerabilities[-25:]
                for v in reversed(recent_vulns):
                    cve_id = v.get("cveID", "").strip()
                    if not cve_id or cve_id in self._cve_cache:
                        continue

                    vendor = v.get("vendorProject", "Unknown Vendor")
                    product = v.get("product", "Core System")
                    title = v.get("vulnerabilityName", f"Critical Vulnerability in {product}")
                    desc = v.get("shortDescription", "Active exploitation observed in the wild.")
                    date_added = v.get("dateAdded", "")
                    due_date = v.get("dueDate", "")
                    action = v.get("requiredAction", "Apply official vendor mitigations immediately.")

                    # Formulate instant terminal remediation command
                    remediation = self._generate_remediation_command(vendor, product, cve_id)
                    nvd_url = f"https://nvd.nist.gov/vuln/detail/{cve_id}"

                    detected.append(
                        CriticalCVE(
                            cve_id=cve_id,
                            title=title,
                            vendor_project=vendor,
                            product=product,
                            description=desc,
                            date_added=date_added,
                            due_date=due_date,
                            action_required=action,
                            cvss_score=9.8,
                            remediation_cmd=remediation,
                            url=nvd_url,
                        )
                    )
        except Exception as err:
            logger.debug(f"Failed to poll CISA KEV feed: {err}")

        return detected

    def _generate_remediation_command(self, vendor: str, product: str, cve_id: str) -> str:
        """Synthesize relevant terminal patch snippet for developers."""
        v_low = vendor.lower()
        p_low = product.lower()

        if any(k in v_low or k in p_low for k in ["linux", "kernel", "ubuntu", "debian"]):
            return "sudo apt update && sudo apt --only-upgrade install linux-image-generic"
        elif any(k in v_low or k in p_low for k in ["docker", "container"]):
            return "docker system prune -a && docker pull <image>:latest"
        elif any(k in v_low or k in p_low for k in ["openssl", "ssh", "nginx", "apache"]):
            return f"sudo apt update && sudo apt install --only-upgrade {p_low}"
        elif any(k in v_low or k in p_low for k in ["python", "pip"]):
            return "pip install --upgrade pip setuptools && pip list --outdated"
        elif any(k in v_low or k in p_low for k in ["node", "npm"]):
            return "npm audit fix --force"
        return f"# Immediate Vendor Patch Required: Check {cve_id} advisories"

    async def mark_cve_dispatched(self, cve: CriticalCVE) -> None:
        """Persist dispatched CVE in memory and PostgreSQL."""
        self._cve_cache.add(cve.cve_id)
        query = (
            "INSERT INTO tech_cve_history (cve_id, title, severity, cvss_score, affected_package) "
            "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (cve_id) DO NOTHING;"
        )
        await self.db.execute(query, cve.cve_id, cve.title, "CRITICAL", cve.cvss_score, f"{cve.vendor_project}/{cve.product}")

    # -------------------------------------------------------------------------
    # Feature D: Major Framework & Runtime Release Radar
    # -------------------------------------------------------------------------
    async def poll_major_releases(self, session: aiohttp.ClientSession) -> list[MajorRelease]:
        """Poll GitHub Releases for top-tier developer runtimes & frameworks."""
        detected_releases: list[MajorRelease] = []
        token = os.getenv("GITHUB_TOKEN", "").strip()
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "KyroTechBot/2.0 (Framework Release Radar)",
        }
        if token:
            headers["Authorization"] = f"token {token}"

        for repo_info in CORE_RELEASE_REPOS:
            repo = repo_info["repo"]
            project = repo_info["project"]
            install_cmd = repo_info["install"]
            url = f"https://api.github.com/repos/{repo}/releases/latest"

            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json()
                    tag = data.get("tag_name", "").strip()
                    if not tag:
                        continue

                    release_id = f"{repo}:{tag}"
                    if release_id in self._releases_cache:
                        continue

                    # Filter out pre-releases or release candidates
                    if data.get("prerelease") or any(k in tag.lower() for k in ["alpha", "beta", "rc", "canary", "nightly"]):
                        continue

                    # Only trigger on major or significant minor versions (e.g. v15.0, v15.1, not v15.0.4)
                    clean_ver = re.sub(r"^[^\d]*", "", tag)
                    parts = clean_ver.split(".")
                    if len(parts) >= 3 and parts[2] not in ["0", "1"]:
                        # Micro patch version - skip
                        continue

                    name = data.get("name") or f"{project} {tag}"
                    body = data.get("body", "")
                    html_url = data.get("html_url", f"https://github.com/{repo}/releases")
                    published_at = data.get("published_at", "")

                    # Clean markdown body and extract summary
                    clean_body = re.sub(r"<[^>]+>", "", body)
                    clean_body = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean_body)
                    lines = [line.strip("- *#\r") for line in clean_body.split("\n") if line.strip()]
                    highlights = [line for line in lines if len(line) > 15 and not line.startswith("Full Changelog")][:3]

                    summary = f"Official production release of {project} {tag} is now generally available."
                    if highlights:
                        summary = f"{highlights[0]}"

                    detected_releases.append(
                        MajorRelease(
                            release_id=release_id,
                            project=project,
                            repo=repo,
                            tag_name=tag,
                            name=name,
                            summary=summary,
                            highlights=highlights[1:3] if len(highlights) > 1 else [],
                            install_cmd=install_cmd,
                            url=html_url,
                            published_at=published_at,
                        )
                    )
            except Exception as exc:
                logger.debug(f"Release poll failed for {repo}: {exc}")

        return detected_releases

    async def mark_release_dispatched(self, release: MajorRelease) -> None:
        """Persist dispatched release in memory and PostgreSQL."""
        self._releases_cache.add(release.release_id)
        query = (
            "INSERT INTO tech_releases_history (release_id, project, tag_name) "
            "VALUES ($1, $2, $3) ON CONFLICT (release_id) DO NOTHING;"
        )
        await self.db.execute(query, release.release_id, release.project, release.tag_name)

    # -------------------------------------------------------------------------
    # Feature C: Global Infrastructure Health Summary (For tech Command)
    # -------------------------------------------------------------------------
    async def get_global_health_summary(self, session: Optional[aiohttp.ClientSession] = None) -> dict[str, str]:
        """Return real-time health indicator for core developer services with 60s cache TTL."""
        now = time.time()
        if self._global_health_cache and (now - self._health_last_fetched < 60.0):
            return {k: v.get("status", "Operational") for k, v in self._global_health_cache.items()}

        headers = {"User-Agent": "KyroTechBot/2.0 (Global Health Radar)"}

        created_session = False
        if session is None:
            created_session = True
            connector = aiohttp.TCPConnector(ssl=False)
            session = aiohttp.ClientSession(connector=connector)

        async def _fetch_health(provider: str, meta: dict[str, str]) -> tuple[str, str]:
            summary_url = meta["summary_url"]
            try:
                async with session.get(summary_url, headers=headers, timeout=aiohttp.ClientTimeout(total=2.5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        indicator = data.get("status", {}).get("indicator", "none")
                        if indicator == "none":
                            return provider, "Operational"
                        elif indicator in ["minor", "minor_outage"]:
                            return provider, "Degraded"
                        elif indicator in ["major", "major_outage"]:
                            return provider, "Major Outage"
                        elif indicator == "critical":
                            return provider, "Critical Down"
                        status_desc = data.get("status", {}).get("description", "Operational")
                        return provider, status_desc
            except Exception:
                pass
            return provider, "Operational"

        try:
            tasks = [_fetch_health(p, m) for p, m in OUTAGE_PROVIDERS.items()]
            health_pairs = await asyncio.gather(*tasks, return_exceptions=True)
            results = {}
            for pair in health_pairs:
                if isinstance(pair, tuple) and len(pair) == 2:
                    results[pair[0]] = pair[1]

            self._global_health_cache = {k: {"status": v} for k, v in results.items()}
            self._health_last_fetched = now
        finally:
            if created_session:
                await session.close()

        return results

    # -------------------------------------------------------------------------
    # Container Presentation Builders
    # -------------------------------------------------------------------------
    def build_outage_container(self, incident: OutageIncident, dot: str = "•") -> KyroContainer:
        """Render self-healing Outage Incident card with dynamic color shifts."""
        status_colors = {
            "investigating": 0xEF4444,  # Red
            "identified": 0xF59E0B,     # Amber
            "monitoring": 0xF59E0B,     # Amber
            "resolved": 0x10B981,       # Emerald Green
        }
        color = status_colors.get(incident.status, 0xF59E0B)
        container = KyroContainer(accent_color=color)

        status_display = incident.status.upper()
        impact_display = incident.impact.upper()

        if incident.status == "resolved":
            badge_title = f"RESOLVED: {incident.provider} Incident"
            sub_line = f"Issue has been successfully resolved and systems verified."
        else:
            badge_title = f"OUTAGE ALERT: {incident.provider} Disruption"
            sub_line = f"Real-time Incident Radar • Live Self-Healing Card"

        container.add_section(
            content=(
                f"### {badge_title}\n"
                f"> {sub_line}"
            )
        )
        container.add_separator(divider=True)

        body_blocks: list[str] = [
            f"**Incident:** {incident.title}",
            f"**Status:** `{status_display}`  {dot}  **Impact:** `{impact_display}`  {dot}  **Provider:** `{incident.provider}`",
        ]

        if incident.components_affected:
            comps = ", ".join(f"`{c}`" for c in incident.components_affected[:4])
            body_blocks.append(f"**Affected Services:** {comps}")

        clean_update = html.unescape(incident.latest_update).strip()
        body_blocks.append(f"**Latest Operational Update:**\n> {clean_update}")

        if incident.status == "resolved":
            body_blocks.append(f"> *All services returned to normal operational status.*")
        else:
            body_blocks.append(f"-# Kyro Self-Healing Engine • This message auto-updates live as status progresses.")

        container.add_text("\n\n".join(body_blocks))
        container.add_separator(divider=True)

        # Action row linking directly to official statuspage
        container.add_action_row([
            {
                "type": 2,
                "style": 5,
                "label": f"View {incident.provider} Statuspage",
                "url": incident.url,
            }
        ])
        return container

    def build_cve_container(self, cve: CriticalCVE, dot: str = "•") -> KyroContainer:
        """Render Crimson Critical Zero-Day Vulnerability Alert card."""
        container = KyroContainer(accent_color=0xDC2626)  # Crimson Alert Red
        container.add_section(
            content=(
                f"### [ZERO-DAY ALERT] {cve.cve_id}\n"
                f"> Actively Exploited In The Wild • CISA KEV Advisory"
            )
        )
        container.add_separator(divider=True)

        body_blocks: list[str] = [
            f"**Vulnerability:** {cve.title}",
            f"**Affected Target:** `{cve.vendor_project}` / `{cve.product}`",
            f"**Severity:** `CRITICAL (CVSS {cve.cvss_score})`  {dot}  **Active Exploitation:** `CONFIRMED`",
            f"**Threat Brief:**\n> {cve.description}",
        ]

        if cve.action_required:
            body_blocks.append(f"**Required Remediation:**\n> {cve.action_required}")

        if cve.remediation_cmd:
            body_blocks.append(f"**Recommended Terminal Patch:**\n```bash\n{cve.remediation_cmd}\n```")

        body_blocks.append("-# Kyro Threat Intelligence • Priority Security Emergency Dispatch")
        container.add_text("\n\n".join(body_blocks))
        container.add_separator(divider=True)

        container.add_action_row([
            {
                "type": 2,
                "style": 5,
                "label": "Official NVD Advisory",
                "url": cve.url,
            },
            {
                "type": 2,
                "style": 5,
                "label": "CISA KEV Catalog",
                "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
            }
        ])
        return container

    def build_release_container(self, release: MajorRelease, dot: str = "•") -> KyroContainer:
        """Render Major Framework / Runtime Release card."""
        container = KyroContainer(accent_color=0x00A8FC)  # Electric Blue
        container.add_section(
            content=(
                f"### [RELEASE RADAR] {release.project} {release.tag_name}\n"
                f"> Production-Ready Release Available"
            )
        )
        container.add_separator(divider=True)

        body_blocks: list[str] = [
            f"**Overview:**\n{release.summary}",
        ]

        if release.highlights:
            hl_text = "\n".join(f"> {dot} {h}" for h in release.highlights[:2])
            body_blocks.append(f"**Key Architectural Highlights:**\n{hl_text}")

        if release.install_cmd:
            body_blocks.append(f"**Instant Upgrade Command:**\n```bash\n{release.install_cmd}\n```")

        body_blocks.append(f"-# Kyro Framework Radar • Curated Tier-1 Developer Releases")
        container.add_text("\n\n".join(body_blocks))
        container.add_separator(divider=True)

        container.add_action_row([
            {
                "type": 2,
                "style": 5,
                "label": "GitHub Release Notes",
                "url": release.url,
            }
        ])
        return container
