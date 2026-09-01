"""
Kyro Discord Bot - Music Extra Controls (Loop, Shuffle, Clear, Remove, Volume)
Lavalink V4 Powered Queue Operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import wavelink

from src.cogs.music._player import KyroPlayer

if TYPE_CHECKING:
    from src.cogs.music._controller import MusicController
    from src.core.context import CustomContext


async def handle_loop(ctx: CustomContext, controller: MusicController, mode: str = "track") -> None:
    """Toggle track or queue loop mode."""
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore
    if not player or not player.connected:
        await ctx.send_warning("I am not connected to a voice channel.")
        return

    mode_clean = mode.lower().strip()
    e_reg = ctx.bot.custom_emojis
    loop_icon = e_reg.get("icons_loop", "")
    prefix = f"{loop_icon} " if loop_icon else ""

    if mode_clean in ["track", "song", "1"]:
        player.set_loop_mode("track")
        await ctx.send_success(f"{prefix}Loop mode set to **Single Track** (repeating current track).", title="Loop Mode")
    elif mode_clean in ["queue", "all"]:
        player.set_loop_mode("queue")
        await ctx.send_success(f"{prefix}Loop mode set to **Entire Queue** (repeating playlist).", title="Loop Mode")
    elif mode_clean in ["off", "disable", "stop"]:
        player.set_loop_mode("off")
        await ctx.send_success(f"{prefix}Loop mode **Disabled**.", title="Loop Mode")
    else:
        current = player.get_loop_mode()
        next_mode = "track" if current == "off" else ("queue" if current == "track" else "off")
        player.set_loop_mode(next_mode)
        await ctx.send_success(f"{prefix}Loop mode toggled to **{next_mode.upper()}**.", title="Loop Mode")


async def handle_shuffle(ctx: CustomContext, controller: MusicController) -> None:
    """Shuffle the current song queue."""
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore
    if not player or len(player.queue) < 2:
        await ctx.send_warning("The queue needs at least 2 tracks to shuffle.")
        return

    player.queue.shuffle()
    e_reg = ctx.bot.custom_emojis
    shuf_icon = e_reg.get("icons_shuffle", "")
    prefix = f"{shuf_icon} " if shuf_icon else ""
    await ctx.send_success(f"{prefix}Shuffled **{len(player.queue)}** upcoming tracks.", title="Queue Shuffled")


async def handle_clear(ctx: CustomContext, controller: MusicController) -> None:
    """Clear all upcoming songs from queue."""
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore
    if not player or player.queue.is_empty:
        await ctx.send_warning("The queue is already empty.")
        return

    count = len(player.queue)
    player.queue.clear()
    e_reg = ctx.bot.custom_emojis
    clear_icon = e_reg.get("icons_stop_button", "")
    prefix = f"{clear_icon} " if clear_icon else ""
    await ctx.send_success(f"{prefix}Cleared **{count}** tracks from the upcoming queue.", title="Queue Cleared")


async def handle_remove(ctx: CustomContext, controller: MusicController, position: int) -> None:
    """Remove a specific track from queue by position number."""
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore
    if not player or player.queue.is_empty:
        await ctx.send_warning("The queue is currently empty.")
        return

    if position < 1 or position > len(player.queue):
        await ctx.send_warning(f"Invalid position. Please specify a number between 1 and {len(player.queue)}.")
        return

    # Delete index (0-indexed)
    del_track = player.queue.get_at(position - 1)
    player.queue.delete(position - 1)

    e_reg = ctx.bot.custom_emojis
    del_icon = e_reg.get("icon_delete", "")
    prefix = f"{del_icon} " if del_icon else ""
    title = del_track.title if del_track else "Track"
    uri = del_track.uri if del_track else "#"
    await ctx.send_success(f"{prefix}Removed **[{title}]({uri})** from queue position `#{position}`.", title="Track Removed")


async def handle_volume(ctx: CustomContext, controller: MusicController, level: Optional[int] = None) -> None:
    """View current volume or adjust audio stream volume (0% to 100%)."""
    player: KyroPlayer = ctx.guild.voice_client  # type: ignore
    if not player or not player.connected:
        await ctx.send_warning("I am not connected to a voice channel.")
        return

    e_reg = ctx.bot.custom_emojis
    cur_vol = int(player.volume)

    # If no level is provided, display current volume
    if level is None:
        vol_icon = e_reg.get("volume_up", "") if cur_vol >= 50 else e_reg.get("volume_down", "")
        prefix = f"{vol_icon} " if vol_icon else ""
        await ctx.send_success(
            f"{prefix}Current playback volume is **{cur_vol}%**.\nUse `{ctx.prefix}volume <0-100>` to change it.",
            title="Playback Volume",
        )
        return

    if level < 0 or level > 100:
        await ctx.send_warning("Volume level must be between `0` and `100` percent to prevent audio distortion.")
        return

    await player.set_volume(level)
    vol_icon = e_reg.get("volume_up", "") if level >= 50 else e_reg.get("volume_down", "")
    prefix = f"{vol_icon} " if vol_icon else ""
    await ctx.send_success(f"{prefix}Playback volume set to **{level}%**.", title="Volume Adjusted")
