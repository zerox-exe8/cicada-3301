"""
Cicada 3301 Discord Bot - Queue Command Handler
"""

from __future__ import annotations

import discord
from src.core.context import CustomContext
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController


async def handle_queue(ctx: CustomContext, controller: MusicController) -> None:
    """Show current song queue."""
    guild_id = ctx.guild.id
    current = controller.get_current(guild_id)
    queue = controller.get_queue(guild_id)

    if not current and not queue:
        await ctx.send("The queue is empty.")
        return

    lines = []
    if current:
        lines.append(f"**Now Playing:** {current.title} (`{current.author}`)")
    if queue:
        lines.append("\n**Up Next:**")
        for i, t in enumerate(queue[:10], 1):
            lines.append(f"`{i}.` {t.title} (`{t.author}`)")
    await ctx.send("\n".join(lines))
