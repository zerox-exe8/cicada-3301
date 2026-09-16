"""
Kyro Discord Bot - Purge Human Messages Module
Bulk deletes messages sent by real users/humans.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import discord

if TYPE_CHECKING:
    from src.core.context import CustomContext
    from src.cogs.moderation.purge import PurgeCog


async def execute_purge_human(cog: PurgeCog, ctx: CustomContext, count: int = 10) -> None:
    """Purge messages authored by humans / non-bots (not m.author.bot)."""
    await cog._execute_purge(
        ctx,
        count=count,
        filter_type="human",
        check_func=lambda m: not m.author.bot,
    )
