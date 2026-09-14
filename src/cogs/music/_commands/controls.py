"""
Kyro Discord Bot - Native Music Control Commands (Volume, Loop, Shuffle, Clear, Remove, Jump, 24/7)
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING
from discord.ext import commands

from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.cogs.music.music import Music


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
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Volume adjusted to:** `{new_vol}%`")
    await send_container_response(ctx, container)


async def execute_loop(cog: Music, ctx: commands.Context, mode: str = "off") -> None:
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

    random.shuffle(player.queue)
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Shuffled {len(player.queue)} tracks in queue.**")
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

    cleared_count = len(player.queue)
    player.queue.clear()
    container = KyroContainer(accent_color=None)
    container.add_text(f"**Cleared {cleared_count} tracks from the queue.**")
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

    removed_track = player.queue.pop(index - 1)
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

    # Keep target track at index 0 and clear preceding tracks
    del player.queue[:index - 1]
    target_track = player.queue[0]
    await player.skip()
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

    player = cog.controller.get_or_create_player(ctx.guild)
    player.is_247 = not player.is_247

    # Persist in database
    await cog.bot.db.execute(
        """
        INSERT INTO guild_music_247 (guild_id, is_247)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET is_247 = EXCLUDED.is_247;
        """,
        ctx.guild.id,
        player.is_247,
    )

    state_str = "ENABLED" if player.is_247 else "DISABLED"
    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**24/7 Voice Mode: {state_str}**\n"
            f"> Kyro will {'remain connected in voice indefinitely even when empty' if player.is_247 else 'automatically disconnect when the voice channel is empty'}."
        )
    )
    await send_container_response(ctx, container)
