"""
Kyro Discord Bot - Native Music Cog
High-Fidelity in-process Discord Audio Engine with zero Lavalink dependencies.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response
from src.cogs.music._controller import MusicController
from src.cogs.music._views import MusicControlView
from src.cogs.music._commands.play import execute_play
from src.cogs.music._commands.pause import execute_pause, execute_resume
from src.cogs.music._commands.skip import execute_skip
from src.cogs.music._commands.stop import execute_stop
from src.cogs.music._commands.queue import execute_queue
from src.cogs.music._commands.nowplaying import execute_nowplaying
from src.cogs.music._commands.autoplay import execute_autoplay
from src.cogs.music._commands.controls import (
    execute_loop,
    execute_shuffle,
    execute_clear,
    execute_volume,
    execute_remove,
    execute_jump,
    execute_stay,
)
from src.cogs.music._commands.playlist import handle_playlist, handle_like, handle_unlike

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Music")


class Music(commands.Cog):
    """High-Performance Native Discord Audio & Studio Music Engine."""
    category: str = "Music"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.controller = MusicController(bot)
        # Register persistent view for button interactions
        self.bot.add_view(MusicControlView(bot, None))

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Handle voice channel disconnects, empty VC timeouts, and 24/7 pause/resume."""
        # 0. Ignore state updates where channel did not change (mute/unmute/deafen/stream)
        if before.channel == after.channel:
            return

        # 1. Bot itself was disconnected from voice
        if member.id == self.bot.user.id and after.channel is None:
            player = self.controller.get_player(member.guild.id)
            if player:
                player.cancel_empty_vc_timer(auto_resume=False)
                # Only announce disconnect if not already announced by empty timer or user command
                if not getattr(player, "_disconnect_announced", False):
                    if player.home_channel and before.channel:
                        try:
                            container = KyroContainer(accent_color=None)
                            container.add_section(
                                content=(
                                    "**Voice Disconnected**\n"
                                    f"> Kyro has disconnected from {before.channel.mention}."
                                )
                            )
                            await send_container_response(player.home_channel, container)
                        except Exception:
                            pass
                player._disconnect_announced = False
                player._was_paused_for_empty_vc = False
                player.queue.clear()
                player.current = None
                player.voice_client = None
            return

        # 2. Non-bot member joined or moved into bot's voice channel
        if after.channel and not member.bot:
            player = self.controller.get_player(after.channel.guild.id)
            if player and player.voice_client and player.voice_client.channel == after.channel:
                was_auto_paused = player._was_paused_for_empty_vc
                # Cancel pending empty VC disconnect timer and auto-resume if it was paused for empty VC
                player.cancel_empty_vc_timer(auto_resume=True)
                if was_auto_paused:
                    if player.home_channel:
                        try:
                            container = KyroContainer(accent_color=None)
                            container.add_section(
                                content=(
                                    "**Playback Resumed**\n"
                                    f"> Listener joined {after.channel.mention}. Resuming music playback."
                                )
                            )
                            await send_container_response(player.home_channel, container)
                        except Exception:
                            pass
                    await player.update_controller_message(force=True)

        # 3. Non-bot member left or moved out of bot's voice channel
        if before.channel and not member.bot:
            player = self.controller.get_player(before.channel.guild.id)
            if player and player.voice_client and player.voice_client.channel == before.channel:
                human_listeners = [m for m in before.channel.members if not m.bot]
                if len(human_listeners) == 0:
                    # Auto-pause playback if playing
                    if player.is_playing:
                        player.pause()
                        player._was_paused_for_empty_vc = True
                        await player.update_controller_message(force=True)

                    # Check 24/7 mode
                    if getattr(player, "is_247", False):
                        logger.info(f"Voice channel #{before.channel.name} empty, but 24/7 active. Paused and staying connected.")
                        if player.home_channel:
                            try:
                                container = KyroContainer(accent_color=None)
                                container.add_section(
                                    content=(
                                        "**Voice Channel Empty (24/7 Mode Active)**\n"
                                        f"> All listeners left {before.channel.mention}. Playback has been paused.\n"
                                        "> Kyro will remain connected in voice (24/7 Mode Enabled)."
                                    )
                                )
                                await send_container_response(player.home_channel, container)
                            except Exception:
                                pass
                        return

                    # 24/7 is OFF: start 2-minute countdown timer
                    logger.info(f"Voice channel #{before.channel.name} empty. Starting 2-minute disconnect countdown.")
                    player.cancel_empty_vc_timer(auto_resume=False)
                    player._was_paused_for_empty_vc = True
                    if player.home_channel:
                        try:
                            container = KyroContainer(accent_color=None)
                            container.add_section(
                                content=(
                                    "**Voice Channel Empty**\n"
                                    f"> All listeners left {before.channel.mention}. Playback has been paused.\n"
                                    "> Kyro will disconnect in **2 minutes** if no one rejoins."
                                )
                            )
                            await send_container_response(player.home_channel, container)
                        except Exception:
                            pass

                    player._empty_vc_task = asyncio.create_task(
                        self._empty_vc_timeout_worker(player, before.channel, timeout=120)
                    )

    async def _empty_vc_timeout_worker(
        self, player: Any, channel: discord.VoiceChannel, timeout: int = 120
    ) -> None:
        """Disconnects player after specified inactivity timeout if channel remains empty."""
        try:
            await asyncio.sleep(timeout)
            if not player.voice_client or player.voice_client.channel != channel:
                return

            human_listeners = [m for m in channel.members if not m.bot]
            if len(human_listeners) > 0:
                return

            if getattr(player, "is_247", False):
                return

            logger.info(f"Empty VC timer expired for #{channel.name} in guild {player.guild.id}. Disconnecting.")
            player._disconnect_announced = True

            if player.home_channel:
                try:
                    container = KyroContainer(accent_color=None)
                    container.add_section(
                        content=(
                            "**Voice Channel Inactivity Disconnect**\n"
                            f"> Disconnected from {channel.mention} due to **2 minutes** of inactivity."
                        )
                    )
                    await send_container_response(player.home_channel, container)
                except Exception:
                    pass

            await player.stop()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Empty VC timeout worker error: {e}", exc_info=True)

    # ==========================================
    # Prefix & Slash Commands
    # ==========================================

    @commands.hybrid_command(
        name="join",
        aliases=["connect", "j"],
        description="Connect Kyro to your current voice channel.",
    )
    async def join(self, ctx: CustomContext) -> None:
        """Connect to voice channel with smart moving support."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            container = KyroContainer(accent_color=None)
            container.add_text("**You must be in a voice channel to use this command.**")
            await send_container_response(ctx, container)
            return

        target_channel = ctx.author.voice.channel
        player = self.controller.get_or_create_player(ctx.guild)
        player.home_channel = ctx.channel

        bot_vc = ctx.guild.me.voice.channel if ctx.guild.me.voice else None
        if bot_vc:
            if bot_vc.id == target_channel.id:
                container = KyroContainer(accent_color=None)
                container.add_text(f"**Already connected to** {target_channel.mention}.")
                await send_container_response(ctx, container)
                return

            current_listeners = [m for m in bot_vc.members if not m.bot]
            # Only block moving if actively playing AND has active human listeners
            if player.is_playing and len(current_listeners) > 0:
                container = KyroContainer(accent_color=None)
                container.add_section(
                    content=(
                        "**Voice Channel Conflict**\n"
                        f"> I am currently streaming music for {len(current_listeners)} listener(s) in {bot_vc.mention}.\n"
                        "> Please join that channel or stop playback first."
                    )
                )
                await send_container_response(ctx, container)
                return

        try:
            player.cancel_empty_vc_timer(auto_resume=False)
            await player.connect_voice(target_channel)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Voice Channel Connected**\n"
                    f"> Connected to {target_channel.mention}. Ready to play music!"
                )
            )
            await send_container_response(ctx, container)
        except Exception as e:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Failed to connect to voice channel:** `{e}`")
            await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="listen",
        aliases=["voicecommand", "vc", "speech"],
        description="Toggle AI Voice Recognition to control music with your mic (e.g. 'Kyro play <song>').",
    )
    @app_commands.describe(state="Enable or disable voice listening: on, off, or toggle")
    async def listen(self, ctx: CustomContext, state: Optional[str] = "") -> None:
        """Toggle AI Voice Recognition for hands-free mic commands."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            container = KyroContainer(accent_color=None)
            container.add_text("**You must be in a voice channel to use this command.**")
            await send_container_response(ctx, container)
            return

        target_channel = ctx.author.voice.channel
        player = self.controller.get_or_create_player(ctx.guild)
        player.home_channel = ctx.channel

        mode = state.lower().strip() if state else ("off" if player.voice_listening else "on")
        if mode in ("on", "enable", "start", "true"):
            try:
                success, err_msg = await player.start_voice_listening(target_channel)
            except Exception as e:
                success = False
                err_msg = str(e)

            container = KyroContainer(accent_color=None)
            if success:
                container.add_section(
                    content=(
                        "**AI Voice Commander Activated**\n"
                        "> Kyro is now actively listening to voice commands in your voice channel.\n\n"
                        "**Supported Wake-Word Prefixes:**\n"
                        "> • `Kyro play <song name>`\n"
                        "> • `Kyro pause` • `Kyro resume`\n"
                        "> • `Kyro skip` • `Kyro stop`\n"
                        "> • `Kyro volume <0-100>`"
                    )
                )
                container.add_separator(divider=True)
                container.add_text("-# Speak clearly into your mic • Use ?listen off to stop")
            else:
                reason = f"\n> `{err_msg}`" if err_msg else ""
                container.add_text(f"**Failed to activate AI Voice Commander.**{reason}")
            await send_container_response(ctx, container)
        else:
            player.stop_voice_listening()
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**AI Voice Commander Deactivated**\n"
                    "> Kyro stopped listening for voice commands in your channel."
                )
            )
            await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="play",
        aliases=["p"],
        description="Play high-fidelity music tracks directly in your voice channel.",
    )
    @app_commands.describe(query="Song title, artist name, Spotify or YouTube URL")
    async def play(self, ctx: CustomContext, *, query: Optional[str] = None) -> None:
        """Play high-fidelity music tracks in your voice channel."""
        await execute_play(self, ctx, query)

    @commands.hybrid_command(
        name="autoplay",
        aliases=["ap"],
        description="Toggle Smart Autoplay to play continuous radio based on played songs.",
    )
    @app_commands.describe(state="Action: on, off, or toggle")
    async def autoplay(self, ctx: CustomContext, state: Optional[str] = "") -> None:
        """Toggle Autoplay mode."""
        await execute_autoplay(self, ctx, state or "")

    @commands.hybrid_command(
        name="pause",
        description="Pause the currently playing music stream.",
    )
    async def pause(self, ctx: CustomContext) -> None:
        """Pause playback."""
        await execute_pause(self, ctx)

    @commands.hybrid_command(
        name="resume",
        aliases=["unpause"],
        description="Resume paused music stream.",
    )
    async def resume(self, ctx: CustomContext) -> None:
        """Resume playback."""
        await execute_resume(self, ctx)

    @commands.hybrid_command(
        name="skip",
        aliases=["s", "next"],
        description="Skip the current track to the next song in queue.",
    )
    async def skip(self, ctx: CustomContext) -> None:
        """Skip currently playing track."""
        await execute_skip(self, ctx)

    @commands.hybrid_command(
        name="stop",
        aliases=["disconnect", "dc"],
        description="Stop playback, clear queue, and disconnect from voice.",
    )
    async def stop(self, ctx: CustomContext) -> None:
        """Stop music, clear queue and leave voice."""
        await execute_stop(self, ctx)

    @commands.hybrid_command(
        name="queue",
        aliases=["q"],
        description="Display the upcoming server music playlist.",
    )
    @app_commands.describe(page="Queue page number")
    async def queue(self, ctx: CustomContext, page: int = 1) -> None:
        """Show current song queue."""
        await execute_queue(self, ctx, page)

    @commands.hybrid_command(
        name="nowplaying",
        aliases=["now", "playing"],
        description="Display the currently playing song with interactive controls.",
    )
    async def nowplaying(self, ctx: CustomContext) -> None:
        """Show currently playing song details."""
        await execute_nowplaying(self, ctx)

    @commands.hybrid_command(
        name="loop",
        description="Toggle loop mode between off, track, and entire queue.",
    )
    @app_commands.describe(mode="Loop mode: off, track, or queue")
    async def loop(self, ctx: CustomContext, mode: str = "track") -> None:
        """Toggle loop mode."""
        await execute_loop(self, ctx, mode)

    @commands.hybrid_command(
        name="shuffle",
        description="Randomize the order of upcoming songs in queue.",
    )
    async def shuffle(self, ctx: CustomContext) -> None:
        """Shuffle queue."""
        await execute_shuffle(self, ctx)

    @commands.hybrid_command(
        name="clear",
        description="Clear all upcoming tracks from the queue.",
    )
    async def clear(self, ctx: CustomContext) -> None:
        """Clear queue."""
        await execute_clear(self, ctx)

    @commands.hybrid_command(
        name="volume",
        aliases=["vol"],
        description="Adjust playback volume (0 to 200 percent).",
    )
    @app_commands.describe(volume="Volume percentage from 0 to 200")
    async def volume(self, ctx: CustomContext, volume: int = 100) -> None:
        """Adjust playback volume."""
        await execute_volume(self, ctx, volume)

    @commands.hybrid_command(
        name="like",
        aliases=["fav", "favorite"],
        description="Save the currently playing song into your personal Favorites playlist.",
    )
    async def like(self, ctx: CustomContext) -> None:
        """Save current song to Favorites playlist."""
        await handle_like(ctx, self)

    @commands.hybrid_command(
        name="unlike",
        aliases=["unfav", "dislike"],
        description="Remove a song from your personal Favorites playlist by title or playing track.",
    )
    @app_commands.describe(query="Optional song title or track number to remove from Favorites")
    async def unlike(self, ctx: CustomContext, *, query: Optional[str] = None) -> None:
        """Remove a song from Favorites playlist."""
        await handle_unlike(ctx, self, query=query)

    @commands.hybrid_command(
        name="playlist",
        aliases=["pl"],
        description="Manage, play, view, and save custom song playlists.",
    )
    @app_commands.describe(
        action="Action: add, play, list, view, delete",
        name="Playlist name",
        query="Optional song title or URL (if adding a specific song)",
    )
    async def playlist(
        self,
        ctx: CustomContext,
        action: Optional[str] = None,
        name: Optional[str] = None,
        *,
        query: Optional[str] = None,
    ) -> None:
        """Manage custom user playlists."""
        await handle_playlist(ctx, self, action, name, query=query)


    @commands.hybrid_command(
        name="remove",
        description="Remove a specific track from the upcoming queue by its number.",
    )
    @app_commands.describe(index="Track number to remove from the queue")
    async def remove(self, ctx: CustomContext, index: int) -> None:
        """Remove a track from queue."""
        await execute_remove(self, ctx, index)

    @commands.hybrid_command(
        name="jump",
        aliases=["skipto"],
        description="Skip directly to a specific track number in the queue.",
    )
    @app_commands.describe(index="Track number to skip directly to")
    async def jump(self, ctx: CustomContext, index: int) -> None:
        """Skip directly to a track in queue."""
        await execute_jump(self, ctx, index)

    @commands.hybrid_command(
        name="247",
        aliases=["stay"],
        description="Toggle 24/7 mode to keep Kyro connected in voice even when empty.",
    )
    @commands.has_permissions(manage_guild=True)
    async def stay_247(self, ctx: CustomContext) -> None:
        """Toggle 24/7 voice stay mode."""
        await execute_stay(self, ctx)


async def setup(bot: KyroBot) -> None:
    """Load the Music Cog into KyroBot."""
    await bot.add_cog(Music(bot))
