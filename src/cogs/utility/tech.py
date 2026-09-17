"""
Kyro Discord Bot - Advanced Tech & Platform Utilities
Engineered for community security, timezone resolution, service diagnostics, and platform insights.
Delivered in Discord Components V2 Containers.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Utility.Tech")

# Known phishing/scam lookalikes and IP logging signatures
KNOWN_MALICIOUS_PATTERNS: list[str] = [
    r"dlscord",
    r"discorcl",
    r"discrod",
    r"discord-nitro",
    r"nitro-steam",
    r"gift-discord",
    r"steamcommuniity",
    r"steam-trade",
    r"steamcommunity\.link",
    r"grabify\.link",
    r"iplogger",
    r"blasze",
    r"2no\.co",
    r"yip\.su",
    r"free-nitro",
    r"claim-nitro",
]

POPULAR_SERVICES: dict[str, tuple[str, str]] = {
    "discord": ("https://discord.com/api/v10/gateway", "Discord Gateway"),
    "steam": ("https://store.steampowered.com", "Steam Network"),
    "valorant": ("https://status.riotgames.com", "Riot Services"),
    "riot": ("https://status.riotgames.com", "Riot Services"),
    "cloudflare": ("https://www.cloudflare.com", "Cloudflare Edge"),
    "github": ("https://api.github.com", "GitHub Core API"),
    "epic": ("https://status.epicgames.com", "Epic Games Store"),
    "youtube": ("https://www.youtube.com", "YouTube Network"),
    "spotify": ("https://api.spotify.com", "Spotify Web API"),
}


class TechCog(commands.Cog):
    """Advanced technical and platform utilities for modern Discord communities."""
    category: str = "Utility"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    # -------------------------------------------------------------------------
    # Helper: Natural Time Parser
    # -------------------------------------------------------------------------
    @staticmethod
    def _parse_time_expression(expr: str) -> Optional[int]:
        """Convert human time phrases (e.g. '2h 30m', 'in 45 mins', 'tomorrow 8pm') to UTC epoch."""
        now = datetime.now(timezone.utc)
        cleaned = expr.strip().lower()

        # Check relative duration (e.g., "1d 2h 30m 10s", "45 mins", "in 2 hours")
        rel_cleaned = re.sub(r"^(?:in|after)\s+", "", cleaned).strip()
        pattern = re.compile(
            r"^(?:(\d+)\s*(?:d|day|days))?\s*"
            r"(?:(\d+)\s*(?:h|hr|hrs|hour|hours))?\s*"
            r"(?:(\d+)\s*(?:m|min|mins|minute|minutes))?\s*"
            r"(?:(\d+)\s*(?:s|sec|secs|second|seconds))?$"
        )
        match = pattern.fullmatch(rel_cleaned)
        if match and any(match.groups()):
            days = int(match.group(1) or 0)
            hours = int(match.group(2) or 0)
            minutes = int(match.group(3) or 0)
            seconds = int(match.group(4) or 0)
            total_secs = days * 86400 + hours * 3600 + minutes * 60 + seconds
            if total_secs > 0:
                return int((now + timedelta(seconds=total_secs)).timestamp())

        # Check absolute clock times (e.g. "8:30pm", "tomorrow 9:00", "today 14:00")
        clock_match = re.search(r"(?:(today|tomorrow)\s+)?(\d{1,2}):(\d{2})(?:\s*(am|pm))?", cleaned)
        if clock_match:
            day_ref = clock_match.group(1)
            hour = int(clock_match.group(2))
            minute = int(clock_match.group(3))
            meridiem = clock_match.group(4)

            if meridiem == "pm" and hour < 12:
                hour += 12
            elif meridiem == "am" and hour == 12:
                hour = 0

            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if day_ref == "tomorrow" or (day_ref is None and target <= now):
                target += timedelta(days=1)
            return int(target.timestamp())

        return None

    # -------------------------------------------------------------------------
    # Command 1: Deep Link Inspector & Phishing Scanner
    # -------------------------------------------------------------------------
    @commands.hybrid_command(
        name="scan",
        aliases=["safety", "checklink", "urlscan"],
        description="Inspect a link for redirect chains, typosquatting, and security risks.",
    )
    @app_commands.describe(target="The URL or domain to inspect")
    async def scan(self, ctx: CustomContext, *, target: str) -> None:
        """Deep security inspector for external links and domains."""
        url = target.strip()
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            container = KyroContainer(accent_color=0xFF3333)
            container.add_section(content="**Invalid Target**\n> Please provide a valid URL or domain.")
            await send_container_response(ctx, container)
            return

        # Check phishing / lookalike signatures
        is_threat = False
        threat_reason = None
        for pattern in KNOWN_MALICIOUS_PATTERNS:
            if re.search(pattern, domain):
                is_threat = True
                threat_reason = "Lookalike domain / Known phishing signature"
                break

        # Follow redirects & measure latency
        hops: list[str] = []
        final_url = url
        status_code: Optional[int] = None
        latency_ms = 0
        error_msg: Optional[str] = None

        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=5)
        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                t0 = time.perf_counter()
                async with session.head(url, allow_redirects=True) as resp:
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    status_code = resp.status
                    final_url = str(resp.url)
                    if resp.history:
                        hops = [str(r.url) for r in resp.history]
        except Exception as exc:
            error_msg = str(exc)

        # Determine Security Verdict
        final_domain = urlparse(final_url).netloc.lower()
        if not is_threat:
            for pattern in KNOWN_MALICIOUS_PATTERNS:
                if re.search(pattern, final_domain):
                    is_threat = True
                    threat_reason = "Redirects to known phishing target"
                    break

        dot = self.bot.custom_emojis.get("heart_dot", "•")

        if is_threat:
            accent = 0xFF3333
            verdict = "MALICIOUS / HIGH RISK"
        elif len(hops) > 2 or not final_url.startswith("https://"):
            accent = 0xFFA500
            verdict = "CAUTION / UNENCRYPTED OR MULTI-HOP"
        elif status_code and status_code < 400:
            accent = 0x00FF66
            verdict = "VERIFIED SAFE"
        else:
            accent = 0x808080
            verdict = "UNREACHABLE / INACTIVE"

        container = KyroContainer(accent_color=accent)
        container.add_section(
            content=(
                f"**Link Security Inspection**\n"
                f"> **{domain}** • `{verdict}`"
            )
        )
        container.add_separator(divider=True)

        status_text = f"`{status_code}` ({latency_ms}ms)" if status_code else "`No response`"
        security_text = "`HTTPS (Encrypted)`" if final_url.startswith("https://") else "`HTTP (Plaintext)`"

        info_lines = [
            f"{dot} **Destination:** `{final_url[:75]}{'...' if len(final_url) > 75 else ''}`",
            f"{dot} **Response Code:** {status_text}",
            f"{dot} **Redirect Chain:** `{len(hops)} Hop(s)`",
            f"{dot} **Transport:** {security_text}",
        ]
        if threat_reason:
            info_lines.append(f"{dot} **Security Flag:** `{threat_reason}`")
        if error_msg:
            info_lines.append(f"{dot} **Diagnostics:** `{error_msg[:60]}`")

        container.add_text("\n".join(info_lines))
        container.add_separator(divider=True)
        container.add_text("-# Kyro Security Sentinel • Zero-Execution Trace")

        buttons = []
        if not is_threat and final_url.startswith("https://"):
            buttons.append({
                "type": 2,
                "style": 5,
                "label": "Open Destination",
                "url": final_url,
            })
        if buttons:
            container.add_action_row(buttons)

        await send_container_response(ctx, container)

    # -------------------------------------------------------------------------
    # Command 2: Discord Dynamic Timestamp & Countdown Generator
    # -------------------------------------------------------------------------
    @commands.hybrid_command(
        name="time",
        aliases=["timestamp", "ts", "countdown"],
        description="Convert human times to auto-updating Discord countdown tags.",
    )
    @app_commands.describe(expression="Time phrase, e.g. '2h 30m', 'in 45 mins', 'tomorrow 8pm'")
    async def time(self, ctx: CustomContext, *, expression: str) -> None:
        """Parse natural time language and output Discord's native auto-updating tags."""
        epoch = self._parse_time_expression(expression)
        if not epoch:
            container = KyroContainer(accent_color=0xFF3333)
            container.add_section(
                content=(
                    "**Invalid Time Format**\n"
                    "> Could not understand the time expression.\n"
                    "> **Examples:** `2h 30m`, `in 45 mins`, `1d`, `tomorrow 8:30pm`"
                )
            )
            await send_container_response(ctx, container)
            return

        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Discord Dynamic Timestamp**\n"
                f"> Preview: <t:{epoch}:F> (<t:{epoch}:R>)"
            )
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Live Countdown:** `<t:{epoch}:R>` → <t:{epoch}:R>\n"
            f"{dot} **Full Date & Time:** `<t:{epoch}:F>` → <t:{epoch}:F>\n"
            f"{dot} **Short Clock:** `<t:{epoch}:t>` → <t:{epoch}:t>"
        )
        container.add_separator(divider=True)
        container.add_text(
            f"**Copy Raw Tags (Paste Anywhere in Discord):**\n"
            f"```text\n"
            f"<t:{epoch}:R>   # Live countdown\n"
            f"<t:{epoch}:F>   # Full date & time\n"
            f"```"
        )
        container.add_separator(divider=True)
        container.add_text("-# Discord Client Clocks • Auto-adjusts to viewer local timezone")

        await send_container_response(ctx, container)

    # -------------------------------------------------------------------------
    # Command 3: Client & Platform Detective
    # -------------------------------------------------------------------------
    @commands.hybrid_command(
        name="device",
        aliases=["client", "platform"],
        description="Inspect a user's active client platform (Desktop, Mobile, Web) and rich presence.",
    )
    @app_commands.describe(member="Member to inspect (defaults to yourself)")
    @commands.guild_only()
    async def device(self, ctx: CustomContext, member: Optional[discord.Member] = None) -> None:
        """Inspect which clients a member is logged into and their current activity."""
        target = member or ctx.author
        if not isinstance(target, discord.Member):
            target = ctx.guild.get_member(target.id) or target

        dot = self.bot.custom_emojis.get("heart_dot", "•")

        # Client status parsing
        desktop = getattr(target, "desktop_status", discord.Status.offline)
        mobile = getattr(target, "mobile_status", discord.Status.offline)
        web = getattr(target, "web_status", discord.Status.offline)

        def format_status(s: discord.Status) -> str:
            if s == discord.Status.online:
                return "`Online`"
            elif s == discord.Status.idle:
                return "`Idle`"
            elif s == discord.Status.dnd:
                return "`Do Not Disturb`"
            return "`Offline`"

        # Rich presence analysis
        activities_text: list[str] = []
        if hasattr(target, "activities") and target.activities:
            for act in target.activities:
                if isinstance(act, discord.Spotify):
                    activities_text.append(f"{dot} **Spotify:** Listening to **{act.title}** by `{act.artist}`")
                elif isinstance(act, discord.Game):
                    activities_text.append(f"{dot} **Game:** Playing **{act.name}**")
                elif isinstance(act, discord.Streaming):
                    activities_text.append(f"{dot} **Stream:** Streaming on **{act.platform or 'Live'}**")
                elif isinstance(act, discord.CustomActivity):
                    if act.name:
                        activities_text.append(f"{dot} **Custom Status:** \"{act.name}\"")
                elif act.type == discord.ActivityType.playing:
                    details = f" ({act.details})" if getattr(act, "details", None) else ""
                    activities_text.append(f"{dot} **Activity:** **{act.name}**{details}")

        if not activities_text:
            activities_text.append(f"{dot} **Presence:** No active game, stream, or media detected.")

        avatar_url = target.display_avatar.with_size(128).url
        accessory = {
            "type": 11,
            "media": {"url": avatar_url},
        }

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Platform & Client Inspection**\n"
                f"> **{target.display_name}** (`{target.id}`)"
            ),
            accessory=accessory,
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Desktop Client:** {format_status(desktop)}\n"
            f"{dot} **Mobile Device:** {format_status(mobile)}\n"
            f"{dot} **Web Browser:** {format_status(web)}"
        )
        container.add_separator(divider=True)
        container.add_text("\n".join(activities_text))
        container.add_separator(divider=True)
        container.add_text("-# Discord Gateway Presence • Precision Hardware Probe")

        await send_container_response(ctx, container)

    # -------------------------------------------------------------------------
    # Command 4: Realtime Gaming & Service Outage Monitor
    # -------------------------------------------------------------------------
    @commands.hybrid_command(
        name="service",
        aliases=["statusweb", "pingweb", "srv"],
        description="Check real-time network status and latency of popular games and services.",
    )
    @app_commands.describe(target="Service name (discord, steam, valorant, cloudflare, github) or custom URL")
    async def service(self, ctx: CustomContext, *, target: str) -> None:
        """Measure HTTP latency and operational health of target networks."""
        t_clean = target.strip().lower()

        if t_clean in POPULAR_SERVICES:
            url, label = POPULAR_SERVICES[t_clean]
        elif target.startswith(("http://", "https://")):
            url = target
            label = urlparse(target).netloc
        else:
            url = f"https://{target}"
            label = target

        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=4)
        status_code: Optional[int] = None
        latency_ms: Optional[int] = None
        is_online = False
        error_info: Optional[str] = None

        try:
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                t0 = time.perf_counter()
                async with session.head(url, allow_redirects=True) as resp:
                    latency_ms = int((time.perf_counter() - t0) * 1000)
                    status_code = resp.status
                    is_online = status_code < 500
        except Exception as exc:
            error_info = str(exc)

        dot = self.bot.custom_emojis.get("heart_dot", "•")

        if is_online and latency_ms is not None:
            if latency_ms < 350:
                accent = 0x00FF66
                verdict = "OPERATIONAL / LOW LATENCY"
            elif latency_ms < 800:
                accent = 0xFFA500
                verdict = "DEGRADED / ELEVATED LATENCY"
            else:
                accent = 0xFF3333
                verdict = "HIGH LATENCY"
        else:
            accent = 0xFF3333
            verdict = "OUTAGE / UNREACHABLE"

        container = KyroContainer(accent_color=accent)
        container.add_section(
            content=(
                f"**Service Health & Latency Probe**\n"
                f"> **{label}** • `{verdict}`"
            )
        )
        container.add_separator(divider=True)

        lines = [
            f"{dot} **Endpoint:** `{url[:70]}`",
            f"{dot} **HTTP Response:** `{status_code or 'Failed'}`",
            f"{dot} **Handshake Roundtrip:** `{f'{latency_ms}ms' if latency_ms is not None else 'Timed Out'}`",
        ]
        if error_info:
            lines.append(f"{dot} **Diagnostics:** `{error_info[:60]}`")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text("-# Kyro Pulse Probe • High Precision Handshake")

        await send_container_response(ctx, container)

    # -------------------------------------------------------------------------
    # Command 5: DNS Over HTTPS Query (DoH)
    # -------------------------------------------------------------------------
    @commands.hybrid_command(
        name="dns",
        aliases=["nslookup", "dig"],
        description="Query DNS records via Cloudflare DoH (A, AAAA, MX, TXT, CNAME).",
    )
    @app_commands.describe(
        domain="Domain name (e.g. google.com, discord.com)",
        record_type="Record type: A, AAAA, MX, TXT, CNAME (default A)",
    )
    async def dns(self, ctx: CustomContext, domain: str, record_type: str = "A") -> None:
        """Resolve DNS records globally using Cloudflare 1.1.1.1 secure resolver."""
        clean_domain = re.sub(r"^https?://", "", domain).strip().split("/")[0]
        rtype = record_type.strip().upper()
        if rtype not in {"A", "AAAA", "MX", "TXT", "CNAME", "NS", "SOA"}:
            rtype = "A"

        url = f"https://cloudflare-dns.com/dns-query?name={clean_domain}&type={rtype}"
        headers = {"Accept": "application/dns-json"}
        connector = aiohttp.TCPConnector(ssl=False)

        answers: list[str] = []
        status = 0
        try:
            async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=4)) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        status = data.get("Status", 0)
                        raw_answers = data.get("Answer", [])
                        for item in raw_answers:
                            val = item.get("data")
                            if val:
                                answers.append(str(val))
        except Exception:
            pass

        dot = self.bot.custom_emojis.get("heart_dot", "•")

        if not answers:
            container = KyroContainer(accent_color=0xFFA500)
            container.add_section(
                content=(
                    f"**DNS Resolution**\n"
                    f"> No `{rtype}` records found for **{clean_domain}** (Status Code: `{status}`)."
                )
            )
            await send_container_response(ctx, container)
            return

        container = KyroContainer(accent_color=0x00FF66)
        container.add_section(
            content=(
                f"**DNS Over HTTPS Resolution**\n"
                f"> **{clean_domain}** • Type `{rtype}` ({len(answers)} Record{'s' if len(answers) > 1 else ''})"
            )
        )
        container.add_separator(divider=True)

        rec_blocks = "\n".join(f"{dot} `{ans}`" for ans in answers[:8])
        container.add_text(rec_blocks)
        container.add_separator(divider=True)
        container.add_text("-# Cloudflare 1.1.1.1 Secure Anycast Resolver")

        await send_container_response(ctx, container)

    # -------------------------------------------------------------------------
    # Command 6: GitHub Repository Inspector
    # -------------------------------------------------------------------------
    @commands.hybrid_command(
        name="github",
        aliases=["gh", "repo"],
        description="Inspect a GitHub repository's stats, language, and activity.",
    )
    @app_commands.describe(repository="Repository in 'owner/repo' format (e.g. 'python/cpython')")
    async def github(self, ctx: CustomContext, *, repository: str) -> None:
        """Lookup repository metadata from GitHub API."""
        repo_clean = repository.strip().strip("/")
        if "github.com/" in repo_clean:
            repo_clean = repo_clean.split("github.com/")[-1]

        url = f"https://api.github.com/repos/{repo_clean}"
        headers = {
            "User-Agent": "KyroBot-TechSuite/1.0",
            "Accept": "application/vnd.github.v3+json",
        }
        connector = aiohttp.TCPConnector(ssl=False)

        data = None
        try:
            async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=4)) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
        except Exception:
            pass

        if not data:
            container = KyroContainer(accent_color=0xFF3333)
            container.add_section(
                content=(
                    f"**Repository Not Found**\n"
                    f"> Could not find `{repo_clean}` on GitHub. Check the owner/repo spelling."
                )
            )
            await send_container_response(ctx, container)
            return

        dot = self.bot.custom_emojis.get("heart_dot", "•")

        full_name = data.get("full_name", repo_clean)
        stars = data.get("stargazers_count", 0)
        forks = data.get("forks_count", 0)
        issues = data.get("open_issues_count", 0)
        language = data.get("language") or "Mixed"
        license_name = (data.get("license") or {}).get("spdx_id") or "None"
        desc = (data.get("description") or "No repository description provided.")[:130]
        repo_url = data.get("html_url", f"https://github.com/{repo_clean}")
        owner_avatar = (data.get("owner") or {}).get("avatar_url")

        accessory = None
        if owner_avatar:
            accessory = {
                "type": 11,
                "media": {"url": owner_avatar},
            }

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**GitHub Repository**\n"
                f"> **{full_name}** • `{language}`"
            ),
            accessory=accessory,
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Overview:** {desc}\n"
            f"{dot} **Stars:** `{stars:,}` • **Forks:** `{forks:,}`\n"
            f"{dot} **Open Issues:** `{issues:,}` • **License:** `{license_name}`"
        )
        container.add_separator(divider=True)
        container.add_text("-# GitHub Public REST Engine")

        container.add_action_row([{
            "type": 2,
            "style": 5,
            "label": "Open Repository",
            "url": repo_url,
        }])

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Register the Tech suite cog with KyroBot."""
    await bot.add_cog(TechCog(bot))
