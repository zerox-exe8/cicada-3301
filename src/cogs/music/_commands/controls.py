"""
Cicada 3301 Discord Bot - Music Extra Controls (Loop, Shuffle, Clear, Remove, Volume)
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING
import discord

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext


async def handle_loop(ctx: CustomContext, controller: MusicController, mode: str = "track") -> None:
    """Toggle track or queue loop mode."""
    guild_id = ctx.guild.id
    mode_clean = mode.lower().strip()
    e_reg = ctx.bot.custom_emojis
    loop_icon = e_reg.get("icons_loop", "🔁")

    if mode_clean in ["track", "song", "1"]:
        controller.set_loop(guild_id, "track")
        await ctx.send_success(f"{loop_icon} Loop mode set to **Single Track** (repeating current track).", title="Loop Mode")
    elif mode_clean in ["queue", "all"]:
        controller.set_loop(guild_id, "queue")
        await ctx.send_success(f"{loop_icon} Loop mode set to **Entire Queue** (repeating playlist).", title="Loop Mode")
    elif mode_clean in ["off", "disable", "stop"]:
        controller.set_loop(guild_id, "off")
        await ctx.send_success(f"{loop_icon} Loop mode **Disabled**.", title="Loop Mode")
    else:
        # Toggle cycle: off -> track -> queue -> off
        current = controller.get_loop(guild_id)
        next_mode = "track" if current == "off" else ("queue" if current == "track" else "off")
        controller.set_loop(guild_id, next_mode)
        await ctx.send_success(f"{loop_icon} Loop mode toggled to **{next_mode.upper()}**.", title="Loop Mode")


async def handle_shuffle(ctx: CustomContext, controller: MusicController) -> None:
    """Shuffle the current song queue."""
    guild_id = ctx.guild.id
    queue = controller.get_queue(guild_id)

    if len(queue) < 2:
        await ctx.send_warning("The queue needs at least 2 tracks to shuffle.")
        return

    random.shuffle(queue)
    e_reg = ctx.bot.custom_emojis
    shuf_icon = e_reg.get("icons_shuffle", "🔀")
    await ctx.send_success(f"{shuf_icon} Shuffled **{len(queue)}** upcoming tracks.", title="Queue Shuffled")


async def handle_clear(ctx: CustomContext, controller: MusicController) -> None:
    """Clear all upcoming songs from queue."""
    guild_id = ctx.guild.id
    queue = controller.get_queue(guild_id)

    if not queue:
        await ctx.send_warning("The queue is already empty.")
        return

    count = len(queue)
    queue.clear()
    await ctx.send_success(f"Cleared **{count}** tracks from the upcoming queue.", title="Queue Cleared")


async def handle_remove(ctx: CustomContext, controller: MusicController, position: int) -> None:
    """Remove a specific track from queue by position number."""
    guild_id = ctx.guild.id
    queue = controller.get_queue(guild_id)

    if not queue:
        await ctx.send_warning("The queue is currently empty.")
        return

    if position < 1 or position > len(queue):
        await ctx.send_warning(f"Invalid position. Please specify a number between 1 and {len(queue)}.")
        return

    removed = queue.pop(position - 1)
    await ctx.send_success(f"Removed **[{removed.title}]({removed.url})** from queue position `#{position}`.", title="Track Removed")


async def handle_volume(ctx: CustomContext, controller: MusicController, level: int) -> None:
    """Adjust audio stream volume (0% to 150%)."""
    if level < 0 or level > 150:
        await ctx.send_warning("Volume level must be between `0` and `150` percent.")
        return

    float_vol = level / 100.0
    controller.set_volume(ctx.guild.id, float_vol)

    voice_client: discord.VoiceClient = ctx.guild.voice_client
    if voice_client and voice_client.source and hasattr(voice_client.source, "volume"):
        voice_client.source.volume = float_vol

    e_reg = ctx.bot.custom_emojis
    vol_icon = e_reg.get("volume_up", "🔊") if level >= 50 else e_reg.get("volume_down", "🔉")
    await ctx.send_success(f"{vol_icon} Playback volume set to **{level}%**.", title="Volume Adjusted")
