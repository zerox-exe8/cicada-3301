"""
Kyro Discord Bot - Moderation Helpers
Shared utility functions for role hierarchy verification, duration parsing, and audit log dispatching.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import TYPE_CHECKING, Optional

import discord

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.Helpers")


def parse_duration(duration_str: str) -> Optional[datetime.timedelta]:
    """Parse duration string like '10s', '15m', '2h', '7d' into timedelta."""
    match = re.match(r"^(\d+)([smhd])$", duration_str.strip().lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == "s":
        return datetime.timedelta(seconds=value)
    elif unit == "m":
        return datetime.timedelta(minutes=value)
    elif unit == "h":
        return datetime.timedelta(hours=value)
    elif unit == "d":
        return datetime.timedelta(days=value)
    return None


def check_hierarchy(bot: KyroBot, ctx: CustomContext, target: discord.Member) -> tuple[bool, str | None]:
    """Verify role hierarchy rules between author, bot, and target."""
    if target.id == ctx.author.id:
        return False, "You cannot execute moderation actions on yourself."
    if bot.user and target.id == bot.user.id:
        return False, "I cannot execute moderation actions on myself."
    if target.id == ctx.guild.owner_id:
        return False, "You cannot moderate the server owner."

    # Check author hierarchy (server owner bypasses)
    if ctx.author.id != ctx.guild.owner_id and target.top_role >= ctx.author.top_role:
        return False, "You cannot moderate this member because their highest role is equal to or higher than yours."

    # Check bot hierarchy
    if target.top_role >= ctx.guild.me.top_role:
        return False, "I cannot moderate this member because their highest role is equal to or higher than mine."

    return True, None


async def dispatch_mod_log(
    bot: KyroBot,
    guild: discord.Guild,
    action: str,
    target: discord.User | discord.Member | None = None,
    moderator: discord.User | discord.Member | None = None,
    reason: Optional[str] = None,
    extra: Optional[str] = None,
    channel: Optional[discord.TextChannel | discord.Thread | discord.abc.GuildChannel] = None,
) -> None:
    """Post a sleek audit log card to the configured mod-log channel if available."""
    log_channel = bot.log_mgr.get_log_channel(guild, "mod")
    if not log_channel:
        return

    e_reg = getattr(bot, "custom_emojis", {})
    dot = e_reg.get("heart_dot", "-")
    badge = e_reg.get("icon_moderation", "")
    badge_str = f"{badge} " if badge else ""

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**{badge_str}Moderation Log — {action}**\n"
            f"> System audit record in **{guild.name}**."
        )
    )
    container.add_separator(divider=True)

    items = []
    if target is not None:
        target_name = getattr(target, "display_name", str(target))
        items.append(f"{dot} **Target:** **{target_name}** (`{target.id}`)")

    if channel is not None:
        items.append(f"{dot} **Channel:** {channel.mention}")

    if moderator is not None:
        mod_name = getattr(moderator, "display_name", str(moderator))
        items.append(f"{dot} **Moderator:** **{mod_name}** (`{moderator.id}`)")

    if extra and str(extra).strip():
        items.append(f"{dot} **Details:** `{str(extra).strip()}`")

    if reason and str(reason).strip() and str(reason).strip().lower() != "no reason provided":
        items.append(f"{dot} **Reason:** `{str(reason).strip()}`")

    container.add_text("\n".join(items) if items else f"{dot} Action completed successfully.")
    container.add_separator(divider=True)
    container.add_text(f"-# Timestamp: <t:{int(discord.utils.utcnow().timestamp())}:f>")

    try:
        await send_container_response(log_channel, container)
    except Exception as e:
        logger.warning(f"Failed to dispatch mod log in {guild.name}: {e}")
