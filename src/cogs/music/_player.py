"""
Kyro Discord Bot - Lavalink Guild Audio Player
Streamlined, zero-lag, zero-stutter audio streaming powered by NexCloud Lavalink v4.
Offloads all heavy audio processing, buffering, and encoding from Render/PC to the Lavalink node.
Maintains full compatibility with Kyro Components V2 interactive cards and commands.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING, Any, List, Optional, Set
import discord
import wavelink

from src.cogs.music._models import Track
from src.cogs.music._autoplay import NativeSmartAutoplay
from src.core.lavalink import (
    LAVALINK_OP_TIMEOUT,
    LAVALINK_PLAY_TIMEOUT,
    LAVALINK_RESOLVE_TIMEOUT,
    close_pool_nodes,
    connect_lavalink_node,
    err_text,
    probe_node,
)
from src.utils.containers import KyroContainer, send_container_response, edit_container_response
from src.cogs.music._views import MusicControlView

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Music.Player")


def shorten_artist(artist: str, max_len: int = 30) -> str:
    """Safely truncate artist string for embeds."""
    if not artist:
        return "Unknown"
    return artist if len(artist) <= max_len else artist[:max_len - 3] + "..."


class KyroPlayer(wavelink.Player):
    """
    Hardened Wavelink 3 Player with Bidirectional Gateway Handshake Defense.

    Fixes three critical upstream flaws in Wavelink 3:
    1. Out-of-Order Handshake Stalls:
       Discord sends VOICE_STATE_UPDATE and VOICE_SERVER_UPDATE in non-deterministic order.
       Upstream Wavelink only calls `_dispatch_voice_update()` inside `on_voice_server_update`.
       If VOICE_SERVER_UPDATE arrives before VOICE_STATE_UPDATE, Wavelink drops the dispatch
       and hangs on `_connection_event.wait()` until timeout (20s).
       KyroPlayer intercepts `on_voice_state_update` to trigger the dispatch as soon as all
       credentials (sessionId, token, endpoint) are present.
    2. Fast Failure Trapping:
       Upstream Wavelink swallows Lavalink exceptions in `_dispatch_voice_update` and silently
       calls `self.disconnect()`, leaving `connect()` hanging until the timeout expires.
       KyroPlayer captures any transport error, stores it, and sets `_connection_event` so
       `connect()` raises the actual error immediately in <200ms instead of 20 seconds.
    3. Stale Disconnect Packet Guard:
       When reconnecting, Discord often emits a delayed `channel_id=None` packet from the
       prior session. Upstream Wavelink unconditionally destroys the player on `not channel_id`,
       killing the connection before the handshake completes. KyroPlayer drops stale null packets
       while connection is in flight.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._connect_error: Optional[Exception] = None
        self._dispatch_lock: asyncio.Lock = asyncio.Lock()

        # Pre-populate voice state from Discord guild member if already available
        guild = getattr(self, "guild", None)
        if not guild and hasattr(self, "channel") and self.channel:
            guild = getattr(self.channel, "guild", None)
        if guild and guild.me and guild.me.voice:
            sid = getattr(guild.me.voice, "session_id", None)
            if sid:
                self._voice_state["voice"]["session_id"] = sid
                ch = getattr(guild.me.voice, "channel", None) or getattr(self, "channel", None)
                if ch:
                    self._voice_state["channel_id"] = str(ch.id)

    async def on_voice_state_update(self, data: Any, /) -> None:
        channel_id = data.get("channel_id")
        # Guard: If channel_id is None and we are still connecting, do NOT let upstream destroy the player!
        if not channel_id and (not self._connected or not self._connection_event.is_set()):
            logger.debug(
                f"KyroPlayer guild {self.guild.id if self.guild else 'unknown'}: "
                "ignoring stale null channel_id during handshake."
            )
            return

        await super().on_voice_state_update(data)
        if not channel_id:
            return

        # Check if voice server credentials (token & endpoint) are already buffered
        v = self._voice_state.get("voice", {})
        if v.get("token") and v.get("endpoint") and v.get("session_id"):
            if not self._connected or not self._connection_event.is_set():
                await self._dispatch_voice_update()

    async def _dispatch_voice_update(self) -> None:
        async with self._dispatch_lock:
            if self._connected and self._connection_event.is_set():
                return
            assert self.guild is not None
            data = self._voice_state.get("voice", {})
            session_id = data.get("session_id")
            if not session_id and self.guild.me and self.guild.me.voice:
                session_id = getattr(self.guild.me.voice, "session_id", None)
                if session_id:
                    self._voice_state["voice"]["session_id"] = session_id

            token = data.get("token")
            endpoint = data.get("endpoint")
            channel_id = self._voice_state.get("channel_id") or (
                str(self.channel.id) if self.channel else None
            )

            if not session_id or not token or not endpoint:
                return

            request = {
                "voice": {
                    "sessionId": session_id,
                    "token": token,
                    "endpoint": endpoint,
                    "channelId": channel_id,
                }
            }

            try:
                await self.node._update_player(self.guild.id, data=request)
                self._connected = True
                self._connection_event.set()
            except Exception as exc:
                logger.error(
                    f"Guild {self.guild.id}: Lavalink _update_player failed ({type(exc).__name__}: {exc})"
                )
                self._connect_error = exc
                self._connection_event.set()

    async def connect(
        self,
        *,
        timeout: float = 4.0,
        reconnect: bool = True,
        self_deaf: bool = False,
        self_mute: bool = False,
    ) -> None:
        self._connect_error = None
        try:
            await super().connect(
                timeout=timeout,
                reconnect=reconnect,
                self_deaf=self_deaf,
                self_mute=self_mute,
            )
            if self._connect_error is not None:
                err = self._connect_error
                self._connect_error = None
                raise err
        except BaseException as exc:
            if self._guild:
                self.node._players.pop(self._guild.id, None)
            raise exc


class GuildPlayer:
    """
    High-Performance Lavalink Guild Player for Kyro Bot.
    Replaces local FFmpeg subprocesses with dedicated Lavalink node streaming.
    """

    def __init__(self, bot: KyroBot, guild: discord.Guild) -> None:
        self.bot = bot
        self.guild = guild
        self.voice_client: Optional[wavelink.Player] = None

        # Playback state
        self.queue: List[Track] = []
        self.current: Optional[Track] = None
        self.volume: float = 1.0  # Normalized (1.0 = 100%)
        self.loop_mode: str = "off"  # "off", "track", "queue"
        self.smart_autoplay: bool = False
        self.autoplay_history: Set[str] = set()
        self.is_247: bool = False
        self._is_paused: bool = False

        # UI & Communication
        self.home_channel: Optional[discord.TextChannel | discord.Thread] = None
        self.controller_message: Optional[discord.Message] = None
        self._disconnect_announced: bool = False
        self._empty_vc_task: Optional[asyncio.Task] = None
        self._advance_lock: asyncio.Lock = asyncio.Lock()
        self._connect_lock: asyncio.Lock = asyncio.Lock()
        self._queue_lock: asyncio.Lock = asyncio.Lock()
        self._last_advance_time: float = 0.0
        self._last_manual_advance: float = 0.0
        self._advance_gen: int = 0
        self._is_prefetching: bool = False
        # Set by the MusicAgent before a self-heal disconnect so the queue survives.
        self.preserve_queue_on_disconnect: bool = False
        # Monotonic deadline until which a VOICE_STATE_UPDATE(channel=None) is treated as
        # the delayed answer to a disconnect Kyro initiated itself (reconnect / stop /
        # self-heal) instead of an external disconnect that must end the session.
        self._disconnect_expected_until: float = 0.0
        # Guard flag indicating that a connect_voice operation is currently in flight
        self._is_connecting: bool = False

    # ── State Properties ──

    @property
    def is_connected(self) -> bool:
        """Check if connected to a valid Discord voice channel."""
        vc = self.guild.voice_client
        return vc is not None and getattr(vc, "connected", False)

    @property
    def is_playing(self) -> bool:
        """Check if actively playing audio."""
        if self.is_paused or self.current is None:
            return False
        return self.is_connected

    @property
    def is_paused(self) -> bool:
        """Check if playback is currently paused."""
        if getattr(self, "_is_paused", False):
            return True
        vc = self.guild.voice_client
        if vc and isinstance(vc, wavelink.Player):
            return getattr(vc, "paused", False)
        return False

    # ── Thread-Safe Queue Operations ──

    async def add_track(self, track: Track) -> None:
        """Thread-safely append a single track to the queue."""
        async with self._queue_lock:
            self.queue.append(track)
        asyncio.create_task(self._prefetch_next_track())

    async def add_tracks(self, tracks: list[Track]) -> None:
        """Thread-safely append multiple tracks to the queue."""
        async with self._queue_lock:
            self.queue.extend(tracks)
        asyncio.create_task(self._prefetch_next_track())

    async def pop_next_track(self) -> Optional[Track]:
        """Thread-safely pop the next track from the front of the queue."""
        async with self._queue_lock:
            if self.queue:
                return self.queue.pop(0)
            return None

    async def clear_queue(self) -> int:
        """Thread-safely clear all tracks from the queue and return count."""
        async with self._queue_lock:
            cnt = len(self.queue)
            self.queue.clear()
            return cnt

    async def remove_track_at(self, index: int) -> Optional[Track]:
        """Thread-safely remove a track at index (0-based) from queue."""
        async with self._queue_lock:
            if 0 <= index < len(self.queue):
                return self.queue.pop(index)
            return None

    async def shuffle_queue(self) -> int:
        """Thread-safely shuffle the upcoming queue."""
        async with self._queue_lock:
            import random
            random.shuffle(self.queue)
            return len(self.queue)

    # ── Voice Connection ──

    async def connect_voice(self, channel: discord.VoiceChannel | discord.StageChannel) -> None:
        """Connect or move to the specified voice channel using Wavelink with race-condition locking."""
        async with self._connect_lock:
            self._is_connecting = True
            try:
                # Check if this guild has an active or in-flight Voice Meeting session
                meeting_cog = self.bot.get_cog("Meeting")
                if meeting_cog and (
                    self.guild.id in getattr(meeting_cog, "_sessions", {})
                    or self.guild.id in getattr(meeting_cog, "_connecting_guilds", set())
                ):
                    raise RuntimeError(
                        f"Cannot connect music player: Guild {self.guild.id} is currently running an active Voice Meeting."
                    )

                # 1. Pre-flight permission and capacity verification
                me = self.guild.me
                perms = channel.permissions_for(me)
                if not perms.connect:
                    raise RuntimeError(f"Kyro lacks 'Connect' permission to join {channel.name}.")
                if channel.user_limit and channel.user_limit > 0:
                    if len(channel.members) >= channel.user_limit and not perms.move_members:
                        raise RuntimeError(f"Voice channel {channel.name} is full ({len(channel.members)}/{channel.user_limit} members).")

                vc = self.guild.voice_client
                me_voice = self.guild.me.voice if self.guild.me else None
                bot_in_target_channel = bool(
                    me_voice is not None
                    and me_voice.channel is not None
                    and me_voice.channel.id == channel.id
                )

                # Case 1: Already fully connected to target channel
                if vc and isinstance(vc, wavelink.Player) and vc.connected:
                    if vc.channel and vc.channel.id == channel.id:
                        self.voice_client = vc
                        return
                    if vc.channel and vc.channel.id != channel.id:
                        try:
                            # Bounded: move_to talks to the Lavalink REST API.
                            await asyncio.wait_for(
                                vc.move_to(channel),
                                timeout=LAVALINK_OP_TIMEOUT,
                            )
                            self.voice_client = vc
                            return
                        except Exception as e:
                            logger.warning(
                                f"Guild {self.guild.id}: move_to {channel.name} failed: "
                                f"{type(e).__name__}: {e}"
                            )

                # Case 2: Bot is already physically in the target channel on Discord Gateway,
                # re-sync with Lavalink directly without disconnecting from Discord!
                if bot_in_target_channel and vc and isinstance(vc, wavelink.Player):
                    logger.info(
                        f"Guild {self.guild.id}: Bot already in #{channel.name}, syncing voice state with Lavalink..."
                    )
                    try:
                        if vc.node and hasattr(vc.node, "_players"):
                            vc.node._players[self.guild.id] = vc
                        if hasattr(vc, "_dispatch_voice_update"):
                            await vc._dispatch_voice_update()
                        if getattr(vc, "connected", False):
                            self.voice_client = vc
                            return
                    except Exception as sync_err:
                        logger.warning(f"Guild {self.guild.id}: In-place voice sync failed: {sync_err}")

                # If connected to an invalid, disconnected, or non-wavelink player, clean it up first
                if vc:
                    # Never disconnect an active Meeting VoiceRecvClient!
                    if meeting_cog and (
                        self.guild.id in getattr(meeting_cog, "_sessions", {})
                        or self.guild.id in getattr(meeting_cog, "_connecting_guilds", set())
                    ):
                        return

                    # Only perform gateway disconnect if the player is actively connected on Discord
                    if getattr(vc, "connected", False):
                        self._disconnect_expected_until = time.monotonic() + 4.0
                        try:
                            await asyncio.wait_for(
                                vc.disconnect(force=True),
                                timeout=1.5,
                            )
                        except Exception:
                            pass
                        await asyncio.sleep(0.15)
                    try:
                        vc.cleanup()
                    except Exception:
                        pass
                    self.voice_client = None

                # Purge lingering voice client cache so next handshake starts clean
                try:
                    self.bot._connection._remove_voice_client(self.guild.id)
                except Exception:
                    pass

                # If Discord Gateway still has us recorded in a voice channel but we don't have a working
                # active player, force a clean voice state reset so Discord emits fresh credentials on connect
                if self.guild.me and self.guild.me.voice and self.guild.me.voice.channel:
                    try:
                        self._disconnect_expected_until = time.monotonic() + 4.0
                        await self.guild.change_voice_state(channel=None)
                        await asyncio.sleep(0.15)
                    except Exception:
                        pass

                # Ensure Wavelink node is alive and connected before connecting player
                node = None
                try:
                    node = wavelink.Pool.get_node()
                except Exception:
                    pass

                if not node or node.status != wavelink.NodeStatus.CONNECTED:
                    logger.info("Wavelink node disconnected or missing. Re-establishing connection...")
                    try:
                        await close_pool_nodes()
                        node = await connect_lavalink_node(
                            self.bot,
                            inactive_player_timeout=300,
                        )
                    except Exception as e:
                        logger.error(f"On-demand Lavalink node connect error: {err_text(e)}")

                # ── Node REST health probe ──
                # Only probe if node status is not already CONNECTED
                if node is not None and getattr(node, "status", None) != wavelink.NodeStatus.CONNECTED:
                    if not await self._probe_lavalink_node(node):
                        logger.warning(
                            f"Guild {self.guild.id}: Lavalink REST API is not responsive, "
                            "re-establishing the node before connecting."
                        )
                        agent = getattr(self.bot, "_music_agent", None)
                        if agent is not None:
                            try:
                                await agent.heal_node(force=True)
                            except Exception as heal_err:
                                logger.error(f"Guild {self.guild.id}: Lavalink node heal failed: {heal_err}")
                        try:
                            node = wavelink.Pool.get_node()
                        except Exception:
                            node = None

                # Connect as hardened KyroPlayer with fast retry on temporary Discord gateway blip
                last_error: Optional[BaseException] = None
                for attempt in range(2):
                    try:
                        self.voice_client = await channel.connect(cls=KyroPlayer, self_deaf=True, timeout=4.0)
                        if self.voice_client:
                            self.voice_client.autoplay = wavelink.AutoPlayMode.disabled
                        last_error = None
                        break
                    except Exception as e:
                        last_error = e
                        logger.warning(
                            f"Guild {self.guild.id}: Voice connect attempt {attempt + 1}/2 failed "
                            f"({type(e).__name__}: {e}), refreshing voice state..."
                        )
                        stale_vc = self.guild.voice_client
                        if stale_vc:
                            self._disconnect_expected_until = time.monotonic() + 4.0
                            if getattr(stale_vc, "connected", False):
                                try:
                                    await asyncio.wait_for(
                                        stale_vc.disconnect(force=True),
                                        timeout=1.5,
                                    )
                                except Exception:
                                    pass
                            try:
                                stale_vc.cleanup()
                            except Exception:
                                pass
                        try:
                            self.bot._connection._remove_voice_client(self.guild.id)
                        except Exception:
                            pass
                        self.voice_client = None

                        # Force Discord Gateway to clear old session if registered in a channel
                        if self.guild.me and self.guild.me.voice and self.guild.me.voice.channel:
                            try:
                                self._disconnect_expected_until = time.monotonic() + 4.0
                                await self.guild.change_voice_state(channel=None)
                                await asyncio.sleep(0.15)
                            except Exception:
                                pass

                        # After first failure, heal node only if unresponsive and pause 0.3s before second attempt
                        if attempt == 0:
                            agent = getattr(self.bot, "_music_agent", None)
                            if agent is not None:
                                try:
                                    await agent.heal_node(force=False)
                                except Exception as heal_err:
                                    logger.error(f"Guild {self.guild.id}: Lavalink node heal failed: {heal_err}")
                            await asyncio.sleep(0.3)

                if last_error is not None:
                    logger.error(f"Guild {self.guild.id}: Wavelink connect error: {last_error}")
                    if hasattr(self.bot, "sentinel") and self.bot.sentinel:
                        from src.sentinel.models import SubsystemType, IncidentSeverity
                        self.bot.sentinel.record_incident(
                            SubsystemType.VOICE,
                            IncidentSeverity.WARNING,
                            "Voice Gateway Connect Failure",
                            f"Failed connecting to channel {channel.name} ({channel.id}): "
                            f"{type(last_error).__name__}: {last_error}",
                            action_taken="Purged stale voice client & gateway state (queue preserved)",
                            resolved=True,
                            guild_id=self.guild.id,
                        )
                    raise last_error
            finally:
                self._is_connecting = False

    async def _probe_lavalink_node(self, node: Any, timeout: float = 4.0) -> bool:
        """
        Verify the Lavalink node REST API is actually responsive.

        The websocket can be alive while the REST API is slow or unreachable -
        and the Wavelink voice handshake only completes after a successful REST
        call, so a dead REST API silently turns into a voice connect timeout.
        """
        return await probe_node(node, timeout=timeout)

    # ── Playback Engine ──

    async def play_track(self, track: Track, message_to_edit: Optional[discord.Message] = None) -> None:
        """Stream a track via the dedicated Lavalink node with 0% stutter."""
        # 1. Verify voice connection or attempt fast recovery
        if not self.voice_client or not self.voice_client.connected:
            vc = self.guild.voice_client
            if vc and isinstance(vc, wavelink.Player) and vc.connected:
                self.voice_client = vc

        if not self.voice_client or not self.voice_client.connected:
            target_ch = getattr(self.guild.me.voice, "channel", None)
            if target_ch:
                try:
                    await self.connect_voice(target_ch)
                except Exception:
                    pass

        if not self.voice_client or not self.voice_client.connected:
            logger.warning(f"Guild {self.guild.id}: Cannot play, voice client not connected.")
            if message_to_edit and isinstance(message_to_edit, discord.Message):
                err_c = KyroContainer(accent_color=None)
                err_c.add_text("**Voice Disconnected**\n> Kyro is not connected to a voice channel. Please join a voice channel and use `?play` to start.")
                try:
                    await edit_container_response(message_to_edit, err_c)
                except Exception:
                    pass
            return

        # 2. Direct playable if already attached, otherwise resolve via Lavalink with strict timeout
        playable = getattr(track, "_playable", None)
        if not playable:
            try:
                playable = await self._resolve_playable(track)
            except Exception as e:
                logger.error(f"Error resolving playable for '{track.title}': {e}")
                playable = None

        if not playable:
            logger.warning(f"Guild {self.guild.id}: Lavalink could not resolve playable for '{track.title}'. Skipping to next track.")
            next_t = await self.pop_next_track()
            if next_t:
                await self.play_track(next_t, message_to_edit=message_to_edit)
            else:
                self.current = None
                if message_to_edit and isinstance(message_to_edit, discord.Message):
                    err_c = KyroContainer(accent_color=None)
                    err_c.add_text(f"**Failed to Stream Track:** `{track.title}`\n> The audio source could not be loaded. Please try another song.")
                    try:
                        await edit_container_response(message_to_edit, err_c)
                    except Exception:
                        pass
                else:
                    await self.send_queue_ended_card()
                self.schedule_empty_vc_timer()
            return

        self.current = track
        self.autoplay_history.add(track.title.lower())
        self._was_paused_for_empty_vc = False
        self._is_paused = False
        self.cancel_empty_vc_timer(auto_resume=False)

        # 3. Start playback on Lavalink node with volume (explicitly unpaused)
        vol_int = int(self.volume * 100)
        try:
            # Bounded: this call talks to the Lavalink REST API. Without a bound it
            # could block for the session's 300s default timeout and freeze the
            # command (and any lock it holds) for five minutes.
            await asyncio.wait_for(
                self.voice_client.play(playable, volume=vol_int, paused=False),
                timeout=LAVALINK_PLAY_TIMEOUT,
            )
        except Exception as play_err:
            logger.error(f"Guild {self.guild.id}: voice_client.play error for '{track.title}': {play_err}")
            if message_to_edit:
                err_c = KyroContainer(accent_color=None)
                err_c.add_text(f"**Failed to Stream Track:** `{track.title}`\n> Playback dispatch error: `{play_err}`")
                try:
                    await edit_container_response(message_to_edit, err_c)
                except Exception:
                    pass
            raise

        # 4. Send or edit sleek Now Playing card with buttons
        await self.send_now_playing_card(track, message_to_edit=message_to_edit)
        asyncio.create_task(self._prefetch_next_track())

    # Domains that are NOT direct audio streams — Lavalink can't play their page URLs
    _NON_STREAM_DOMAINS = (
        "spotify.com",
        "open.spotify.com",
        "music.youtube.com",
        "youtube.com/watch",
        "youtu.be",
    )

    def _is_direct_stream_url(self, url: str) -> bool:
        """Return True only if url is a raw audio stream Lavalink can play via HTTP."""
        if not url or not url.startswith(("http://", "https://")):
            return False
        u_low = url.lower()
        if any(domain in u_low for domain in ("googlevideo.com", "saavncdn.com", "jiosaavn.com", "akamai")):
            return True
        if any(ext in u_low for ext in (".mp4", ".m4a", ".mp3", ".webm", ".opus", ".aac", "videoplayback")):
            return True
        return False

    async def _prefetch_next_track(self) -> None:
        """Background pre-resolver: resolves upcoming track's Playable before current track ends."""
        if getattr(self, "_is_prefetching", False):
            return
        self._is_prefetching = True
        try:
            target_track: Optional[Track] = None
            async with self._queue_lock:
                for t in self.queue[:2]:
                    if not getattr(t, "_playable", None):
                        target_track = t
                        break
            if target_track:
                p = await self._resolve_playable(target_track)
                if p:
                    target_track._playable = p
                    logger.debug(f"Pre-fetched playable for upcoming track '{target_track.title}'")
        except Exception as e:
            logger.debug(f"Background prefetch notice: {e}")
        finally:
            self._is_prefetching = False

    async def _resolve_playable(self, track: Track) -> Optional[wavelink.Playable]:
        """Resolve a Lavalink Playable for a track with a hard overall deadline.

        The inner cascade can try up to five strategies twice each, so without an
        overall budget a single unresolvable track could keep the caller waiting
        for well over a minute. The whole resolution is capped here instead.
        """
        try:
            return await asyncio.wait_for(
                self._resolve_playable_cascade(track),
                timeout=LAVALINK_RESOLVE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Guild {self.guild.id}: playable resolution timed out after "
                f"{LAVALINK_RESOLVE_TIMEOUT:.0f}s for '{track.title}'."
            )
            return None
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(
                f"Guild {self.guild.id}: playable resolution failed for '{track.title}': "
                f"{type(e).__name__}: {e}"
            )
            return None

    async def _resolve_playable_cascade(self, track: Track) -> Optional[wavelink.Playable]:
        """Resolve Lavalink Playable via attached playable, direct YouTube/Spotify URL, or resilient search cascade.

        Each search strategy is retried once on TimeoutError with a short backoff.
        Timeouts are set to 10s to survive transient Lavalink / YouTube 429 slowness.
        """
        # ── Priority 1: Attached Playable (already resolved) ──
        playable = getattr(track, "_playable", None)
        if playable:
            return playable

        # ── Priority 1.5: Direct Stream URL Resolution (JioSaavn Akamai MP4/AAC / HTTP Stream) ──
        stream_url = track.stream_url or ""
        if stream_url.startswith(("http://", "https://")):
            try:
                results = await asyncio.wait_for(wavelink.Playable.search(stream_url), timeout=4.0)
                if results:
                    p = results[0] if isinstance(results, list) else results.tracks[0]
                    track._playable = p
                    return p
            except Exception as e:
                logger.debug(f"Direct stream_url resolution error for '{track.title}': {e}")

        # ── Priority 2: Direct URL Resolution (for YouTube/SoundCloud/Direct URLs) ──
        url = track.url or ""
        if url.startswith(("http://", "https://")) and not any(sp in url for sp in ("spotify.com", "spoti.fi")):
            try:
                results = await asyncio.wait_for(wavelink.Playable.search(url), timeout=3.0)
                if results:
                    p = results[0] if isinstance(results, list) else results.tracks[0]
                    track._playable = p
                    return p
            except Exception as e:
                logger.debug(f"Direct URL resolution error for '{url}': {e}")

        # ── Priority 3: High-Speed YouTube Music Search (~0.8s) ──
        from src.cogs.music._extractor import clean_track_title
        clean_title = clean_track_title(track.title) if track.title else ""
        raw_author = track.author if (track.author and "spotify" not in track.author.lower() and "unknown" not in track.author.lower() and "artist" != track.author.lower() and "youtube" != track.author.lower()) else ""
        
        # Clean title of video junk like (Official Video), [Music Video], etc. so YouTube Music matches the exact song
        import re
        pure_title = re.sub(r"\(.*?(?:official|video|audio|remix|lyrics|hd|4k|feat|ft).*?\)|\[.*?(?:official|video|audio|remix|lyrics|hd|4k|feat|ft).*?\]", "", clean_title, flags=re.IGNORECASE).strip()
        pure_title = pure_title or clean_title

        full_query = f"{pure_title} {raw_author}".strip() or track.query or track.title or ""

        if full_query:
            try:
                results = await asyncio.wait_for(
                    wavelink.Playable.search(full_query, source=wavelink.TrackSource.YouTubeMusic),
                    timeout=2.0,
                )
                if results:
                    p = results[0] if isinstance(results, list) else results.tracks[0]
                    track._playable = p
                    return p
            except Exception as e:
                logger.debug(f"YouTube Music search error for '{full_query}': {e}")

        # ── Priority 4: Standard YouTube Fallback ──
        search_target = pure_title or clean_title or full_query
        if search_target:
            try:
                results = await asyncio.wait_for(
                    wavelink.Playable.search(search_target, source=wavelink.TrackSource.YouTube),
                    timeout=2.0,
                )
                if results:
                    p = results[0] if isinstance(results, list) else results.tracks[0]
                    track._playable = p
                    return p
            except Exception as e:
                logger.debug(f"YouTube fallback search error for '{search_target}': {e}")

        # ── Priority 5: JioSaavn Unblocked Audio Engine (Akamai CDN Stream) ──
        try:
            from src.cogs.music._extractor import NativeExtractor
            saavn_target = pure_title or clean_title or full_query or track.title
            saavn_trk = await asyncio.wait_for(
                NativeExtractor._extract_jiosaavn(saavn_target, requester=track.requester, is_autoplay=track.is_autoplay),
                timeout=4.0,
            )
            if saavn_trk and saavn_trk.stream_url:
                results = await asyncio.wait_for(wavelink.Playable.search(saavn_trk.stream_url), timeout=4.0)
                if results:
                    p = results[0] if isinstance(results, list) else results.tracks[0]
                    track._playable = p
                    track.stream_url = saavn_trk.stream_url
                    if not track.thumbnail:
                        track.thumbnail = saavn_trk.thumbnail
                    return p
        except Exception as e:
            logger.debug(f"JioSaavn playable fallback notice for '{track.title}': {e}")

        # ── Priority 6: SoundCloud Fallback ──
        if search_target:
            try:
                results = await asyncio.wait_for(
                    wavelink.Playable.search(search_target, source=wavelink.TrackSource.SoundCloud),
                    timeout=3.0,
                )
                if results:
                    p = results[0] if isinstance(results, list) else results.tracks[0]
                    track._playable = p
                    return p
            except Exception as e:
                logger.debug(f"SoundCloud fallback notice for '{search_target}': {e}")

        logger.warning(f"All resolution strategies exhausted for '{track.title}'")
        return None


    # ── Controls ──

    @staticmethod
    async def _bounded_node_call(coro: Any, timeout: float = LAVALINK_OP_TIMEOUT) -> None:
        """
        Run a Lavalink REST call with a hard deadline.

        Wavelink's aiohttp session uses the library default timeout of 300s, so a
        single unreachable node can keep a background task alive for five minutes.
        """
        try:
            await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug(f"Bounded Lavalink call failed: {type(e).__name__}: {e}")

    def pause(self) -> bool:
        """Pause playback."""
        if self.voice_client and self.current and not self.is_paused:
            self._is_paused = True
            try:
                self.voice_client._paused = True
            except Exception:
                pass
            asyncio.create_task(self._bounded_node_call(self.voice_client.pause(True)))
            return True
        return False

    def resume(self) -> bool:
        """Resume playback."""
        if self.voice_client and (self.is_paused or getattr(self.voice_client, "paused", False)):
            self._is_paused = False
            try:
                self.voice_client._paused = False
            except Exception:
                pass
            asyncio.create_task(self._bounded_node_call(self.voice_client.pause(False)))
            self._was_paused_for_empty_vc = False
            return True
        return False

    @staticmethod
    async def _safe_delete_message(msg: discord.Message) -> None:
        try:
            await msg.delete()
        except Exception:
            pass

    async def skip(self) -> None:
        """
        Skip the currently playing track.
        Directly pops the next queued track and plays it via Lavalink's native replacement.
        """
        if self.loop_mode == "track":
            self.loop_mode = "off"

        target = await self.pop_next_track()
        if target is not None:
            await self.play_track(target)
        else:
            self.current = None
            if self.voice_client:
                try:
                    await asyncio.wait_for(
                        self.voice_client.skip(force=True),
                        timeout=LAVALINK_OP_TIMEOUT,
                    )
                except Exception as e:
                    logger.debug(f"Guild {self.guild.id}: voice skip notice: {e}")
            await self.send_queue_ended_card()
            self.schedule_empty_vc_timer()


    async def stop(self) -> None:
        """Stop playback and disconnect."""
        self.cancel_empty_vc_timer(auto_resume=False)
        self.queue.clear()
        self.current = None
        self.autoplay_history.clear()
        self._was_paused_for_empty_vc = False
        self._is_paused = False

        if self.voice_client:
            # Mark this as a self-initiated disconnect so the matching
            # VOICE_STATE_UPDATE(channel=None) does not run the teardown twice.
            self._disconnect_expected_until = time.monotonic() + 5.0
            try:
                # Bounded: an unreachable node must not hang ?stop for minutes.
                await asyncio.wait_for(
                    self.voice_client.disconnect(force=True),
                    timeout=LAVALINK_OP_TIMEOUT,
                )
            except Exception as e:
                logger.warning(
                    f"Guild {self.guild.id}: voice disconnect failed: {type(e).__name__}: {e}"
                )
            self.voice_client = None

        # Clear reference without deleting card from chat
        self.controller_message = None

    def set_volume(self, volume_percent: int) -> int:
        """Adjust volume (0 - 150%)."""
        clamped = max(0, min(150, volume_percent))
        self.volume = clamped / 100.0
        if self.voice_client:
            asyncio.create_task(self._bounded_node_call(self.voice_client.set_volume(clamped)))
        return clamped

    def set_loop_mode(self, mode: Optional[str] = None) -> str:
        """
        Cycle loop mode or set specific mode ('off', 'track', 'queue').
        Accepts: 'off', 'track', 'queue', 'song', 'all', 'toggle', or None.
        """
        modes = ["off", "track", "queue"]
        m_str = (mode or "").strip().lower()

        if m_str in ("track", "song", "single", "1"):
            self.loop_mode = "track"
        elif m_str in ("queue", "all", "q"):
            self.loop_mode = "queue"
        elif m_str in ("off", "none", "disable", "stop", "0"):
            self.loop_mode = "off"
        else:
            cur_idx = modes.index(self.loop_mode) if self.loop_mode in modes else 0
            self.loop_mode = modes[(cur_idx + 1) % len(modes)]

        return self.loop_mode

    # ── Track End & Autoplay Transition ──

    async def on_track_end(
        self,
        reason: Optional[str] = None,
        *,
        manual: bool = False,
        expected_gen: Optional[int] = None,
    ) -> None:
        """
        Invoked when Lavalink finishes playing a track.

        `manual=True` is used by explicit user actions (skip/jump) which must
        ALWAYS advance, while event driven advances are debounced so a duplicate
        `TrackEndEvent` cannot skip two tracks at once.
        """
        if reason and str(reason).lower() in ("replaced", "cleanup"):
            return

        if reason and str(reason).lower() in ("loadfailed", "load_failed"):
            logger.warning(f"Guild {self.guild.id}: Lavalink reported track loadFailed.")
            # Unblocked recovery: if current track failed from YouTube, retry once with direct stream
            curr = self.current
            if curr and not getattr(curr, "_load_failed_retried", False):
                curr._load_failed_retried = True
                try:
                    from src.cogs.music._extractor import NativeExtractor
                    if curr.query and not curr.query.startswith(("http://", "https://")):
                        query_target = curr.query
                    else:
                        query_target = f"{curr.title} {curr.author}".strip()
                    if curr.url and any(yt in curr.url for yt in ("youtube.com/", "youtu.be/")) and ("unknown" in query_target.lower() or not query_target):
                        try:
                            yt_t = await asyncio.wait_for(NativeExtractor._fetch_youtube_title(curr.url), timeout=3.0)
                            if yt_t:
                                query_target = yt_t
                        except Exception:
                            pass
                    logger.info(f"Guild {self.guild.id}: Attempting unblocked stream recovery for '{curr.title}'...")
                    fallback_trk = await asyncio.wait_for(
                        NativeExtractor._extract_jiosaavn(query_target, requester=curr.requester, is_autoplay=curr.is_autoplay),
                        timeout=5.0,
                    )
                    if fallback_trk and fallback_trk.stream_url:
                        fallback_trk._load_failed_retried = True
                        p = await self._resolve_playable(fallback_trk)
                        if p:
                            fallback_trk._playable = p
                            self.current = fallback_trk
                            # Update existing card in place to prevent duplicate embeds
                            await self.update_controller_message()
                            vol_int = int(self.volume * 100)
                            await self.voice_client.play(p, volume=vol_int, paused=False)
                            logger.info(f"Guild {self.guild.id}: Successfully recovered '{curr.title}' via unblocked audio stream.")
                            return

                    # Secondary recovery via SoundCloud if JioSaavn was unavailable
                    try:
                        sc_res = await asyncio.wait_for(
                            wavelink.Playable.search(query_target, source=wavelink.TrackSource.SoundCloud),
                            timeout=4.0,
                        )
                        if sc_res:
                            top_sc = sc_res[0] if isinstance(sc_res, list) else sc_res.tracks[0]
                            sc_trk = Track(
                                title=top_sc.title or curr.title,
                                author=top_sc.author or curr.author,
                                url=top_sc.uri or curr.url,
                                stream_url="",
                                duration=int((top_sc.length or 0) / 1000),
                                thumbnail=top_sc.artwork or curr.thumbnail,
                                requester=curr.requester,
                                is_autoplay=curr.is_autoplay,
                                query=curr.query,
                            )
                            sc_trk._playable = top_sc
                            sc_trk._load_failed_retried = True
                            self.current = sc_trk
                            await self.update_controller_message()
                            vol_int = int(self.volume * 100)
                            await self.voice_client.play(top_sc, volume=vol_int, paused=False)
                            logger.info(f"Guild {self.guild.id}: Successfully recovered '{curr.title}' via SoundCloud.")
                            return
                    except Exception as sc_err:
                        logger.debug(f"Guild {self.guild.id}: SoundCloud recovery notice: {sc_err}")
                except Exception as rec_err:
                    logger.debug(f"Guild {self.guild.id}: Stream recovery notice: {rec_err}")

            next_track = await self.pop_next_track()
            if next_track:
                await self.play_track(next_track)
            else:
                self.current = None
                await self.send_queue_ended_card()
                self.schedule_empty_vc_timer()
            return

        async with self._advance_lock:
            now = time.time()

            if manual:
                # A TrackEnd event already advanced the queue for this skip.
                if expected_gen is not None and self._advance_gen != expected_gen:
                    logger.debug(
                        f"Guild {self.guild.id}: skip advance skipped, "
                        "queue was already advanced by a TrackEnd event."
                    )
                    return
            else:
                # Debounce duplicate TrackEnd events (Lavalink emits one per skip).
                if now - self._last_advance_time < 0.8:
                    logger.debug(f"Guild {self.guild.id}: Duplicate on_track_end call debounced")
                    return
                # A locally advanced skip may still be followed by the node's own
                # TrackEnd event — ignore it within a short window to avoid double-skip.
                # Window reduced to 1.5s (was 2.0s) so rapid legitimate user skips
                # are not incorrectly blocked.
                if self._last_manual_advance and (now - self._last_manual_advance) < 1.5:
                    logger.debug(
                        f"Guild {self.guild.id}: Redundant TrackEnd event after a manually "
                        "advanced skip ignored (within 1.5s window)"
                    )
                    self._last_advance_time = now
                    return

            self._last_advance_time = now
            self._advance_gen += 1
            if manual:
                self._last_manual_advance = now

            # ── Critical section: only in-memory state decisions ──
            # The lock must NOT be held while a track is resolved or dispatched:
            # both talk to the Lavalink node and can take many seconds. Holding it
            # here meant one slow advance blocked every later ?skip / ?jump /
            # track-end for the whole duration.
            if self.loop_mode == "track" and self.current:
                target: Optional[Track] = self.current
            else:
                if self.loop_mode == "queue" and self.current:
                    await self.add_track(self.current)
                target = await self.pop_next_track()

        # ── Slow work happens OUTSIDE the advance lock ──
        if target is not None:
            await self.play_track(target)
            return

        if self.smart_autoplay and self.current:
            # Smart Autoplay AI recommendation
            try:
                rec = await NativeSmartAutoplay.get_next_recommendation(
                    self.current, self.autoplay_history, self.bot.db
                )
                if rec:
                    rec.requester = "⚡ Smart Autoplay"
                    await self.play_track(rec)
                else:
                    self.current = None
                    await self.send_queue_ended_card()
                    self.schedule_empty_vc_timer()
            except Exception as e:
                logger.error(f"Guild {self.guild.id}: Smart autoplay error: {e}", exc_info=True)
                self.current = None
                await self.send_queue_ended_card()
                self.schedule_empty_vc_timer()
        else:
            self.current = None
            await self.send_queue_ended_card()
            self.schedule_empty_vc_timer()

    # ── Components V2 Controller Card ──

    def build_now_playing_container(self, track: Track) -> KyroContainer:
        """Construct the Components V2 Now Playing card matching custom layout."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        heart_e = ""
        if e_reg:
            heart_e = (
                e_reg.get("heart_dot", "")
                or e_reg.get("icons_heart", "")
                or e_reg.get("heart", "")
            )
        link_emoji = e_reg.get("link", "") if e_reg else ""

        container = KyroContainer(accent_color=None)

        # 1. Title: Now Playing (ZERO emoji on title)
        container.add_text("## Now Playing")

        # 2. 1 Divider line directly beneath Now Playing
        container.add_separator(divider=True)

        # 3. Song, Artist, and Duration with heart emoji in front (NO normal/unicode emojis, no source)
        safe_title = track.title.replace("[", "(").replace("]", ")")
        song_display = f"[{safe_title}]({track.url})" if track.url else safe_title
        artist_display = track.author or "Unknown Artist"
        duration_display = track.formatted_duration or "00:00"

        dot_prefix = f"> {heart_e} " if heart_e else "> "
        link_prefix = f"{link_emoji} " if link_emoji else ""

        body_lines = [
            f"{dot_prefix}**Song:** {song_display}",
            f"{dot_prefix}**Artist:** `{artist_display}`",
            f"{dot_prefix}**Duration:** `{duration_display}`",
        ]

        container.add_section(content="\n".join(body_lines))

        # Resolve thumbnail (fallback to YouTube thumbnail if missing)
        thumb = track.thumbnail
        if not thumb and track.url and ("youtube.com" in track.url or "youtu.be" in track.url):
            import re
            m = re.search(r"(?:v=|\/|youtu\.be\/)([0-9A-Za-z_-]{11})", track.url)
            if m:
                thumb = f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg"
                track.thumbnail = thumb

        if thumb:
            container.add_thumbnail(thumb)

        # 4. Divider line before footer
        container.add_separator(divider=True)

        # 5. Footer: Requested by ONLY
        container.add_text(f"-# Requested by: {track.requester}")

        # 6. Divider line after footer before action row buttons
        container.add_separator(divider=True)
        return container

    async def send_now_playing_card(self, track: Track, message_to_edit: Optional[discord.Message] = None) -> None:
        """Post or edit the interactive Now Playing card in home channel."""
        if not self.home_channel:
            return

        container = self.build_now_playing_container(track)
        view = MusicControlView(self.bot, player=self, track_url=track.url)

        # 1. If message_to_edit is provided, edit it directly (e.g. replacing 'Searching...' card)
        if message_to_edit and isinstance(message_to_edit, discord.Message):
            try:
                await edit_container_response(message_to_edit, container, view=view, content=None)
                self.controller_message = message_to_edit
                return
            except Exception:
                pass

        # 2. Clean up any existing controller card to prevent duplicate cards in chat (in background)
        if self.controller_message and isinstance(self.controller_message, discord.Message):
            old_msg = self.controller_message
            self.controller_message = None
            asyncio.create_task(self._safe_delete_message(old_msg))

        # 3. Post a fresh Now Playing card
        try:
            msg = await send_container_response(
                self.home_channel, container, view=view, content=None
            )
            if isinstance(msg, discord.Message):
                self.controller_message = msg
        except Exception as e:
            logger.debug(f"Failed to send now playing card: {e}")

    async def update_controller_message(self, force: bool = False) -> None:
        """Refresh active controller card."""
        if not self.controller_message or not self.current:
            return

        container = self.build_now_playing_container(self.current)
        view = MusicControlView(self.bot, player=self, track_url=self.current.url)
        try:
            await edit_container_response(self.controller_message, container, view=view, content=None)
        except Exception as e:
            logger.debug(f"Failed to edit controller message: {e}")

    async def send_queue_ended_card(self) -> None:
        """Post or edit the Queue Ended card in home channel."""
        if not self.home_channel:
            return

        e_reg = getattr(self.bot, "custom_emojis", None)
        dot = e_reg.get("heart_dot", "") if hasattr(e_reg, "get") else ""
        bullet = f"{dot} " if dot else "> "

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"# **Queue Concluded**\n"
                f"{bullet}All queued songs have finished playing.\n"
                f"> Add more tracks using `?play <song>` or enable autoplay with `?autoplay on`!"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Disconnecting in 3 minutes if no new songs are added.")
        container.add_separator(divider=True)

        if self.controller_message and isinstance(self.controller_message, discord.Message):
            try:
                await edit_container_response(
                    self.controller_message,
                    container,
                    view=None,
                    content=None,
                )
                self.controller_message = None
                return
            except Exception:
                pass

        try:
            await send_container_response(
                self.home_channel,
                container,
                content=None,
            )
        except Exception:
            pass

    # ── Inactivity Timers ──

    def cancel_empty_vc_timer(self, auto_resume: bool = False) -> None:
        """Cancel idle disconnect timer."""
        if self._empty_vc_task and not self._empty_vc_task.done():
            self._empty_vc_task.cancel()
            self._empty_vc_task = None

    def schedule_empty_vc_timer(self) -> None:
        """Schedule disconnect after 3 minutes of idle queue."""
        if getattr(self, "is_247", False):
            return
        self.cancel_empty_vc_timer()
        self._empty_vc_task = asyncio.create_task(self._empty_vc_timeout(180))

    async def _empty_vc_timeout(self, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
            if getattr(self, "is_247", False):
                return
            if not self.is_playing and not self.queue:
                logger.info(f"Guild {self.guild.id}: Idle timeout reached, disconnecting silently.")
                await self.stop()
        except asyncio.CancelledError:
            pass
