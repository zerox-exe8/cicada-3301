"""
Cicada 3301 Discord Bot - Ping & Diagnostic Command
Uses Discord Components V2 Container card with sleek, compact typography.
"""

from __future__ import annotations

import time
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import CicadaContainer, send_container_response


class Ping(commands.Cog):
    """General utility and diagnostics commands."""
    category: str = "General"

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="ping",
        aliases=["pong", "pung", "latency"],
        description="Check Cicada 3301 Bot's websocket, latency, and database response speed.",
    )
    async def ping(self, ctx: CustomContext) -> None:
        """Measure websocket latency, database roundtrip time, and uptime."""
        # 1. Measure DB ping
        start_db = time.perf_counter()
        await self.bot.db.fetch_one("SELECT 1;")
        db_latency = (time.perf_counter() - start_db) * 1000

        # 2. Measure Discord Websocket latency
        ws_latency = self.bot.latency * 1000

        # 3. Calculate Uptime
        now = discord.utils.utcnow()
        start = getattr(self.bot, "start_time", now)
        delta = int((now - start).total_seconds())
        hours, remainder = divmod(delta, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"

        shard_id = ctx.guild.shard_id if ctx.guild else 0

        e_reg = self.bot.custom_emojis
        ping_icon = e_reg.get("icons_goodping", e_reg.get("icons_ping", "📡"))

        container = CicadaContainer(accent_color=None)
        container.add_text(
            f"{ping_icon} **Pong!**\n\n"
            f"• **Websocket:** `{ws_latency:.2f}ms`\n"
            f"• **Database:** `{db_latency:.2f}ms`\n"
            f"• **Uptime:** `{uptime_str}` | **Shard:** `#{shard_id}`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, container)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Ping(bot))
