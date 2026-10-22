from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING, Optional
from discord.ext import commands

from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music

logger = logging.getLogger("Kyro.Music.Controls")

# Per-guild 247 toggle debounce: prevents duplicate responses from hybrid
# commands firing twice (prefix + slash) or rapid double-clicks.
_247_last_toggle: dict[int, float] = {}
_247_DEBOUNCE_SECONDS: float = 3.0


def check_voice_channel(ctx: commands.Context) -> tuple[bool, str | None]:
    """Verify that author is in the same voice channel as the bot."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        return False, "You must be connected to a voice channel to use music commands."
    if ctx.guild.me.voice and ctx.guild.me.voice.channel:
        if ctx.guild.me.voice.channel.id != ctx.author.voice.channel.id:
            return False, f"You must be in the same voice channel as Kyro ({ctx.guild.me.voice.channel.mention})."
    return True, None


async def execute_volume(cog: Music, ctx: commands.Context, volume: int) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyroContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    new_vol = player.set_volume(volume)
    await player.update_controller_message(force=True)
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Volume adjusted to:** `{new_vol}%`")
    await send_container_response(ctx, container)


async def execute_loop(cog: Music, ctx: commands.Context, mode: Optional[str] = None) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyroContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    new_mode = player.set_loop_mode(mode)
    await player.update_controller_message(force=True)
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Loop mode set to:** `{new_mode.upper()}`")
    await send_container_response(ctx, container)


async def execute_shuffle(cog: Music, ctx: commands.Context) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or len(player.queue) < 2:
        container = KyroContainer(accent_color=None)
        container.add_text("**Queue needs at least 2 tracks to shuffle.**")
        await send_container_response(ctx, container)
        return

    shuffled_count = await player.shuffle_queue()
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Shuffled {shuffled_count} tracks in queue.**")
    await send_container_response(ctx, container)


async def execute_clear(cog: Music, ctx: commands.Context) -> None:
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected:
        container = KyroContainer(accent_color=None)
        container.add_text("**No active player found in this server.**")
        await send_container_response(ctx, container)
        return

    if not player.queue:
        container = KyroContainer(accent_color=None)
        container.add_text("**The queue is already empty.**")
        await send_container_response(ctx, container)
        return

    cleared_count = await player.clear_queue()
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Cleared {cleared_count} track{'s' if cleared_count != 1 else ''} from the queue.**")
    await send_container_response(ctx, container)


async def execute_remove(cog: Music, ctx: commands.Context, index: int) -> None:
    """Remove a specific track at 1-based index from the upcoming queue."""
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or not player.queue:
        container = KyroContainer(accent_color=None)
        container.add_text("**The queue is currently empty.**")
        await send_container_response(ctx, container)
        return

    if index < 1 or index > len(player.queue):
        container = KyroContainer(accent_color=None)
        container.add_text(f"**Invalid track index.** Please provide a number between `1` and `{len(player.queue)}`.")
        await send_container_response(ctx, container)
        return

    removed_track = await player.remove_track_at(index - 1)
    if not removed_track:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**Invalid track index.**")
        await send_container_response(ctx, container)
        return

    container = KyroContainer(accent_color=None)
    container.add_text(f"**Removed #{index}:** `{removed_track.title}`")
    await send_container_response(ctx, container)


async def execute_jump(cog: Music, ctx: commands.Context, index: int) -> None:
    """Skip directly to a specific track in queue."""
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    player = cog.controller.get_player(ctx.guild.id)
    if not player or not player.is_connected or not player.queue:
        container = KyroContainer(accent_color=None)
        container.add_text("**The queue is currently empty.**")
        await send_container_response(ctx, container)
        return

    if index < 1 or index > len(player.queue):
        container = KyroContainer(accent_color=None)
        container.add_text(f"**Invalid track index.** Please provide a number between `1` and `{len(player.queue)}`.")
        await send_container_response(ctx, container)
        return

    # If single track loop is on, disable it so skip properly advances to the jumped track
    if player.loop_mode == "track":
        player.loop_mode = "off"

    # Thread-safely keep target track at index 0 and clear preceding tracks
    async with player._queue_lock:
        del player.queue[:index - 1]
        target_track = player.queue[0]

    try:
        await player.skip()
    except Exception as e:
        logger.warning(f"Guild {ctx.guild.id}: jump failed: {type(e).__name__}: {e}")
        container = KyroContainer(accent_color=None)
        container.add_text(f"**Could not jump:** `{e}`\n> Please try again in a moment.")
        await send_container_response(ctx, container)
        return

    container = KyroContainer(accent_color=None)
    container.add_text(f"**Jumping to:** `{target_track.title}`")
    await send_container_response(ctx, container)


async def execute_stay(cog: Music, ctx: commands.Context) -> None:
    """Toggle 24/7 stay mode in voice."""
    allowed, err = check_voice_channel(ctx)
    if not allowed:
        container = KyroContainer(accent_color=None)
        container.add_text(f"**{err}**")
        await send_container_response(ctx, container)
        return

    # Debounce: hybrid commands can fire twice (prefix + slash invocation) or
    # users double-click the slash command. Ignore repeated calls within 3s.
    guild_id = ctx.guild.id
    now = time.monotonic()
    last = _247_last_toggle.get(guild_id, 0.0)
    if now - last < _247_DEBOUNCE_SECONDS:
        return
    _247_last_toggle[guild_id] = now

    player = cog.controller.get_or_create_player(ctx.guild)
    player.is_247 = not getattr(player, "is_247", False)

    if player.is_247:
        if hasattr(cog.controller, "_247_cache"):
            cog.controller._247_cache.add(ctx.guild.id)
        player.cancel_empty_vc_timer(auto_resume=False)
        # Connect immediately if not already connected
        if not player.is_connected and ctx.author.voice and ctx.author.voice.channel:
            try:
                await player.connect_voice(ctx.author.voice.channel)
            except Exception:
                pass
    else:
        if hasattr(cog.controller, "_247_cache"):
            cog.controller._247_cache.discard(ctx.guild.id)
        if not player.is_playing and not player.queue:
            player.schedule_empty_vc_timer()

    # Persist in database
    if hasattr(cog.bot, "db") and cog.bot.db and getattr(cog.bot.db, "pool", None):
        try:
            await cog.bot.db.execute(
                """
                INSERT INTO guild_music_247 (guild_id, is_247)
                VALUES ($1, $2)
                ON CONFLICT(guild_id) DO UPDATE SET is_247 = EXCLUDED.is_247;
                """,
                ctx.guild.id,
                player.is_247,
            )
        except Exception:
            pass

    state_str = "ENABLED" if player.is_247 else "DISABLED"
    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**24/7 Voice Mode: {state_str}**\n"
            f"> Kyro will {'remain connected in voice indefinitely even when empty' if player.is_247 else 'automatically disconnect when the voice channel is empty'}."
        )
    )
    container.add_separator(divider=True)
    container.add_text(f"-# Requested by {ctx.author.display_name}")
    await send_container_response(ctx, container)
