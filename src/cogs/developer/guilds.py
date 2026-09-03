"""
Kyro Discord Bot - Network Guilds Telemetry
Developer diagnostics for connected server nodes and member population.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class GuildsCog(commands.Cog, name="Developer-Guilds"):
    """Network server nodes telemetry."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="guilds", aliases=["servers"])
    @is_developer()
    async def network_guilds(self, ctx: CustomContext) -> None:
        """Display connected server nodes and member metrics."""
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count or 0, reverse=True)
        total_members = sum(g.member_count or 0 for g in guilds)

        lines = []
        for g in guilds[:10]:
            lines.append(f"> `{g.name}` • `{g.member_count} members` (`{g.id}`)")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Network Nodes ({len(guilds)} Guilds)**\n"
                + "\n".join(lines)
            )
        )
        container.add_separator(divider=True)
        lat = round(self.bot.latency * 1000) if (self.bot.latency and self.bot.latency == self.bot.latency) else 0
        container.add_text(f"-# Total Network Entities: {total_members:,} | Latency: {lat}ms")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(GuildsCog(bot))
