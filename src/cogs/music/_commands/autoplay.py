"""
Kyro Discord Bot - Autoplay Command
Simple, clean Autoplay toggle and usage information.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.context import CustomContext
    from src.cogs.music._controller import MusicController


async def handle_autoplay(ctx: CustomContext, controller: MusicController, action: Optional[str] = None) -> None:
    """Toggle Autoplay mode or show clean usage instructions."""
    e_reg = ctx.bot.custom_emojis
    dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "•"))
    autoplay_icon = e_reg.get("icons_loop", e_reg.get("music_playing", ""))
    prefix_icon = f"{autoplay_icon} " if autoplay_icon else ""

    guild_id = ctx.guild.id
    current_state = controller.get_autoplay(guild_id)

    # 1. If no argument provided, show clean usage guide
    if not action:
        container = KyroContainer(accent_color=None)
        status_text = "Enabled" if current_state else "Disabled"
        container.add_section(
            content=(
                f"**{prefix_icon}Autoplay Settings**\n"
                f"> **Status:** `{status_text}`\n"
                f"> **Usage:** `{ctx.prefix}autoplay <on / off>`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Description:** Automatically queues similar tracks based on the songs you play when the queue ends."
        )
        await send_container_response(ctx, container)
        return

    act = action.lower().strip()

    if act in ("on", "enable", "1", "true"):
        controller.set_autoplay(guild_id, True)
        await ctx.send_success(
            f"{prefix_icon}Autoplay has been **Enabled**. Similar songs will play automatically after the queue ends.",
            title="Autoplay Enabled",
        )
    elif act in ("off", "disable", "0", "false"):
        controller.set_autoplay(guild_id, False)
        await ctx.send_success(
            f"{prefix_icon}Autoplay has been **Disabled**.",
            title="Autoplay Disabled",
        )
    else:
        # Toggle
        new_state = not current_state
        controller.set_autoplay(guild_id, new_state)
        state_str = "Enabled" if new_state else "Disabled"
        await ctx.send_success(
            f"{prefix_icon}Autoplay is now **{state_str}**.",
            title=f"Autoplay {state_str}",
        )
