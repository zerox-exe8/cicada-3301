from __future__ import annotations

import asyncio
import os
import platform
import sys
import time
from typing import TYPE_CHECKING
import discord
from discord.ext import commands
import psutil

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class SystemCog(commands.Cog, name="Developer-System"):
    """Hardware and runtime system telemetry."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="sys", aliases=["system", "bench", "hardware", "host"])
    @is_developer()
    async def view_system(self, ctx: CustomContext) -> None:
        """
        Inspect live hardware, process memory, and runtime latency.
        Usage:
          ?sys
        """
        # measure live Database latency
        t_db_start = time.perf_counter()
        db_status = "Disconnected"
        db_lat = 0.0
        try:
            await self.bot.db.fetch_one("SELECT 1;")
            db_lat = (time.perf_counter() - t_db_start) * 1000
            db_status = f"Connected ({db_lat:.1f}ms)"
        except Exception:
            db_status = "Error / Offline"

        # process memory
        proc = psutil.Process(os.getpid())
        mem_rss_mb = proc.memory_info().rss / (1024 * 1024)
        mem_vms_mb = proc.memory_info().vms / (1024 * 1024)

        # system memory
        vm = psutil.virtual_memory()
        total_sys_gb = vm.total / (1024 * 1024 * 1024)
        used_sys_gb = vm.used / (1024 * 1024 * 1024)

        # CPU info
        cpu_usage = psutil.cpu_percent(interval=0.1)
        cpu_cores = psutil.cpu_count(logical=True)

        # Discord Gateway latency
        gw_lat = round(self.bot.latency * 1000) if (self.bot.latency and self.bot.latency == self.bot.latency) else 0

        # Async Tasks & Threads
        active_tasks = len(asyncio.all_tasks())
        thread_count = proc.num_threads()

        info_lines = [
            f"process:  {mem_rss_mb:.1f} MB (rss)",
            f"memory:   {used_sys_gb:.1f} / {total_sys_gb:.1f} GB ({vm.percent}%)",
            f"cpu:      {cpu_cores} cores ({cpu_usage}%)",
            f"tasks:    {active_tasks} active • {thread_count} threads",
            f"gateway:  {gw_lat}ms",
            f"database: {db_status}",
            f"runtime:  Python {sys.version.split()[0]} • discord.py {discord.__version__}",
            f"platform: {platform.system()} {platform.release()} ({platform.machine()})",
        ]
        text_block = "\n".join(info_lines)

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"```yaml\n{text_block}\n```")
        container.add_separator(divider=True)
        container.add_text(f"-# pid {proc.pid}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(SystemCog(bot))
