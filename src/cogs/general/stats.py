from __future__ import annotations

import logging
import platform
import sys
import psutil
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.General.Stats")


class Stats(commands.Cog, name="General-Stats"):
    """Live telemetry and system health."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="stats",
        aliases=["uptime"],
        description="View live system telemetry, RAM/CPU metrics, and process health.",
    )
    async def stats(self, ctx: CustomContext) -> None:
        """Display live bot performance telemetry."""
        # uptime calculation
        now = discord.utils.utcnow()
        uptime_delta = now - self.bot.start_time
        days = uptime_delta.days
        hours, remainder = divmod(int(uptime_delta.total_seconds()), 3600)
        hours = hours % 24
        minutes, _ = divmod(remainder, 60)

        if days > 0:
            uptime_str = f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            uptime_str = f"{hours}h {minutes}m"
        else:
            uptime_str = f"{minutes}m"

        # memory & CPU
        process = psutil.Process()
        mem_info = process.memory_info()
        ram_used_mb = mem_info.rss / (1024 * 1024)
        cpu_percent = process.cpu_percent(interval=None)

        sys_mem = psutil.virtual_memory()
        total_sys_ram_gb = sys_mem.total / (1024 * 1024 * 1024)

        # network & Bot metrics
        total_guilds = len(self.bot.guilds)
        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        ws_ping = round(self.bot.latency * 1000) if self.bot.latency else 0

        # container
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### {Config.BOT_NAME} Telemetry\n"
                f"> **Process Uptime:** `{uptime_str}`\n"
                f"> **Gateway Latency:** `{ws_ping}ms`"
            )
        )
        container.add_separator(divider=True)
        container.add_section(
            content=(
                f"**System & Resources**\n"
                f"RAM Usage: `{ram_used_mb:.1f} MB` / `{total_sys_ram_gb:.1f} GB`\n"
                f"Process CPU: `{cpu_percent:.1f}%`\n"
                f"Runtimes: Python `{sys.version.split()[0]}` | Discord.py `{discord.__version__}`\n"
                f"Platform: `{platform.system()} {platform.release()}`"
            )
        )
        container.add_separator(divider=True)
        container.add_section(
            content=(
                f"**Network Reach**\n"
                f"Guilds: `{total_guilds:,}` servers\n"
                f"Users In Scope: `{total_members:,}` members"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        view = discord.ui.View()
        if Config.INVITE_URL:
            view.add_item(
                discord.ui.Button(
                    label="Invite Kyro",
                    url=Config.INVITE_URL,
                    style=discord.ButtonStyle.link,
                )
            )
        if Config.SUPPORT_URL:
            view.add_item(
                discord.ui.Button(
                    label="Support Server",
                    url=Config.SUPPORT_URL,
                    style=discord.ButtonStyle.link,
                )
            )

        if len(view.children) > 0:
            await send_container_response(ctx, container, view=view)
        else:
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Stats(bot))
