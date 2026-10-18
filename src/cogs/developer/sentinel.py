from __future__ import annotations

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
          ?sentinel heal <db|lavalink|voice>
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

        e_reg = getattr(self.bot, "custom_emojis", None)
        status_icon = "🟢" if report["status"] == "HEALTHY" else ("🟡" if report["status"] == "DEGRADED" else "🔴")

        telemetry = [
            f"=================== [ KYRO SENTINEL SRE ] ===================",
            f"system_health:     {report['status']} {status_icon}",
            f"uptime:            {report['uptime']}",
            f"gateway_latency:   {report['gateway_latency_ms']}",
            f"lavalink_node:     {report['lavalink_node']}",
            f"active_streams:    {report['active_audio_streams']} voice stream(s)",
            f"connected_guilds:  {report['guild_count']} guilds",
            "-------------------------------------------------------------",
            f"process_ram:       {report['ram_mb']}",
            f"process_cpu:       {report['cpu_percent']}",
            "-------------------------------------------------------------",
            f"healed_events:     db: {healed.get('database', 0)} • music: {healed.get('music', 0)} • voice: {healed.get('voice', 0)}",
            f"total_incidents:   {report['total_incidents']} recorded in buffer",
            "=============================================================",
        ]

        text_block = "\n".join(telemetry)

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"```yaml\n{text_block}\n```")
        container.add_separator(divider=True)
        container.add_text(f"-# Kyro Autonomous SRE Agent • Use `{ctx.prefix}sentinel incidents` for incident log")
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
            lines.append(
                f"`[{inc.id}]` {sev_icon} **{inc.subsystem.value}** - {inc.title}\n"
                f"> **Details:** `{inc.details}`\n"
                f"> **Action:** {inc.action_taken or 'None'} | **State:** `{res_str}` | **Time:** `{inc.formatted_time}`"
            )

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"**Autonomous Sentinel Incident Log (Last {len(incidents_list)})**\n\n" + "\n\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Telemetry buffer retains last 50 events in memory")
        await send_container_response(ctx, container)

    @sentinel_group.command(name="heal", aliases=["fix", "recover"])
    @is_developer()
    async def heal(self, ctx: CustomContext, target: str) -> None:
        """
        Manually trigger an automated self-healing action on a subsystem.
        Targets: db | lavalink | voice
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
                        "> Wavelink connection pool re-established and node status verified."
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

        else:
            container.add_section(
                content=(
                    "**Unknown Heal Target**\n"
                    "> Valid targets: `db` (database pool), `lavalink` (music node), `voice` (local guild voice client)."
                )
            )

        container.add_separator(divider=True)
        container.add_text(f"-# Manual remediation dispatched by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(SentinelCog(bot))
