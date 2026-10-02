from __future__ import annotations

import asyncio
import os
import platform
import sys
import time
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

try:
    import psutil
except ImportError:
    psutil = None

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer

if TYPE_CHECKING:
    from src.core.bot import KyroBot


def _make_bar(val: float, max_val: float, length: int = 16) -> str:
    """Generate an ASCII bar meter."""
    ratio = min(max(val / max_val, 0.0), 1.0) if max_val > 0 else 0.0
    filled = int(round(ratio * length))
    return "|" * filled + "." * (length - filled)


class MonitorCog(commands.Cog, name="Developer-Monitor"):
    """Real-time live streaming runtime telemetry and benchmark suite."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="live", aliases=["monitor", "htop", "watch"])
    @is_developer()
    async def live_monitor(self, ctx: CustomContext) -> None:
        """
        Stream live real-time server telemetry directly in Discord chat.
        Usage:
          ?live
          ?monitor
        """
        container = KyroContainer(accent_color=None)
        container.add_section(content="```yaml\ninitializing live telemetry stream...\n```")
        container.add_separator(divider=True)
        container.add_text("-# connecting to runtime stream...")

        msg = await ctx.reply(embed=container.build())

        total_ticks = 8
        pid = os.getpid()

        for tick in range(1, total_ticks + 1):
            t_db = time.perf_counter()
            try:
                await self.bot.db.fetch_one("SELECT 1;")
                db_ms = (time.perf_counter() - t_db) * 1000
                db_str = f"{db_ms:.2f}ms"
            except Exception:
                db_ms = 999.0
                db_str = "offline"

            rss_mb = 0.0
            thread_count = 1
            if psutil:
                try:
                    p = psutil.Process(pid)
                    rss_mb = p.memory_info().rss / (1024 * 1024)
                    thread_count = p.num_threads()
                except Exception:
                    pass
            else:
                try:
                    import resource
                    rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
                except Exception:
                    rss_mb = 54.0

            gw_lat = round(self.bot.latency * 1000) if self.bot.latency else 0
            tasks_count = len(asyncio.all_tasks())

            try:
                load = os.getloadavg()
                load_str = f"[{load[0]:.2f}, {load[1]:.2f}]"
            except Exception:
                load_str = "[nominal]"

            gw_bar = _make_bar(gw_lat, 100, 14)
            db_bar = _make_bar(db_ms, 20, 14)
            mem_bar = _make_bar(rss_mb, 200, 14)

            is_last = tick == total_ticks
            state_str = "COMPLETE (Stream Ended)" if is_last else f"LIVE STREAMING (#{tick}/{total_ticks})"

            matrix = [
                "================= [ LIVE RUNTIME MONITOR ] =================",
                f"STREAM STATE    {state_str}",
                f"HOST PID        {pid} • node: kyro-core-01",
                "-----------------------------------------------------------",
                f"GATEWAY WS      {gw_lat:>3}ms [{gw_bar}]",
                f"DATABASE POOL   {db_str:>7} [{db_bar}]",
                f"PROCESS RAM     {rss_mb:>5.1f}MB [{mem_bar}]",
                f"ASYNC ENGINE    {tasks_count} coroutines • {thread_count} threads",
                f"CPU LOAD AVG    {load_str}",
                "===========================================================",
            ]

            frame = KyroContainer(accent_color=None)
            frame.add_section(content="```yaml\n" + "\n".join(matrix) + "\n```")
            frame.add_separator(divider=True)
            status_text = f"-# stream finished • {total_ticks} ticks recorded" if is_last else f"-# live streaming • updating every 1.5s • tick {tick}/{total_ticks}"
            frame.add_text(status_text)

            try:
                await msg.edit(embed=frame.build())
            except Exception:
                break

            if not is_last:
                await asyncio.sleep(1.5)

    @commands.command(name="bench", aliases=["speed", "benchmark"])
    @is_developer()
    async def run_benchmark(self, ctx: CustomContext) -> None:
        """
        Run multi-tier live benchmark: CPU compute, Event Loop, DB pool, and Discord REST API.
        Usage:
          ?bench
        """
        msg = await ctx.reply("`[BENCHMARK]` Starting multi-tier hardware & network benchmark...")

        t_cpu = time.perf_counter()
        _ = sum(i * i for i in range(1_000_000))
        cpu_ms = (time.perf_counter() - t_cpu) * 1000

        t_loop = time.perf_counter()
        await asyncio.sleep(0)
        loop_ms = (time.perf_counter() - t_loop) * 1000

        t_db = time.perf_counter()
        try:
            await self.bot.db.fetch_one("SELECT 1;")
            db_ms = (time.perf_counter() - t_db) * 1000
            db_res = f"{db_ms:.2f}ms (OK)"
        except Exception as e:
            db_res = f"ERR ({e})"

        t_rest = time.perf_counter()
        try:
            await ctx.channel.fetch_message(msg.id)
            rest_ms = (time.perf_counter() - t_rest) * 1000
            rest_res = f"{rest_ms:.2f}ms"
        except Exception:
            rest_res = "N/A"

        gw_lat = round(self.bot.latency * 1000) if self.bot.latency else 0
        overall_score = "TIER-S (Hyper-Optimized)" if cpu_ms < 100 and db_ms < 5 else "TIER-A (Nominal Production)"

        results = [
            "================= [ KYRO BENCHMARK REPORT ] =================",
            f"PERFORMANCE TIER  {overall_score}",
            "-------------------------------------------------------------",
            f"1. CPU 1M OPS     {cpu_ms:.2f}ms (Compute Engine)",
            f"2. EVENT LOOP     {loop_ms:.3f}ms (Zero-Delay Coroutines)",
            f"3. DATABASE POOL  {db_res} (Supabase PostgreSQL)",
            f"4. REST API RTT   {rest_res} (Discord API Edge)",
            f"5. GATEWAY WS     {gw_lat}ms (Heartbeat Shard #0)",
            "-------------------------------------------------------------",
            f"HOST SPECS        {platform.system()} {platform.release()} • Python {sys.version.split()[0]}",
            "=============================================================",
        ]

        container = KyroContainer(accent_color=None)
        container.add_section(content="```yaml\n" + "\n".join(results) + "\n```")
        container.add_separator(divider=True)
        container.add_text("-# hardware & network benchmark complete")

        await msg.edit(content="", embed=container.build())


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(MonitorCog(bot))
