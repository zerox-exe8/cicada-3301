from __future__ import annotations

import gc
import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response
from src.sentinel.models import IncidentSeverity, SubsystemType

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Developer.Sentinel")


class SentinelCog(commands.Cog, name="Developer-Sentinel"):
    """Autonomous In-Bot SRE Sentinel diagnostic and remediation console."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.group(name="sentinel", aliases=["sre", "watchdog"], invoke_without_command=True)
    @is_developer()
    async def sentinel_group(self, ctx: CustomContext) -> None:
        """
        Inspect autonomous Sentinel health telemetry, auto-heals, and system status.
        Usage:
          ?sentinel
          ?sentinel status
          ?sentinel incidents
          ?sentinel rca [incident_id]
          ?sentinel heal <db|lavalink|voice|memory>
        """
        await self.status(ctx)

    @sentinel_group.command(name="status", aliases=["health", "metrics"])
    @is_developer()
    async def status(self, ctx: CustomContext) -> None:
        """Display live health metrics, hardware usage, and auto-heal telemetry."""
        if not hasattr(self.bot, "sentinel") or not self.bot.sentinel:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Sentinel Offline**\n> Sentinel SRE Agent is not initialized.")
            await send_container_response(ctx, container)
            return

        report = self.bot.sentinel.get_health_report()
        healed = report["healed_counts"]

        status_icon = "🟢" if report["status"] == "HEALTHY" else ("🟡" if report["status"] == "DEGRADED" else "🔴")

        telemetry = [
            f"=================== [ KYRO SENTINEL SRE ] ===================",
            f"system_health:     {report['status']} {status_icon}",
            f"uptime:            {report['uptime']}",
            f"gateway_latency:   {report['gateway_latency_ms']}",
            f"loop_lag:          {report.get('loop_lag_ms', '0.0 ms')}",
            f"lavalink_node:     {report['lavalink_node']}",
            f"ai_rca_engine:     {report.get('ai_rca_engine', 'Offline')}",
            f"active_streams:    {report['active_audio_streams']} voice stream(s)",
            f"connected_guilds:  {report['guild_count']} guilds",
            "-------------------------------------------------------------",
            f"process_ram:       {report['ram_mb']}",
            f"process_cpu:       {report['cpu_percent']}",
            "-------------------------------------------------------------",
            f"healed_events:     db: {healed.get('database', 0)} • music: {healed.get('music', 0)} • voice: {healed.get('voice', 0)} • mem: {healed.get('memory', 0)}",
            f"total_incidents:   {report['total_incidents']} recorded (unresolved: {report.get('unresolved_incidents', 0)})",
            "=============================================================",
        ]

        text_block = "\n".join(telemetry)

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"```yaml\n{text_block}\n```")
        container.add_separator(divider=True)
        container.add_text(
            f"-# Kyro Autonomous SRE Agent • Use `{ctx.prefix}sentinel rca` for AI diagnosis • `{ctx.prefix}sentinel incidents` for logs"
        )
        await send_container_response(ctx, container)

    @sentinel_group.command(name="incidents", aliases=["log", "history"])
    @is_developer()
    async def incidents(self, ctx: CustomContext, limit: int = 5) -> None:
        """Display recent telemetry incidents and automated remediation history."""
        if not hasattr(self.bot, "sentinel") or not self.bot.sentinel:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Sentinel Offline**\n> Sentinel SRE Agent is not initialized.")
            await send_container_response(ctx, container)
            return

        incidents_list = list(self.bot.sentinel.incidents)[-limit:]
        if not incidents_list:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Sentinel Telemetry Clean**\n> Zero incidents recorded in buffer. System nominal.")
            await send_container_response(ctx, container)
            return

        lines = []
        for inc in reversed(incidents_list):
            res_str = "RESOLVED" if inc.resolved else "UNRESOLVED"
            sev_icon = "🟢" if inc.severity == IncidentSeverity.INFO else ("🟡" if inc.severity == IncidentSeverity.WARNING else "🔴")
            ai_tag = " • 🤖 *[AI RCA]*" if inc.ai_analysis else ""
            lines.append(
                f"`[{inc.id}]` {sev_icon} **{inc.subsystem.value}** - {inc.title}{ai_tag}\n"
                f"> **Details:** `{inc.details[:180]}`\n"
                f"> **Action:** {inc.action_taken or 'None'} | **State:** `{res_str}` | **Time:** `{inc.formatted_time}`"
            )

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"**Autonomous Sentinel Incident Log (Last {len(incidents_list)})**\n\n" + "\n\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Use `{ctx.prefix}sentinel rca <id>` to view autonomous AI diagnosis")
        await send_container_response(ctx, container)

    @sentinel_group.command(name="rca", aliases=["diagnose", "explain"])
    @is_developer()
    async def rca(self, ctx: CustomContext, incident_id: Optional[str] = None) -> None:
        """
        Run or display autonomous Gemini AI Root Cause Analysis for an incident.
        Usage:
          ?sentinel rca
          ?sentinel rca INC-123456
        """
        sentinel = getattr(self.bot, "sentinel", None)
        if not sentinel:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Sentinel Offline**\n> Sentinel SRE Agent is not initialized.")
            await send_container_response(ctx, container)
            return

        # Find target incident
        target_inc = None
        if incident_id:
            incident_id = incident_id.upper().strip()
            for inc in reversed(sentinel.incidents):
                if inc.id == incident_id:
                    target_inc = inc
                    break
        else:
            # Pick latest unresolved incident or latest incident
            for inc in reversed(sentinel.incidents):
                if not inc.resolved:
                    target_inc = inc
                    break
            if not target_inc and sentinel.incidents:
                target_inc = sentinel.incidents[-1]

        if not target_inc:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content="**No Incidents Found**\n> Telemetry buffer is empty or specified incident ID does not exist."
            )
            await send_container_response(ctx, container)
            return

        # If analysis not generated yet, run it on-demand
        ai_rca = target_inc.ai_analysis
        if not ai_rca:
            ai_rca = await sentinel.analyze_incident_with_gemini(target_inc)

        container = KyroContainer(accent_color=None)
        sev_icon = "🟢" if target_inc.severity == IncidentSeverity.INFO else ("🟡" if target_inc.severity == IncidentSeverity.WARNING else "🔴")

        container.add_section(
            content=(
                f"**Sentinel Incident RCA: `{target_inc.id}`**\n"
                f"> **Subsystem:** `{target_inc.subsystem.value}` | **Severity:** {sev_icon} `{target_inc.severity.value}`\n"
                f"> **Title:** **{target_inc.title}**\n"
                f"> **Time:** `{target_inc.formatted_time}` | **State:** `{'RESOLVED' if target_inc.resolved else 'UNRESOLVED'}`"
            )
        )
        container.add_separator(divider=True)

        if ai_rca:
            container.add_section(
                content=f"**🤖 Gemini Autonomous Root Cause Analysis**\n{ai_rca}"
            )
        else:
            container.add_section(
                content=(
                    "**AI Diagnosis Unavailable**\n"
                    f"> Details: `{target_inc.details}`\n"
                    "> Ensure `GEMINI_API_KEY` is configured in `.env` for AI Root Cause Analysis."
                )
            )

        if target_inc.traceback:
            tb_snippet = target_inc.traceback[-500:].strip()
            container.add_separator(divider=True)
            container.add_section(
                content=f"**Recent Stack Trace Snippet**\n```python\n{tb_snippet}\n```"
            )

        container.add_separator(divider=True)
        container.add_text(f"-# Autonomous Sentinel Telemetry • Kyro SRE Intelligence")
        await send_container_response(ctx, container)

    @sentinel_group.command(name="heal", aliases=["fix", "recover"])
    @is_developer()
    async def heal(self, ctx: CustomContext, target: str) -> None:
        """
        Manually trigger an automated self-healing action on a subsystem.
        Targets: db | lavalink | voice | memory
        """
        target = target.lower().strip()
        sentinel = getattr(self.bot, "sentinel", None)
        if not sentinel:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Sentinel Offline**\n> Sentinel SRE Agent is not initialized.")
            await send_container_response(ctx, container)
            return

        container = KyroContainer(accent_color=None)

        if target in ("db", "database", "postgres"):
            try:
                await sentinel.heal_database()
                container.add_section(
                    content=(
                        "**Database Pool Auto-Healed**\n"
                        "> PostgreSQL connection pool recycled and tested successfully."
                    )
                )
            except Exception as e:
                container.add_section(
                    content=(
                        "**Database Pool Heal Failed**\n"
                        f"> Encountered error: `{e}`"
                    )
                )

        elif target in ("lavalink", "music", "node"):
            try:
                await sentinel.heal_lavalink()
                container.add_section(
                    content=(
                        "**Lavalink Node Auto-Healed**\n"
                        "> Wavelink connection pool cleanly re-established and node status verified."
                    )
                )
            except Exception as e:
                container.add_section(
                    content=(
                        "**Lavalink Node Heal Failed**\n"
                        f"> Encountered error: `{e}`"
                    )
                )

        elif target in ("voice", "vc", "client"):
            if not ctx.guild:
                container.add_section(content="**Invalid Context**\n> Voice client heal requires a server context.")
                await send_container_response(ctx, container)
                return

            success = await sentinel.heal_stuck_voice_client(ctx.guild)
            if success:
                container.add_section(
                    content=(
                        "**Voice Client Auto-Healed**\n"
                        f"> Voice client for server `{ctx.guild.name}` was cleanly purged and reset."
                    )
                )
            else:
                container.add_section(
                    content=(
                        "**Voice Client Heal Failed**\n"
                        f"> Could not cleanly reset voice client for `{ctx.guild.name}`."
                    )
                )

        elif target in ("memory", "ram", "gc"):
            collected = gc.collect()
            sentinel._healed_counts["memory"] += 1
            container.add_section(
                content=(
                    "**Process Memory Auto-Purged**\n"
                    f"> Python garbage collection executed. Reclaimed `{collected}` unreachable objects."
                )
            )

        else:
            container.add_section(
                content=(
                    "**Unknown Heal Target**\n"
                    "> Valid targets: `db` (database pool), `lavalink` (music node), `voice` (local guild voice client), `memory` (force garbage collection)."
                )
            )

        container.add_separator(divider=True)
        container.add_text(f"-# Manual remediation dispatched by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(SentinelCog(bot))
