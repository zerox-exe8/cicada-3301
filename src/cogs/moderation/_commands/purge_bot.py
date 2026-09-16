"""
Kyro Discord Bot - Purge Bot Messages Module
Bulk deletes messages sent by bot accounts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import discord

if TYPE_CHECKING:
    from src.core.context import CustomContext
    from src.cogs.moderation.purge import PurgeCog


async def execute_purge_bot(cog: PurgeCog, ctx: CustomContext, count: int = 10) -> None:
    """Purge messages authored by bot accounts (m.author.bot == True)."""
    await cog._execute_purge(
        ctx,
        count=count,
        filter_type="bot",
        check_func=lambda m: bool(m.author.bot),
    )
