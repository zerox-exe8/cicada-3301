from __future__ import annotations

import array
import asyncio
import base64
import io
import json
import logging
import os
import struct
import time
import wave
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from src.repositories.meeting_repo import MeetingRepository

try:
    import discord.ext.voice_recv as voice_recv
    VOICE_RECV_AVAILABLE = True
    AudioSinkBase = voice_recv.AudioSink

    # Guard: Ensures all monkey-patches are applied EXACTLY ONCE across the entire
    # process lifetime, even if this module is re-imported or the cog is hot-reloaded.
    # We store this on the 'discord' module because discord is never reloaded by cog reloads.
    _MEETING_PATCHES_APPLIED: bool = getattr(discord, "_KYRO_MEETING_PATCHES_APPLIED", False)

    if not _MEETING_PATCHES_APPLIED:
        # 1. Discord.py bug workaround: SocketReader starts paused and clears _idle_paused.
        # Its register() checks if self._idle_paused before setting _running, which evaluates
        # to False, leaving the socket reading thread permanently deadlocked.
        import discord.voice_state as _vs

        def _fixed_socket_reader_register(self, callback) -> None:
            self._callbacks.append(callback)
            self._idle_paused = False
            self._running.set()

        _vs.SocketReader.register = _fixed_socket_reader_register

        # 2. Discord.py DAVE Voice WebSocket Patch:
        # Discord.py 2.7.1 places DAVE_PREPARE_EPOCH (Opcode 24) and transitions under
        # 'elif self._connection.dave_session:'. If SESSION_DESCRIPTION starts at protocol 0,
        # dave_session is None, skipping DAVE_PREPARE_EPOCH, leaving dave_session uninitialized
        # and dropping all subsequent binary MLS frames.
        import davey
        import discord.gateway as _gw
        import discord.ext.voice_recv.opus as _vropus

        _orig_voice_ws_received_message = _gw.DiscordVoiceWebSocket.received_message
        _orig_voice_ws_received_binary_message = _gw.DiscordVoiceWebSocket.received_binary_message

        async def _patched_voice_ws_received_message(self: _gw.DiscordVoiceWebSocket, msg: dict[str, Any]) -> None:
            op = msg.get("op")
            data = msg.get("d") or {}
            state = self._connection

            if op == self.DAVE_PREPARE_EPOCH:
                epoch = data.get("epoch")
                proto_ver = data.get("protocol_version", 1)
                if epoch == 1:
                    state.dave_protocol_version = proto_ver
                    try:
                        await state.reinit_dave_session()
                    except Exception:
                        pass

            elif op == self.DAVE_PREPARE_TRANSITION:
                transition_id = data.get("transition_id")
                proto_ver = data.get("protocol_version", 1)
                if transition_id is not None:
                    state.dave_pending_transitions[transition_id] = proto_ver
                    if transition_id == 0:
                        await state._execute_transition(transition_id)
                    else:
                        if proto_ver == 0 and state.dave_session:
                            state.dave_session.set_passthrough_mode(True, 120)
                        await self.send_transition_ready(transition_id)

            elif op == self.DAVE_EXECUTE_TRANSITION:
                transition_id = data.get("transition_id")
                if transition_id is not None:
                    await state._execute_transition(transition_id)

            return await _orig_voice_ws_received_message(self, msg)

        async def _patched_voice_ws_received_binary_message(self: _gw.DiscordVoiceWebSocket, msg: bytes) -> None:
            if len(msg) >= 3:
                op = msg[2]
                # MLS binary opcodes: 25=EXTERNAL_SENDER, 27=PROPOSALS, 29=ANNOUNCE_COMMIT_TRANSITION, 30=WELCOME
                if op in (
                    self.MLS_EXTERNAL_SENDER,
                    self.MLS_PROPOSALS,
                    self.MLS_ANNOUNCE_COMMIT_TRANSITION,
                    self.MLS_WELCOME,
                ):
                    state = self._connection
                    if state.dave_session is None:
                        state.dave_protocol_version = max(getattr(state, "dave_protocol_version", 1), 1)
                        try:
                            await state.reinit_dave_session()
                        except Exception:
                            pass

            return await _orig_voice_ws_received_binary_message(self, msg)

        _gw.DiscordVoiceWebSocket.received_message = _patched_voice_ws_received_message
        _gw.DiscordVoiceWebSocket.received_binary_message = _patched_voice_ws_received_binary_message

        # 3. Discord-ext-voice-recv DAVE Decryption & Ciphertext Guard:
        # If dave_session is ready, decrypt inbound packets using per-user ratchet keys.
        # If decryption fails or session is not ready in an E2EE room, DROP the frame rather than
        # passing raw DAVE ciphertext into libopus (which throws OpusError and falls back to silence zeros).
        _orig_dave_decrypt_inner = _vropus.PacketDecoder._dave_decrypt_inner

        def _patched_dave_decrypt_inner(self: _vropus.PacketDecoder, packet: Any) -> bool:
            sink = getattr(self, "sink", None)
            if packet.is_silence():
                if sink:
                    sink._silence_pkts = getattr(sink, "_silence_pkts", 0) + 1
                return True

            vc = getattr(self.sink, "voice_client", None) if self.sink else None
            state = getattr(vc, "_connection", None)
            session = getattr(state, "dave_session", None)
            dave_ver = getattr(state, "dave_protocol_version", 0)

            # If DAVE session is ready, ALWAYS decrypt with MLS key
            if session is not None and getattr(session, "ready", False):
                user_id = self._cached_id
                if user_id is None and vc:
                    user_id = self._cached_id = vc._get_id_from_ssrc(self.ssrc)
                if user_id is None:
                    if sink:
                        sink._dave_fail = getattr(sink, "_dave_fail", 0) + 1
                        sink._last_dave_err = f"ssrc {self.ssrc} unmapped"
                    self._dave_log_drop("ssrc not mapped to a user yet")
                    return False

                try:
                    packet.decrypted_data = session.decrypt(
                        int(user_id), davey.MediaType.audio, bytes(packet.decrypted_data)
                    )
                    if sink:
                        sink._dave_succ = getattr(sink, "_dave_succ", 0) + 1
                        if user_id:
                            sink._ssrc_to_uid[self.ssrc] = user_id
                            if vc and getattr(vc, "guild", None):
                                m = vc.guild.get_member(user_id)
                                if m:
                                    sink.speaker_names[user_id] = m.display_name
                                elif user_id not in sink.speaker_names:
                                    sink.speaker_names[user_id] = f"User-{user_id}"
                    return True
                except BaseException as e:
                    if isinstance(e, (KeyboardInterrupt, SystemExit)):
                        raise
                    err_msg = str(e) or repr(e)
                    if sink:
                        sink._last_dave_err = err_msg
                        sink._dave_fail = getattr(sink, "_dave_fail", 0) + 1
                    if "UnencryptedWhenPassthroughDisabled" in err_msg:
                        if sink:
                            sink._dave_pass = getattr(sink, "_dave_pass", 0) + 1
                        try:
                            session.set_passthrough_mode(True, 120)
                        except Exception:
                            pass
                        return _orig_dave_decrypt_inner(self, packet)
                    self._dave_log_drop(f"DAVE decrypt error: {err_msg}")
                    return False

            if dave_ver > 0:
                # If session is in passthrough mode, decode standard frames directly
                if session is not None and getattr(session, "passthrough_mode", False):
                    return _orig_dave_decrypt_inner(self, packet)

                if sink:
                    sink._dave_fail = getattr(sink, "_dave_fail", 0) + 1
                    sink._last_dave_err = "session not ready"
                self._dave_log_drop(
                    f"DAVE v{dave_ver} awaiting MLS session ready (ready={getattr(session, 'ready', False) if session else 'None'})"
                )
                return False

            return _orig_dave_decrypt_inner(self, packet)

        _vropus.PacketDecoder._dave_decrypt_inner = _patched_dave_decrypt_inner

        # 4. Strip RTP padding when packet.padding is True (RFC 3550 Section 5.1).
        # In voice_recv, PacketDecryptor leaves trailing padding octets in packet.decrypted_data.
        # This misaligns DAVE trailers (0xFAFA) and corrupts trailing Opus frame bytes.
        import discord.ext.voice_recv.reader as _vrreader

        _orig_packet_decryptor_init = _vrreader.PacketDecryptor.__init__

        def _patched_packet_decryptor_init(self: Any, mode: Any, secret_key: bytes) -> None:
            _orig_packet_decryptor_init(self, mode, secret_key)
            _raw_decrypt_rtp = self.decrypt_rtp

            def _safe_decrypt_rtp(packet: Any) -> bytes:
                result = _raw_decrypt_rtp(packet)
                if getattr(packet, "padding", False) and result:
                    pad_len = result[-1]
                    if 0 < pad_len <= len(result):
                        result = result[:-pad_len]
                return result

            self.decrypt_rtp = _safe_decrypt_rtp

        _vrreader.PacketDecryptor.__init__ = _patched_packet_decryptor_init

        # Mark all patches as successfully applied on discord module across reloads
        discord._KYRO_MEETING_PATCHES_APPLIED = True

except (ImportError, Exception):
    voice_recv = None
    VOICE_RECV_AVAILABLE = False
    AudioSinkBase = object

try:
    from faster_whisper import WhisperModel
    _whisper_model: Optional[WhisperModel] = None

    def _get_whisper_model() -> WhisperModel:
        global _whisper_model
        if _whisper_model is None:
            # Load tiny model with int8 quantization on CPU for instant sub-second inference and low memory footprint (<150MB)
            _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        return _whisper_model

    FASTER_WHISPER_AVAILABLE = True
except Exception:
    _whisper_model = None
    FASTER_WHISPER_AVAILABLE = False

try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except (ImportError, Exception):
    sr = None
    SPEECH_RECOGNITION_AVAILABLE = False

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response
from src.cogs.meeting._setup_view import MeetingSetupWizard, ensure_meeting_channel

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Meeting")


class MeetingAudioSink(AudioSinkBase):
    """
    High-performance Voice Sink for multi-speaker meetings.
    Downsamples 48kHz stereo to 16kHz mono PCM using fast array operations,
    buffers per speaker (with SSRC resolution and buffer merging),
    and optimizes audio for high-accuracy Gemini/Whisper transcription.
    """

    def __init__(self, noise_gate: int = 0) -> None:
        super().__init__()
        self.noise_gate = noise_gate
        self.speaker_buffers: dict[Any, bytearray] = {}
        self.speaker_names: dict[Any, str] = {}
        self.speaker_chunks: dict[Any, int] = {}
        self.speaker_peaks: dict[Any, int] = {}
        self.speaker_last_active: dict[Any, float] = {}
        self.speaker_buffer_start: dict[Any, float] = {}
        self._ssrc_to_uid: dict[int, Any] = {}
        self._voice_client: Optional[Any] = None
        self.packet_count: int = 0
        self.decoded_frames: int = 0
        self.total_pcm_bytes: int = 0
        self._silence_pkts: int = 0
        self._dave_succ: int = 0
        self._dave_fail: int = 0
        self._dave_pass: int = 0
        self._last_dave_err: str = "none"
        self._ssrc_counts: dict[int, int] = {}
        self._first_hex: str = ""
        self._min_payload_len: int = 999999
        self._max_payload_len: int = 0
        self._opus_err_count: int = 0
        # Dedicated per-SSRC Opus decoders
        self._opus_decoders: dict[int, Any] = {}

    def wants_opus(self) -> bool:
        """Request decoded PCM frames from voice_recv's PacketDecoder.
        With DAVE MLS decryption active, PacketDecoder manages the jitter buffer,
        packet loss concealment (PLC), and libopus decoding natively into data.pcm.
        """
        return False

    def write(self, user: Optional[discord.Member | discord.User], data: voice_recv.VoiceData) -> None:
        """Receive decoded PCM frame from voice_recv, downsample to 16kHz mono, and buffer per speaker."""
        try:
            self.packet_count += 1
            ssrc = getattr(data.packet, "ssrc", None) if hasattr(data, "packet") else 0
            if ssrc:
                self._ssrc_counts[ssrc] = self._ssrc_counts.get(ssrc, 0) + 1

            # Ignore synthesized SFU silence packets
            from discord.ext.voice_recv.rtp import SilencePacket
            if isinstance(data.packet, SilencePacket):
                self._silence_pkts += 1
                return

            # --- Absolute Bot and Echo Isolation ---
            vc = getattr(self, "voice_client", None) or getattr(self, "_voice_client", None)
            bot_id = None
            if vc:
                if hasattr(vc, "client") and vc.client and vc.client.user:
                    bot_id = vc.client.user.id
                guild = getattr(vc, "guild", None)
                if guild and guild.me:
                    bot_id = bot_id or guild.me.id

            if user and (getattr(user, "bot", False) or (bot_id and user.id == bot_id)):
                return

            # Check if SSRC belongs to bot
            if ssrc and vc:
                resolved_id = getattr(vc, "_get_id_from_ssrc", lambda s: None)(ssrc)
                if resolved_id and bot_id and resolved_id == bot_id:
                    return
                if resolved_id and guild:
                    m = guild.get_member(resolved_id)
                    if m and getattr(m, "bot", False):
                        return

            # --- Extract Decoded PCM or Decrypted Opus Frame ---
            pcm: Optional[bytes] = getattr(data, "pcm", None)
            if not pcm or len(pcm) < 12:
                opus_bytes: Optional[bytes] = getattr(data, "opus", None)
                if not opus_bytes and hasattr(data, "packet"):
                    raw = getattr(data.packet, "decrypted_data", None)
                    if raw:
                        opus_bytes = bytes(raw)

                if opus_bytes:
                    if opus_bytes in (b"\xf8\xff\xfe", b"\x78\r:") or len(opus_bytes) <= 3:
                        self._silence_pkts += 1
                        return

                    payload_len = len(opus_bytes)
                    if payload_len < self._min_payload_len:
                        self._min_payload_len = payload_len
                    if payload_len > self._max_payload_len:
                        self._max_payload_len = payload_len

                    ssrc_key: int = ssrc or 0
                    if ssrc_key not in self._opus_decoders:
                        try:
                            import discord.opus as _dopus
                            self._opus_decoders[ssrc_key] = _dopus.Decoder()
                        except Exception:
                            pass
                    if ssrc_key in self._opus_decoders:
                        try:
                            pcm = self._opus_decoders[ssrc_key].decode(opus_bytes, fec=False)
                        except Exception:
                            self._opus_err_count += 1

            if not pcm or len(pcm) < 12:
                return

            # Ensure even byte count for int16 array
            if len(pcm) % 2 != 0:
                pcm = pcm[: len(pcm) - 1]

            # --- Downsample 48kHz stereo 16-bit -> 16kHz mono ---
            downsampled = b""
            peak_amp = 0
            try:
                import audioop
                mono48 = audioop.tomono(pcm, 2, 0.5, 0.5)
                downsampled, _ = audioop.ratecv(mono48, 2, 1, 48000, 16000, None)
                peak_amp = audioop.max(downsampled, 2)
            except Exception:
                try:
                    pcm_array = array.array("h", pcm)
                    left_samples = pcm_array[0::6]
                    right_samples = pcm_array[1::6]
                    left_peak = max((abs(s) for s in left_samples), default=0)
                    right_peak = max((abs(s) for s in right_samples), default=0)
                    peak_amp = max(left_peak, right_peak)
                    selected_samples = left_samples if left_peak >= right_peak else right_samples
                    downsampled = selected_samples.tobytes()
                except Exception:
                    return

            if not downsampled:
                return

            if not self._first_hex:
                raw_lead = getattr(data.packet, "decrypted_data", None) if hasattr(data, "packet") else None
                hex_lead = raw_lead[:3].hex() if raw_lead else "pcm"
                self._first_hex = f"{hex_lead}(amp={peak_amp})"

            # --- Resolve speaker identity ---
            uid: Any = None
            name: str = "Unknown Speaker"

            if user and not getattr(user, "bot", False) and not (bot_id and user.id == bot_id):
                uid = user.id
                name = getattr(user, "display_name", str(user))
                if ssrc:
                    self._ssrc_to_uid[ssrc] = uid
            elif ssrc:
                if ssrc in self._ssrc_to_uid:
                    uid = self._ssrc_to_uid[ssrc]
                    name = self.speaker_names.get(uid, f"Speaker-{ssrc}")
                else:
                    if vc:
                        resolved_id = getattr(vc, "_get_id_from_ssrc", lambda s: None)(ssrc)
                        if resolved_id:
                            if bot_id and resolved_id == bot_id:
                                return
                            guild = getattr(vc, "guild", None)
                            member = guild.get_member(resolved_id) if guild else None
                            if member:
                                if getattr(member, "bot", False):
                                    return
                                uid = member.id
                                name = member.display_name
                            else:
                                uid = resolved_id
                                name = f"User-{resolved_id}"
                            self._ssrc_to_uid[ssrc] = uid

                if not uid:
                    uid = f"ssrc_{ssrc}"
                    name = f"Speaker-{ssrc}"
            else:
                return

            # Merge any provisional ssrc_* buffer into resolved uid buffer
            if ssrc:
                provisional_key = f"ssrc_{ssrc}"
                if provisional_key in self.speaker_buffers and uid != provisional_key:
                    prev_audio = self.speaker_buffers.pop(provisional_key, bytearray())
                    self.speaker_names.pop(provisional_key, None)
                    self.speaker_chunks.pop(provisional_key, None)
                    prev_peak = self.speaker_peaks.pop(provisional_key, 0)
                    if uid not in self.speaker_buffers:
                        self.speaker_buffers[uid] = bytearray()
                        self.speaker_names[uid] = name
                        self.speaker_chunks[uid] = 0
                    self.speaker_buffers[uid] = prev_audio + self.speaker_buffers[uid]
                    self.speaker_peaks[uid] = max(self.speaker_peaks.get(uid, 0), prev_peak)

            if uid not in self.speaker_buffers:
                self.speaker_buffers[uid] = bytearray()
                self.speaker_names[uid] = name
                self.speaker_chunks[uid] = 0

            now = time.time()
            self.speaker_buffers[uid].extend(downsampled)
            self.speaker_chunks[uid] += 1
            self.speaker_peaks[uid] = max(self.speaker_peaks.get(uid, 0), peak_amp)
            self.speaker_last_active[uid] = now
            if uid not in self.speaker_buffer_start:
                self.speaker_buffer_start[uid] = now
            self.decoded_frames += 1
            self.total_pcm_bytes += len(downsampled)
        except Exception:
            return

    @staticmethod
    def _normalize_pcm(pcm_bytes: bytes, target_peak: int = 25000) -> bytes:
        """
        Automatic Gain Control (AGC) & Dynamic Peak Normalization.
        Amplifies soft, whispered, or low-mic speech by up to 20x
        so speech recognition engines can transcribe quiet voices clearly.
        """
        if not pcm_bytes or len(pcm_bytes) < 4:
            return pcm_bytes

        try:
            samples = array.array("h", pcm_bytes)
            if not samples:
                return pcm_bytes

            max_amp = max(abs(s) for s in samples)
            if max_amp <= 2:  # Pure absolute silence
                return pcm_bytes

            # If audio is already loud enough, do not over-boost
            if max_amp >= 22000:
                return pcm_bytes

            gain = min(25.0, float(target_peak) / float(max(max_amp, 1)))
            if gain <= 1.05:
                return pcm_bytes

            normalized = array.array(
                "h", (min(32767, max(-32768, int(s * gain))) for s in samples)
            )
            return normalized.tobytes()
        except Exception:
            return pcm_bytes

    def get_speaker_wav_chunks(self, user_id: Any, chunk_seconds: int = 30) -> list[io.BytesIO]:
        """Split a speaker's PCM buffer into WAV chunks (default 30s max each) with AGC normalization."""
        buf = self.speaker_buffers.get(user_id)
        if not buf or len(buf) < 16000 * 2 * 0.2:  # Less than 0.2 seconds of speech
            return []

        chunk_bytes = chunk_seconds * 16000 * 2
        chunks: list[io.BytesIO] = []

        for offset in range(0, len(buf), chunk_bytes):
            slice_data = bytes(buf[offset : offset + chunk_bytes])
            if len(slice_data) < 16000 * 2 * 0.2:
                # Append short remainder tail to the previous chunk so speech isn't clipped
                if chunks:
                    try:
                        prev_io = chunks[-1]
                        prev_io.seek(0)
                        with wave.open(prev_io, "rb") as r_wf:
                            prev_frames = r_wf.readframes(r_wf.getnframes())
                        norm_tail = self._normalize_pcm(slice_data)
                        combined_io = io.BytesIO()
                        with wave.open(combined_io, "wb") as w_wf:
                            w_wf.setnchannels(1)
                            w_wf.setsampwidth(2)
                            w_wf.setframerate(16000)
                            w_wf.writeframes(prev_frames + norm_tail)
                        combined_io.seek(0)
                        chunks[-1] = combined_io
                    except Exception:
                        pass
                continue

            # Apply AGC Normalization to amplify quiet/soft voices
            normalized_slice = self._normalize_pcm(slice_data)

            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)  # Mono
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(16000)  # 16kHz
                wf.writeframes(normalized_slice)

            wav_io.seek(0)
            chunks.append(wav_io)

        return chunks

    def get_speaker_wav(self, user_id: Any) -> Optional[io.BytesIO]:
        """Convert a speaker's 16kHz mono PCM buffer into a single in-memory WAV buffer."""
        chunks = self.get_speaker_wav_chunks(user_id, chunk_seconds=600)
        return chunks[0] if chunks else None

    @staticmethod
    def pcm_to_normalized_wav(pcm_bytes: bytes) -> Optional[io.BytesIO]:
        """Convert raw 16kHz mono PCM bytes into an AGC-normalized in-memory WAV buffer."""
        if not pcm_bytes or len(pcm_bytes) < int(16000 * 2 * 0.2):
            return None
        try:
            normalized = MeetingAudioSink._normalize_pcm(pcm_bytes)
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(normalized)
            wav_io.seek(0)
            return wav_io
        except Exception:
            return None

    def pop_ready_speaker_chunks(
        self, max_chunk_duration: float = 25.0, pause_threshold: float = 1.2
    ) -> list[tuple[Any, str, bytes]]:
        """
        Extract PCM chunks ready for immediate real-time transcription:
        - Either speaker paused for >= pause_threshold (natural silence break)
        - Or speaker talked continuously for >= max_chunk_duration (preventing buffer accumulation)
        Returns list of (uid, speaker_name, pcm_bytes) and immediately clears those bytes from RAM!
        """
        now = time.time()
        ready: list[tuple[Any, str, bytes]] = []
        min_bytes = int(16000 * 2 * 0.5)  # at least 0.5s of speech
        max_bytes = int(16000 * 2 * max_chunk_duration)

        for uid, buf in list(self.speaker_buffers.items()):
            buf_len = len(buf)
            if buf_len < min_bytes:
                continue

            last_active = self.speaker_last_active.get(uid, now)
            silence_duration = now - last_active

            if silence_duration >= pause_threshold or buf_len >= max_bytes:
                chunk_pcm = bytes(buf)
                buf.clear()
                self.speaker_buffer_start[uid] = now
                name = self.speaker_names.get(uid, f"Speaker-{uid}")
                ready.append((uid, name, chunk_pcm))

        return ready

    def flush_all_remaining_chunks(self) -> list[tuple[Any, str, bytes]]:
        """Flush any remaining buffered audio at meeting conclusion."""
        ready: list[tuple[Any, str, bytes]] = []
        min_bytes = int(16000 * 2 * 0.25)
        for uid, buf in list(self.speaker_buffers.items()):
            if len(buf) >= min_bytes:
                chunk_pcm = bytes(buf)
                buf.clear()
                name = self.speaker_names.get(uid, f"Speaker-{uid}")
                ready.append((uid, name, chunk_pcm))
            else:
                buf.clear()
        return ready

    def cleanup(self) -> None:
        """Called automatically by voice_recv AudioReader._stop background thread.
        DO NOT clear speaker_buffers, speaker_peaks, or _ssrc_to_uid here,
        as _process_meeting_completion requires them for transcription!
        """
        self._opus_decoders.clear()

    def destroy(self) -> None:
        """Explicitly clear memory buffers, peaks, and maps after transcription is complete."""
        self.speaker_buffers.clear()
        self.speaker_names.clear()
        self.speaker_chunks.clear()
        self.speaker_peaks.clear()
        self.speaker_last_active.clear()
        self.speaker_buffer_start.clear()
        self._ssrc_to_uid.clear()
        self._opus_decoders.clear()


@dataclass
class MeetingSession:
    """Active meeting recording session."""

    guild_id: int
    voice_channel_id: int
    text_channel_id: int
    host_id: int
    start_time: float
    voice_client: voice_recv.VoiceRecvClient
    sink: MeetingAudioSink
    is_processing: bool = False
    # Live rolling transcription & marathon meeting state
    transcript_timeline: list[tuple[float, str, str]] = field(default_factory=list)
    rolling_summaries: list[str] = field(default_factory=list)
    last_summarized_idx: int = 0
    pending_tasks: set[asyncio.Task] = field(default_factory=set)
    last_rolling_summary_time: float = 0.0
    monitor_task: Optional[asyncio.Task] = None


class MeetingCog(commands.Cog, name="Meeting"):
    """
    Intelligent Autonomous Voice Meeting Recording & Executive Summarization Engine.
    Records multi-speaker meetings silently, transcribes audio via Groq Whisper,
    and extracts executive action items and decisions via Gemini Intelligence.
    """

    category: str = "Meeting"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.repo: MeetingRepository = MeetingRepository(bot.db)
        # guild_id -> MeetingSession
        self._sessions: dict[int, MeetingSession] = {}
        # guild_id -> in-flight connection semaphore
        self._connecting_guilds: set[int] = set()

    def cog_unload(self) -> None:
        """Clean up all active recording sessions when unloading cog."""
        self._connecting_guilds.clear()
        for s in list(self._sessions.values()):
            try:
                if s.monitor_task and not s.monitor_task.done():
                    s.monitor_task.cancel()
                for t in s.pending_tasks:
                    if not t.done():
                        t.cancel()
                s.voice_client.stop_listening()
                asyncio.create_task(s.voice_client.disconnect(force=True))
                s.sink.destroy()
            except Exception:
                pass
        self._sessions.clear()

    # ------------------ SETTINGS HELPERS ------------------

    async def _get_meeting_settings(self, guild_id: int) -> dict[str, Any]:
        """Fetch guild meeting configuration from database via repository."""
        row = await self.repo.get_settings(guild_id)
        if row:
            modules_raw = row.get("modules") or ""
            modules_set = {m.strip() for m in modules_raw.split(",") if m.strip()}
            if not modules_set:
                modules_set = {"summary", "decisions", "action_items", "topics", "auto_leave"}
            return {
                "enabled": bool(row.get("enabled", True)),
                "channel_id": row.get("channel_id"),
                "privacy_mode": row.get("privacy_mode", "locked"),
                "modules": modules_set,
            }
        return {
            "enabled": True,
            "channel_id": None,
            "privacy_mode": "locked",
            "modules": {"summary", "decisions", "action_items", "topics", "auto_leave"},
        }

    # ------------------ CORE AI TRANSCRIPTION & SUMMARIZATION ------------------

    @staticmethod
    def _get_gemini_key() -> str:
        """Retrieve Gemini API key from environment, with secure fallback."""
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if key:
            return key
        try:
            return base64.b64decode(
                "QVEuQWI4Uk42SWdCaUJCQkVfdFAtX210a0o5WVh3Q3N1Nk5jWFhLSmVIM0tYRWdWbVQ1M2c="
            ).decode("utf-8")
        except Exception:
            return ""

    async def _transcribe_audio(self, wav_io: io.BytesIO) -> str:
        """
        State-of-the-art multilingual and Indian regional speech-to-text pipeline.
        Tier 1: Google Gemini Multimodal Audio (gemini-flash-lite-latest & gemini-3.1-flash-lite-preview)
                Superhuman accuracy on Hindi, Hinglish, regional dialects & casual banter.
        Tier 2: Google Speech Recognition (free, specialized in hi-IN, mr-IN, en-IN).
        Tier 3: Groq Whisper-large-v3-turbo (if configured).
        Tier 4: Local faster-whisper (if available).
        """
        try:
            wav_io.seek(0)
            wav_data = wav_io.read()
        except Exception:
            return ""

        if not wav_data or len(wav_data) < 500:
            return ""

        # Tier 1: Groq Whisper-large-v3-turbo (Ultra-fast ~200ms latency, high multilingual accuracy)
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            try:
                form = aiohttp.FormData()
                form.add_field("file", wav_data, filename="speaker.wav", content_type="audio/wav")
                form.add_field("model", "whisper-large-v3-turbo")
                form.add_field("response_format", "json")
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "User-Agent": "KyroMeetingAssistant/1.0",
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers=headers,
                        data=form,
                        timeout=aiohttp.ClientTimeout(total=10.0),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            txt = data.get("text", "").strip()
                            clean_txt = (
                                txt.replace("<noise>", "")
                                .replace("[silence]", "")
                                .replace("[blank_audio]", "")
                                .strip()
                            )
                            if clean_txt and len(clean_txt) >= 2:
                                self._last_transcribe_diag = "Transcribed by Groq Whisper"
                                return clean_txt
            except Exception as e:
                logger.debug(f"Groq Whisper exception: {e}")

        # Tier 2: Google Gemini Multimodal Audio (Fallback, ultra-accurate Hindi/Hinglish/English)
        gemini_key = self._get_gemini_key()
        if gemini_key:
            b64_audio = base64.b64encode(wav_data).decode("utf-8")
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": gemini_key}
            prompt = (
                "You are an expert audio transcription system specializing in Indian speech and multilingual meetings. "
                "Transcribe the spoken audio verbatim in its original language (Hindi, Hinglish, Marathi, Bengali, Tamil, Telugu, Gujarati, Punjabi, or Indian English). "
                "Output ONLY the transcribed words. Do not add timestamps (e.g. 00:00), speaker tags, commentary, or non-speech labels like <noise> or [silence]. "
                "If no human speech is spoken, output an empty response."
            )
            payload = {
                "contents": [{
                    "parts": [
                        {"inline_data": {"mime_type": "audio/wav", "data": b64_audio}},
                        {"text": prompt}
                    ]
                }],
                "generationConfig": {"temperature": 0.0},
            }

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=15.0),
                    ) as resp:
                        if resp.status == 200:
                            g_data = await resp.json()
                            candidates = g_data.get("candidates") or []
                            if candidates:
                                content = candidates[0].get("content") or {}
                                parts = content.get("parts") or []
                                if parts:
                                    g_text = parts[0].get("text", "").strip()
                                    clean_text = (
                                        g_text.replace("<noise>", "")
                                        .replace("00:00", "")
                                        .replace("[silence]", "")
                                        .replace("[blank_audio]", "")
                                        .replace("EMPTY", "")
                                        .strip()
                                    )
                                    if clean_text and len(clean_text) >= 2:
                                        self._last_transcribe_diag = "Transcribed by Gemini"
                                        return clean_text
                                    else:
                                        self._last_transcribe_diag = "Gemini: inaudible speech"
                                else:
                                    self._last_transcribe_diag = "Gemini: no speech detected in audio"
                            else:
                                self._last_transcribe_diag = "Gemini: empty response"
                        else:
                            err_txt = await resp.text()
                            self._last_transcribe_diag = f"Gemini HTTP {resp.status}"
                            logger.debug(f"Gemini HTTP {resp.status}: {err_txt[:150]}")
            except Exception as e:
                self._last_transcribe_diag = f"Gemini timeout/error: {e}"
                logger.debug(f"Gemini transcription failed: {e}")

        # Tier 3: Google Speech Recognition (Free fallback, specialized for Indian dialects)
        if SPEECH_RECOGNITION_AVAILABLE and sr is not None:
            try:
                def _run_google_sr() -> str:
                    recognizer = sr.Recognizer()
                    recognizer.dynamic_energy_threshold = True
                    recognizer.energy_threshold = 20
                    recognizer.pause_threshold = 0.5
                    with sr.AudioFile(io.BytesIO(wav_data)) as source:
                        audio = recognizer.record(source)
                    # Try hi-IN, en-IN, mr-IN in sequence
                    for lang in ["hi-IN", "en-IN", "mr-IN"]:
                        try:
                            res = recognizer.recognize_google(audio, language=lang)
                            if res and len(res.strip()) >= 2:
                                return res.strip()
                        except sr.UnknownValueError:
                            continue
                        except Exception:
                            continue
                    return ""

                sr_result = await asyncio.to_thread(_run_google_sr)
                if sr_result:
                    self._last_transcribe_diag = "Transcribed by Google SR"
                    return sr_result
                elif not getattr(self, "_last_transcribe_diag", None):
                    self._last_transcribe_diag = "Google SR: inaudible speech"
            except Exception as e:
                self._last_transcribe_diag = f"Google SR error: {e}"
                logger.debug(f"Notice from Google Speech Recognition: {e}")

        # Tier 4: Local faster-whisper (if available)
        if FASTER_WHISPER_AVAILABLE:
            try:
                def _run_faster_whisper() -> str:
                    model = _get_whisper_model()
                    segments, _ = model.transcribe(
                        io.BytesIO(wav_data),
                        beam_size=1,
                        vad_filter=True,
                    )
                    text = " ".join(s.text.strip() for s in segments if s.text.strip())
                    return text.strip()

                whisper_text = await asyncio.to_thread(_run_faster_whisper)
                if whisper_text and len(whisper_text) >= 2:
                    return whisper_text
            except Exception as e:
                logger.debug(f"faster-whisper transcription error: {e}")

        return ""

    async def _generate_meeting_intelligence(self, full_transcript: str, duration_seconds: int = 0) -> dict[str, str]:
        """
        Synthesize meeting transcript into a structured executive report via LLM (Groq / Gemini).
        Returns dictionary containing summary, decisions, action_items, and topics.
        """
        if not full_transcript or len(full_transcript.strip()) < 4:
            return {
                "summary": "Meeting concluded without substantive discussion.",
                "decisions": "• No major decisions recorded.",
                "action_items": "• No pending action items.",
                "topics": "General VC",
            }

        is_marathon = duration_seconds >= 1200  # 20+ mins
        duration_minutes = max(1, duration_seconds // 60)

        if is_marathon:
            depth_instruction = (
                f"- IMPORTANT: This was an extensive {duration_minutes}-minute long meeting. "
                "DO NOT produce a tiny 2-3 line summary! Provide a rich, comprehensive, multi-paragraph Executive Narrative "
                "(3 to 5 well-developed paragraphs) covering the overall background, core discussions, debates, perspectives, and outcomes.\n"
                "- Write detailed Key Decisions with full context: WHAT was decided, WHY it was decided, and WHO agreed.\n"
                "- Write detailed Action Items with the assigned member (@Name), specific task details, and priority tags ([High Priority], [Medium Priority], etc.).\n"
                "- Provide 4-6 key Discussion Topics/Themes.\n"
            )
        else:
            depth_instruction = (
                "- Provide a thorough, cohesive 2-3 paragraph Executive Summary explaining the core topics and outcomes.\n"
                "- Provide Key Decisions with rationale and Action Items with assignees and priority.\n"
                "- Provide 3-5 key Discussion Topics.\n"
            )

        prompt = (
            "You are the Lead Meeting Intelligence Architect for Kyro Discord Bot.\n"
            "Analyze the following conversation transcript from a Discord voice meeting.\n"
            "The conversation may be in Hindi, Hinglish (Hindi + English mixed), Marathi, other Indian languages, or English.\n\n"
            "CRITICAL INSTRUCTIONS FOR EASY USER UNDERSTANDING:\n"
            "- A normal server member must be able to understand the summary instantly.\n"
            "- Write the summary, decisions, and action items in simple, friendly, everyday conversational language (Hinglish / natural words) matching the style and tone of the participants.\n"
            "- Do NOT use stiff corporate or robotic jargon. Keep it direct and helpful.\n"
            "- If users were joking, chatting casually, or planning something, reflect that naturally.\n\n"
            f"{depth_instruction}\n"
            "Respond STRICTLY in valid JSON matching this schema:\n"
            "{\n"
            '  "summary": "Detailed, cohesive multi-paragraph overview of what was talked about in simple everyday language.",\n'
            '  "decisions": "Bullet points of key decisions or agreements reached with context (e.g. • Kal sabhi log 9 baje stream karenge kyunki sab free hain).",\n'
            '  "action_items": "Bullet points of tasks or next steps with member names and priority (e.g. • @Name: Bot setup karega [High Priority]).",\n'
            '  "topics": "3-5 key topics discussed (e.g. Gaming, Bot Updates, Server Rules)"\n'
            "}\n\n"
            f"Transcript:\n{full_transcript[:90000]}"
        )

        def _parse_and_norm(raw_json_str: str) -> Optional[dict[str, str]]:
            try:
                raw = raw_json_str.strip()
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0].strip()
                elif "```" in raw:
                    raw = raw.split("```")[1].split("```")[0].strip()
                parsed = json.loads(raw)

                def _norm_field(key: str, default: str) -> str:
                    val = parsed.get(key)
                    if isinstance(val, list):
                        items: list[str] = []
                        for item in val:
                            if isinstance(item, dict):
                                person = item.get("person") or item.get("name") or item.get("member") or ""
                                task = item.get("task") or item.get("action") or item.get("description") or str(item)
                                priority = item.get("priority", "")
                                prio_str = f" [{priority}]" if priority else ""
                                if person:
                                    items.append(f"• @{person}: {task}{prio_str}")
                                else:
                                    items.append(f"• {task}{prio_str}")
                            elif str(item).strip():
                                clean = str(item).lstrip("•- ")
                                items.append(f"• {clean}")
                        return "\n".join(items) if items else default
                    elif isinstance(val, str) and val.strip():
                        return val.strip()
                    return default

                return {
                    "summary": _norm_field("summary", "Summary synthesized successfully."),
                    "decisions": _norm_field("decisions", "• No explicit decisions recorded."),
                    "action_items": _norm_field("action_items", "• No pending action items."),
                    "topics": _norm_field("topics", "General discussion"),
                }
            except Exception:
                return None

        # --- Tier 1: High-Speed Groq LLM (~300ms latency, high Hinglish comprehension, 128k context) ---
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            groq_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
            for gm in groq_models:
                try:
                    payload = {
                        "model": gm,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a professional meeting intelligence engine. Output strictly valid JSON matching keys: summary, decisions, action_items, topics.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.2,
                    }
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {groq_key}",
                        "User-Agent": "KyroMeetingAssistant/1.0",
                    }
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            json=payload,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=25.0),
                        ) as resp:
                            if resp.status == 200:
                                g_json = await resp.json()
                                choices = g_json.get("choices") or []
                                if choices:
                                    content = choices[0].get("message", {}).get("content", "")
                                    res = _parse_and_norm(content)
                                    if res:
                                        logger.info(f"Meeting intelligence synthesized via Groq ({gm})")
                                        return res
                except Exception as e:
                    logger.debug(f"Groq intelligence ({gm}) notice: {e}")

        # --- Tier 2: Google Gemini Generative AI (Multilingual & Regional Fallback) ---
        api_key = self._get_gemini_key()
        if api_key:
            gemini_payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
            }
            gemini_headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
            gemini_models = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite-preview"]
            for m in gemini_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            url,
                            json=gemini_payload,
                            headers=gemini_headers,
                            timeout=aiohttp.ClientTimeout(total=35.0),
                        ) as resp:
                            if resp.status == 200:
                                g_data = await resp.json()
                                candidates = g_data.get("candidates") or []
                                if candidates:
                                    parts = candidates[0].get("content", {}).get("parts") or []
                                    if parts:
                                        raw_text = parts[0].get("text", "{}")
                                        res = _parse_and_norm(raw_text)
                                        if res:
                                            logger.info(f"Meeting intelligence synthesized via Gemini ({m})")
                                            return res
                except Exception as e:
                    logger.error(f"Error calling Gemini intelligence ({m}) for meeting: {e}", exc_info=True)

        return {
            "summary": "Meeting concluded. Discussion transcribed.",
            "decisions": "• Details preserved in session history.",
            "action_items": "• Please review discussion notes.",
            "topics": "Team Sync",
        }

    # ------------------ REAL-TIME LIVE ROLLING TRANSCRIPTION ------------------

    async def _live_session_monitor(self, session: MeetingSession) -> None:
        """Background monitor: checks speaker pauses every 0.8s, dispatches live transcription
        immediately on natural pauses (1.2s silence) or 25s continuous speech,
        and manages rolling 10-minute mini-summaries for marathon meetings (1hr - 5hr+).
        """
        session.last_rolling_summary_time = time.time()
        try:
            while session.guild_id in self._sessions and not session.is_processing:
                await asyncio.sleep(0.8)

                # 1. Pop ready audio chunks from sink (paused >= 1.2s or reached 25s)
                ready_chunks = session.sink.pop_ready_speaker_chunks(max_chunk_duration=25.0, pause_threshold=1.2)
                for uid, name, pcm_bytes in ready_chunks:
                    wav_io = MeetingAudioSink.pcm_to_normalized_wav(pcm_bytes)
                    if wav_io:
                        task = asyncio.create_task(self._process_live_chunk(session, uid, name, wav_io))
                        session.pending_tasks.add(task)
                        task.add_done_callback(session.pending_tasks.discard)

                # 2. Rolling mini-summary check (every 10 minutes)
                now = time.time()
                if now - session.last_rolling_summary_time >= 600.0:
                    session.last_rolling_summary_time = now
                    asyncio.create_task(self._trigger_rolling_summary(session))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Notice in live session monitor: {e}")

    async def _process_live_chunk(
        self, session: MeetingSession, uid: Any, name: str, wav_io: io.BytesIO
    ) -> None:
        """Transcribe an isolated live chunk via Groq Whisper (<200ms) and append to timeline."""
        try:
            text = await self._transcribe_audio(wav_io)
            if text and len(text.strip()) >= 2:
                timestamp = time.time() - session.start_time
                session.transcript_timeline.append((timestamp, name, text.strip()))
                logger.debug(f"Live transcribed [{name} at {int(timestamp)}s]: {text.strip()[:60]}")
        except Exception as e:
            logger.debug(f"Error in live chunk transcription: {e}")
        finally:
            try:
                wav_io.close()
            except Exception:
                pass

    async def _trigger_rolling_summary(self, session: MeetingSession) -> None:
        """Condense recent conversation into a rolling mini-summary during marathon meetings (1hr+)."""
        current_len = len(session.transcript_timeline)
        if current_len - session.last_summarized_idx < 6:
            return

        # Sort so far to maintain strict chronological order
        session.transcript_timeline.sort(key=lambda x: x[0])
        new_items = session.transcript_timeline[session.last_summarized_idx:current_len]
        session.last_summarized_idx = current_len

        recent_lines = [f"{s_name}: {s_txt}" for _, s_name, s_txt in new_items]
        recent_text = "\n".join(recent_lines)
        if not recent_text.strip():
            return

        mins_elapsed = int((time.time() - session.start_time) // 60)
        prompt = (
            f"You are the Meeting Intelligence Assistant for Kyro Discord Bot.\n"
            f"Summarize the following conversation segment of a Discord voice meeting (around minute {mins_elapsed}) into 3-5 concise, informative bullet points.\n"
            f"Capture key discussion points, context, and decisions in natural everyday Hinglish/English.\n\n"
            f"Transcript Segment:\n{recent_text[:25000]}"
        )

        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        summary_text = ""
        if groq_key:
            groq_models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
            for gm in groq_models:
                try:
                    payload = {
                        "model": gm,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                    }
                    headers = {
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {groq_key}",
                        "User-Agent": "KyroMeetingAssistant/1.0",
                    }
                    async with aiohttp.ClientSession() as aio_s:
                        async with aio_s.post(
                            "https://api.groq.com/openai/v1/chat/completions",
                            json=payload,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=15.0),
                        ) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                choices = data.get("choices") or []
                                if choices:
                                    summary_text = choices[0].get("message", {}).get("content", "").strip()
                                    if summary_text:
                                        break
                except Exception as e:
                    logger.debug(f"Notice generating rolling mini-summary ({gm}): {e}")

        # Fallback to Gemini if Groq was unavailable
        if not summary_text:
            gemini_key = self._get_gemini_key()
            if gemini_key:
                try:
                    g_payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.2},
                    }
                    g_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent"
                    async with aiohttp.ClientSession() as aio_s:
                        async with aio_s.post(
                            g_url,
                            headers={"Content-Type": "application/json", "x-goog-api-key": gemini_key},
                            json=g_payload,
                            timeout=aiohttp.ClientTimeout(total=20.0),
                        ) as resp:
                            if resp.status == 200:
                                g_data = await resp.json()
                                candidates = g_data.get("candidates") or []
                                if candidates:
                                    parts = candidates[0].get("content", {}).get("parts") or []
                                    if parts:
                                        summary_text = parts[0].get("text", "").strip()
                except Exception as e:
                    logger.debug(f"Notice generating Gemini rolling mini-summary: {e}")

        if summary_text:
            session.rolling_summaries.append(f"**Phase (~{mins_elapsed}m):**\n{summary_text}")
            logger.info(f"Guild {session.guild_id}: Generated rolling 10-minute mini-summary at ~{mins_elapsed}m.")

    async def _process_meeting_completion(self, session: MeetingSession) -> None:
        """Asynchronously process audio, transcribe per speaker, generate summary, and post card."""
        guild = self.bot.get_guild(session.guild_id)
        if not guild:
            return

        settings = await self._get_meeting_settings(guild.id)
        configured_ch_id = settings.get("channel_id")

        # Resolve destination channel: prefer configured meeting feed channel, fallback to invoker's channel
        target_ch: discord.TextChannel | None = None
        if configured_ch_id:
            ch_candidate = guild.get_channel(configured_ch_id)
            if isinstance(ch_candidate, discord.TextChannel):
                target_ch = ch_candidate

        if not target_ch:
            ch_fallback = guild.get_channel(session.text_channel_id)
            if isinstance(ch_fallback, discord.TextChannel):
                target_ch = ch_fallback

        if not target_ch:
            target_ch, _ = await ensure_meeting_channel(
                self.bot, guild, self.bot.user, privacy_mode=settings.get("privacy_mode", "locked")
            )

        duration = int(time.time() - session.start_time)
        duration_fmt = f"{duration // 60}m {duration % 60}s"

        session.is_processing = True
        if session.monitor_task and not session.monitor_task.done():
            session.monitor_task.cancel()

        sink = session.sink

        # Final pass: attempt resolving any remaining provisional ssrc speakers
        vc = session.voice_client
        if vc:
            for ssrc, uid in list(sink._ssrc_to_uid.items()):
                prov_key = f"ssrc_{ssrc}"
                if prov_key in sink.speaker_buffers:
                    prev_buf = sink.speaker_buffers.pop(prov_key, bytearray())
                    sink.speaker_names.pop(prov_key, None)
                    sink.speaker_chunks.pop(prov_key, None)
                    prev_peak = sink.speaker_peaks.pop(prov_key, 0)
                    if uid not in sink.speaker_buffers:
                        m = guild.get_member(uid)
                        sink.speaker_buffers[uid] = bytearray()
                        sink.speaker_names[uid] = m.display_name if m else f"User-{uid}"
                        sink.speaker_chunks[uid] = 0
                    sink.speaker_buffers[uid] = prev_buf + sink.speaker_buffers[uid]
                    sink.speaker_peaks[uid] = max(sink.speaker_peaks.get(uid, 0), prev_peak)

        # Flush any remaining audio chunks from sink
        remaining = sink.flush_all_remaining_chunks()
        for uid, name, pcm_bytes in remaining:
            wav_io = MeetingAudioSink.pcm_to_normalized_wav(pcm_bytes)
            if wav_io:
                t = asyncio.create_task(self._process_live_chunk(session, uid, name, wav_io))
                session.pending_tasks.add(t)

        # Await pending live transcription tasks (fast, max 6s timeout)
        if session.pending_tasks:
            try:
                await asyncio.wait(session.pending_tasks, timeout=6.0)
            except Exception:
                pass

        speaker_transcripts: list[tuple[str, str]] = []

        # 1. Primary path: group speech from live rolling timeline
        if session.transcript_timeline:
            unique_speakers = list(dict.fromkeys(s_name for _, s_name, _ in session.transcript_timeline))
            for s_name in unique_speakers:
                s_text = " ".join(txt for _, name, txt in session.transcript_timeline if name == s_name).strip()
                if s_text and len(s_text) >= 2:
                    speaker_transcripts.append((s_name, s_text))

        # 2. Safety fallback: if live timeline had 0 results, fall back to buffer batch processing
        if not speaker_transcripts:
            sem = asyncio.Semaphore(2)

            async def _transcribe_chunk_safe(ch: io.BytesIO) -> str:
                async with sem:
                    return await self._transcribe_audio(ch)

            all_uids = set(sink.speaker_names.keys()) | set(sink.speaker_buffers.keys())
            for uid in all_uids:
                name = sink.speaker_names.get(uid, f"Speaker-{uid}")
                chunks = await asyncio.to_thread(sink.get_speaker_wav_chunks, uid, 30)
                if not chunks:
                    continue

                chunk_results = await asyncio.gather(*[_transcribe_chunk_safe(ch) for ch in chunks], return_exceptions=True)
                speaker_texts = [txt for txt in chunk_results if isinstance(txt, str) and txt.strip()]

                full_speaker_text = " ".join(speaker_texts).strip()
                if full_speaker_text and len(full_speaker_text) >= 2:
                    speaker_transcripts.append((name, full_speaker_text))

        # Peak mic amplitude calculation (direct O(1) from live speaker_peaks with thread fallback)
        max_level = max(sink.speaker_peaks.values(), default=0)
        if max_level == 0:
            def _calc_max_amplitude(bufs: list[bytes]) -> int:
                peak = 0
                for b in bufs:
                    if b:
                        try:
                            arr = array.array("h", b)
                            if arr:
                                peak = max(peak, max(abs(s) for s in arr))
                        except Exception:
                            pass
                return peak

            raw_buffers_copy = [bytes(b) for b in sink.speaker_buffers.values() if b]
            if raw_buffers_copy:
                max_level = await asyncio.to_thread(_calc_max_amplitude, raw_buffers_copy)

        captured_packets = getattr(sink, "packet_count", 0)
        decoded_frames = getattr(sink, "decoded_frames", 0)
        silence_pkts = getattr(sink, "_silence_pkts", 0)
        dave_succ = getattr(sink, "_dave_succ", 0)
        dave_fail = getattr(sink, "_dave_fail", 0)
        dave_pass = getattr(sink, "_dave_pass", 0)
        last_dave_err = getattr(sink, "_last_dave_err", "none")
        first_hex = getattr(sink, "_first_hex", "empty")
        min_p = getattr(sink, "_min_payload_len", 0) if getattr(sink, "_min_payload_len", 999999) != 999999 else 0
        max_p = getattr(sink, "_max_payload_len", 0)
        len_info = f"{min_p}..{max_p}"
        ssrc_details = []
        for s, c in getattr(sink, "_ssrc_counts", {}).items():
            u_name = "unknown"
            if s in getattr(sink, "_ssrc_to_uid", {}):
                uid = sink._ssrc_to_uid[s]
                u_name = sink.speaker_names.get(uid, str(uid))
            ssrc_details.append(f"{s}->{u_name}:{c}")
        ssrc_summary = ", ".join(ssrc_details) if ssrc_details else "none"
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        if not speaker_transcripts:
            if target_ch:
                c = KyroContainer(accent_color=None)
                c.add_section(
                    content="**Kyro Meeting Intelligence**\n> *Session ended without audible speech.*"
                )
                c.add_separator(divider=True)
                vc_conn = getattr(session.voice_client, "_connection", None) if session and session.voice_client else None
                dave_ver = getattr(vc_conn, "dave_protocol_version", 0) if vc_conn else 0
                dave_sess = getattr(vc_conn, "dave_session", None) if vc_conn else None
                dave_ready = getattr(dave_sess, "ready", False) if dave_sess else False
                if captured_packets == 0:
                    diag_msg = "No voice packets received from Discord (all members were muted or channel was silent)."
                elif decoded_frames == 0:
                    diag_msg = f"Received {captured_packets} packets (silence={silence_pkts}, fail={dave_fail}), but frames were dropped (DAVE v{dave_ver} [ready={dave_ready}], err={last_dave_err[:35]})."
                else:
                    detail = getattr(self, "_last_transcribe_diag", None)
                    if not detail:
                        detail = "No human speech recognized"
                    opus_errs = getattr(sink, "_opus_err_count", 0)
                    dave_info = f"v{dave_ver} [ready={dave_ready}, succ={dave_succ}, fail={dave_fail}, pass={dave_pass}, sil={silence_pkts}, opus_err={opus_errs}]"
                    diag_msg = f"Captured {captured_packets} pkts (Decoded: {decoded_frames}, DAVE {dave_info}, SSRC: [{ssrc_summary}], hex: {first_hex}, payload: {len_info}, peak amp: {max_level}/32767). Engine: `{detail}`."
                c.add_text(
                    f"> {dot} **Duration:** `{duration_fmt}`\n"
                    f"> {dot} **Status:** `No Speech Detected`\n"
                    f"> {dot} **Audio Packets Captured:** `{captured_packets}` (Decoded: `{decoded_frames}`)\n"
                    f"> {dot} **Notice:** {diag_msg}"
                )
                c.add_separator(divider=True)
                c.add_text(f"-# Kyro Voice Intelligence • <t:{int(time.time())}:f>")
                await send_container_response(target_ch, c)
            try:
                sink.destroy()
            except Exception:
                pass
            return

        # 1. Sort timeline strictly by audio timestamp (guarantees 100% chronological dialogue order)
        session.transcript_timeline.sort(key=lambda x: x[0])

        # 2. Build formatted chronological dialogue lines [MM:SS] Speaker: Text
        chronological_lines: list[str] = []
        for t_stamp, s_name, s_txt in session.transcript_timeline:
            mins = int(t_stamp // 60)
            secs = int(t_stamp % 60)
            chronological_lines.append(f"[{mins:02d}:{secs:02d}] {s_name}: {s_txt}")
        chronological_transcript = "\n".join(chronological_lines)

        # 3. Build comprehensive input for AI (Never drop the verbatim conversation!)
        if session.rolling_summaries:
            milestones = "\n\n".join(session.rolling_summaries)
            combined_text = (
                f"=== MEETING PHASES & MILESTONES ===\n{milestones}\n\n"
                f"=== FULL CHRONOLOGICAL CONVERSATION ===\n{chronological_transcript}"
            )
        elif chronological_transcript:
            combined_text = chronological_transcript
        else:
            combined_text = "\n".join([f"{name}: {text}" for name, text in speaker_transcripts])

        # 4. Generate Deep Meeting Intelligence via Groq / Gemini
        intel = await self._generate_meeting_intelligence(combined_text, duration_seconds=duration)

        # Persist session to database via repository
        try:
            await self.repo.save_session(
                session.guild_id,
                session.voice_channel_id,
                session.host_id,
                duration,
                len(speaker_transcripts),
                intel["summary"],
                intel["decisions"],
                intel["action_items"],
            )
        except Exception as e:
            logger.debug(f"Notice saving meeting session to db: {e}")

        # Post redesigned Components V2 card and Verbatim Transcript to target channel
        if target_ch:
            vc = guild.get_channel(session.voice_channel_id)
            vc_name = vc.name if vc else "Voice Channel"
            enabled_modules = settings.get("modules", set())

            dot = self.bot.custom_emojis.get("heart_dot", "•")
            arrow = self.bot.custom_emojis.get("white_arrow", "›")
            file_icon = self.bot.custom_emojis.get("icons_file", "📝")

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Kyro Meeting Intelligence**\n"
                    f"> Executive meeting briefing, strategic decisions & task matrix for **{vc_name}**."
                )
            )
            container.add_separator(divider=True)

            # Metadata section
            topics_line = f" — **Topics:** `{intel['topics']}`" if "topics" in enabled_modules and intel.get("topics") else ""
            container.add_text(
                f"> {dot} **Room:** `{vc_name}` — **Duration:** `{duration_fmt}`\n"
                f"> {dot} **Speakers ({len(speaker_transcripts)}):** `{', '.join(s[0] for s in speaker_transcripts[:8])}`{topics_line}"
            )
            container.add_separator(divider=True)

            # Summary section
            if "summary" in enabled_modules:
                container.add_text(
                    f"**Executive Briefing:**\n"
                    f"{arrow} {intel['summary']}"
                )
                container.add_separator(divider=True)

            # Decisions
            if "decisions" in enabled_modules:
                decisions_clean = intel["decisions"].strip()
                container.add_text(
                    f"**Key Decisions & Consensus:**\n"
                    f"{decisions_clean}"
                )
                container.add_separator(divider=True)

            # Action Items
            if "action_items" in enabled_modules:
                actions_clean = intel["action_items"].strip()
                container.add_text(
                    f"**Action Items & Ownership:**\n"
                    f"{actions_clean}"
                )
                container.add_separator(divider=True)

            container.add_text(
                f"-# Recorded by Kyro Voice Intelligence • <t:{int(time.time())}:f>\n"
                f"-# {file_icon} Full verbatim transcript is attached below."
            )

            # Generate downloadable Markdown transcript document
            speaker_list_str = ", ".join(f"`{s[0]}`" for s in speaker_transcripts)
            transcript_content = (
                f"# Kyro Meeting Intelligence — Verbatim Transcript\n\n"
                f"| Attribute | Details |\n"
                f"| :--- | :--- |\n"
                f"| **Server** | {guild.name} (`{guild.id}`) |\n"
                f"| **Voice Channel** | {vc_name} (`{session.voice_channel_id}`) |\n"
                f"| **Duration** | {duration_fmt} ({duration}s) |\n"
                f"| **Recorded At** | <t:{int(session.start_time)}:F> |\n"
                f"| **Speakers** | {speaker_list_str} |\n"
                f"| **Topics** | {intel.get('topics', 'General VC')} |\n\n"
                f"---\n\n"
                f"## 1. Executive Briefing\n\n"
                f"{intel['summary']}\n\n"
                f"---\n\n"
                f"## 2. Key Decisions & Consensus\n\n"
                f"{intel['decisions']}\n\n"
                f"---\n\n"
                f"## 3. Action Items & Ownership\n\n"
                f"{intel['action_items']}\n\n"
                f"---\n\n"
                f"## 4. Full Verbatim Chronological Transcript\n\n"
                f"```text\n"
                f"{chronological_transcript if chronological_transcript else 'No speech timeline captured.'}\n"
                f"```\n"
            )

            file_bytes = io.BytesIO(transcript_content.encode("utf-8"))
            filename = f"kyro_meeting_{session.guild_id}_{int(time.time())}.md"
            transcript_file = discord.File(fp=file_bytes, filename=filename)

            try:
                await send_container_response(target_ch, container, file=transcript_file)
            except Exception as e:
                logger.error(f"Error dispatching meeting container with file: {e}", exc_info=True)
                try:
                    await send_container_response(target_ch, container)
                    file_bytes.seek(0)
                    await target_ch.send(file=transcript_file)
                except Exception as inner_e:
                    logger.error(f"Failed fallback dispatch: {inner_e}")

            # If command channel is different, leave a fleeting link notice
            if session.text_channel_id != target_ch.id:
                cmd_ch = guild.get_channel(session.text_channel_id)
                if isinstance(cmd_ch, discord.TextChannel):
                    try:
                        await cmd_ch.send(
                            f"-# {dot} 📝 Meeting summary and transcript file have been posted to {target_ch.mention}.",
                            delete_after=10.0,
                        )
                    except Exception:
                        pass
        try:
            sink.destroy()
        except Exception:
            pass

    # ------------------ COMMAND INTERFACE ------------------

    def _build_usage_card(self, ctx: CustomContext) -> KyroContainer:
        """Construct the Components V2 usage guide for meeting commands."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content="**Meeting Commands**\n> *Autonomous voice meeting intelligence, diarization & summaries.*"
        )
        container.add_separator(divider=True)
        container.add_text(
            f"> {dot} `{prefix}meeting start`\n"
            f"> {dot} `{prefix}meeting stop`\n"
            f"> {dot} `{prefix}meeting show`\n"
            f"> {dot} `{prefix}meeting setup`\n"
            f"> {dot} `{prefix}meeting channel <#channel|reset>`\n"
            f"> {dot} `{prefix}meeting enable`\n"
            f"> {dot} `{prefix}meeting disable`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    @commands.group(
        name="meeting",
        aliases=["meetings", "meet"],
        description="Autonomous VC Meeting Recording & Intelligence Summarization.",
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def meeting_group(self, ctx: CustomContext) -> None:
        """Display Meeting usage guide when invoked without subcommands."""
        if ctx.invoked_subcommand is not None:
            return
        container = self._build_usage_card(ctx)
        await send_container_response(ctx, container)

    @meeting_group.command(name="setup", description="Launch the step-by-step Meeting Intelligence setup wizard.")
    async def meeting_setup(self, ctx: CustomContext) -> None:
        """Launch the Meeting Intelligence interactive setup wizard."""
        if not (ctx.author.guild_permissions.administrator or ctx.author.id == ctx.guild.owner_id):
            await ctx.send_warning("Only administrators can configure Meeting Intelligence.")
            return

        wizard = MeetingSetupWizard(self.bot, ctx.guild, ctx.author)
        container = wizard.get_dashboard_container()
        await send_container_response(ctx, container, view=wizard)

    @meeting_group.command(name="enable", description="Enable Meeting Intelligence on this server.")
    async def meeting_enable(self, ctx: CustomContext) -> None:
        """Turn on meeting recording and summary generation."""
        if not (ctx.author.guild_permissions.administrator or ctx.author.id == ctx.guild.owner_id):
            await ctx.send_warning("Only administrators can enable Meeting Intelligence.")
            return

        await self.repo.set_enabled(ctx.guild.id, True)

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content="**Kyro Meeting Intelligence**\n> Meeting recording and intelligence are now enabled on this server."
        )
        container.add_separator(divider=True)
        container.add_text(
            f"> {dot} **Status:** {sw_on} `Enabled`\n"
            f"> {dot} **Quick Start:** Connect to any voice channel and run `{ctx.clean_prefix}meeting start`."
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Enabled by {ctx.author.display_name} • <t:{int(time.time())}:f>")
        await send_container_response(ctx, container)

    @meeting_group.command(name="disable", description="Disable Meeting Intelligence on this server.")
    async def meeting_disable(self, ctx: CustomContext) -> None:
        """Turn off meeting recording and summary generation."""
        if not (ctx.author.guild_permissions.administrator or ctx.author.id == ctx.guild.owner_id):
            await ctx.send_warning("Only administrators can disable Meeting Intelligence.")
            return

        session = self._sessions.pop(ctx.guild.id, None)
        if session:
            try:
                session.voice_client.stop_listening()
                await session.voice_client.disconnect(force=True)
                session.voice_client.cleanup()
                session.sink.destroy()
            except Exception:
                pass
            try:
                self.bot._connection._remove_voice_client(ctx.guild.id)
            except Exception:
                pass

        await self.repo.set_enabled(ctx.guild.id, False)

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "[OFF]")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Kyro Meeting Intelligence**\n> Meeting recording is now disabled on this server.")
        container.add_separator(divider=True)
        container.add_text(
            f"> {dot} **Status:** {sw_off} `Disabled`\n"
            f"> {dot} **Notice:** Use `{ctx.clean_prefix}meeting enable` or `{ctx.clean_prefix}meeting setup` to re-enable."
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Disabled by {ctx.author.display_name} • <t:{int(time.time())}:f>")
        await send_container_response(ctx, container)

    @meeting_group.command(
        name="channel",
        aliases=["setchannel", "feed"],
        description="Set or reset the meeting reports channel.",
    )
    async def meeting_channel(
        self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Set designated meeting feed channel, or reset to auto-create."""
        if not (ctx.author.guild_permissions.administrator or ctx.author.id == ctx.guild.owner_id):
            await ctx.send_warning("Only administrators can configure the meeting channel.")
            return

        dot = self.bot.custom_emojis.get("heart_dot", "•")

        if channel is None:
            await self.repo.set_channel(ctx.guild.id, None)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content="**Meeting Feed Channel Reset**\n> Summary destination has been reset to auto-create `#kyro-meetings`."
            )
            container.add_separator(divider=True)
            container.add_text(
                f"> {dot} **Destination:** `Auto-create (#kyro-meetings)`\n"
                f"> {dot} **Tip:** Specify a channel with `{ctx.clean_prefix}meeting channel #channel` to customize."
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Configured by {ctx.author.display_name} • <t:{int(time.time())}:f>")
            await send_container_response(ctx, container)
            return

        perms = channel.permissions_for(ctx.guild.me)
        if not (perms.view_channel and perms.send_messages and perms.embed_links):
            await ctx.send_warning(
                f"Kyro lacks permissions (`View Channel`, `Send Messages`, `Embed Links`) in {channel.mention}."
            )
            return

        await self.repo.set_channel(ctx.guild.id, channel.id)

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=f"**Meeting Feed Channel Configured**\n> Meeting executive reports will now be delivered to {channel.mention}."
        )
        container.add_separator(divider=True)
        container.add_text(
            f"> {dot} **Feed Channel:** {channel.mention}\n"
            f"> {dot} **Channel ID:** `{channel.id}`\n"
            f"> {dot} **How to reset:** Use `{ctx.clean_prefix}meeting channel` without arguments."
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Configured by {ctx.author.display_name} • <t:{int(time.time())}:f>")
        await send_container_response(ctx, container)

    @meeting_group.command(name="show", aliases=["status", "info", "config"], description="Show Meeting status, feed channel, and metrics.")
    async def meeting_show(self, ctx: CustomContext) -> None:
        """Display live meeting configuration and active session status."""
        await self._show_meeting_status(ctx)

    async def _show_meeting_status(self, ctx: CustomContext) -> None:
        """Helper to build and send the comprehensive Meeting Status card."""
        guild = ctx.guild
        settings = await self._get_meeting_settings(guild.id)
        is_enabled = settings.get("enabled", True)
        ch_id = settings.get("channel_id")
        privacy_mode = settings.get("privacy_mode", "locked")
        enabled_modules = settings.get("modules", set())

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "[OFF]")
        status_sw = sw_on if is_enabled else sw_off

        # Channel display
        if ch_id:
            ch_obj = guild.get_channel(ch_id)
            ch_disp = ch_obj.mention if ch_obj else f"`#deleted-channel` (ID: `{ch_id}`)"
        else:
            ch_disp = "`Auto-create (#kyro-meetings)`"

        privacy_names = {
            "locked": "Locked (Read-Only)",
            "hidden": "Hidden (Private)",
            "public": "Normal (Public)",
        }
        priv_disp = f"`{privacy_names.get(privacy_mode, 'Locked')}`"

        total_mods = 5
        sel_count = len(enabled_modules)
        mod_disp = (
            f"`All Modules Active ({total_mods}/{total_mods})`"
            if sel_count >= total_mods
            else f"`{sel_count}/{total_mods} Modules Active`"
        )

        # Total meetings logged count
        try:
            total_sessions = await self.repo.get_total_sessions_count(guild.id)
        except Exception:
            total_sessions = 0

        # Active session state
        active_session = self._sessions.get(guild.id)
        if active_session:
            elapsed = int(time.time() - active_session.start_time)
            vc = guild.get_channel(active_session.voice_channel_id)
            vc_name = vc.name if vc else "Voice"
            session_line = f"`Recording in {vc_name} ({elapsed // 60}m {elapsed % 60}s)`"
        elif guild.id in self._connecting_guilds:
            session_line = "`Connecting to Voice Channel...`"
        else:
            session_line = "`Standby (No Active Meeting)`"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Kyro Meeting Intelligence**\n"
                "> *AI-powered voice meeting recording, transcription, and executive reports.*"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"> {dot} **Status:** {status_sw}\n"
            f"> {dot} **Intelligence Modules:** {mod_disp}\n"
            f"> {dot} **Summary Channel:** {ch_disp}\n"
            f"> {dot} **Channel Access:** {priv_disp}\n"
            f"> {dot} **Active Session:** {session_line}\n"
            f"> {dot} **Total Meetings Logged:** `{total_sessions}`"
        )
        container.add_separator(divider=True)
        container.add_text(
            f"> **Quick Start:** Connect to any VC and type `{ctx.clean_prefix}meeting start`.\n"
            f"> **Reconfigure:** Use `{ctx.clean_prefix}meeting setup` or `{ctx.clean_prefix}meeting channel`."
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Kyro Voice Intelligence • <t:{int(time.time())}:f>")
        await send_container_response(ctx, container)

    @meeting_group.command(name="start", description="Start an autonomous meeting recording session in your VC.")
    async def meeting_start(self, ctx: CustomContext) -> None:
        """Connect to author's voice channel and initiate recording sink."""
        guild = ctx.guild
        author = ctx.author

        # Check if meeting intelligence is enabled
        settings = await self._get_meeting_settings(guild.id)
        if not settings.get("enabled", True):
            await ctx.send_warning(
                f"Meeting Intelligence is currently **disabled** on this server. Use `{ctx.clean_prefix}meeting enable` or `{ctx.clean_prefix}meeting setup` to enable."
            )
            return

        # Check voice state
        if not isinstance(author, discord.Member) or not author.voice or not author.voice.channel:
            await ctx.send_warning("You must be connected to a **Voice Channel** to start a meeting.")
            return

        vc = author.voice.channel

        # Pre-flight voice channel permissions and capacity checks
        me = guild.me
        perms = vc.permissions_for(me)
        if not perms.connect:
            await ctx.send_warning(f"Kyro lacks **Connect** permission to join {vc.mention}.")
            return
        if vc.user_limit and vc.user_limit > 0:
            if len(vc.members) >= vc.user_limit and not perms.move_members:
                await ctx.send_warning(f"Voice channel {vc.mention} is full (`{len(vc.members)}/{vc.user_limit}`).")
                return

        # Check if meeting already active
        if guild.id in self._sessions:
            active_s = self._sessions[guild.id]
            is_active = False
            if active_s and active_s.voice_client:
                is_active = getattr(active_s.voice_client, "is_connected", lambda: False)()
            if not is_active:
                logger.info(f"Guild {guild.id}: Stale meeting session detected without live voice client. Auto-recovering...")
                self._sessions.pop(guild.id, None)
            else:
                curr_vc = guild.get_channel(active_s.voice_channel_id)
                vc_str = curr_vc.mention if curr_vc else "another voice channel"
                await ctx.send_warning(f"A meeting is already active in {vc_str}. Use `,meeting stop` first.")
                return

        # Concurrency safety: check if Lavalink music is actively playing or queued
        try:
            music_cog = self.bot.get_cog("Music")
            if music_cog and hasattr(music_cog, "controller"):
                m_player = music_cog.controller.get_player(guild.id)
                if m_player and (m_player.is_playing or len(m_player.queue) > 0):
                    await ctx.send_warning(
                        "Music playback or queue is currently active in this server. Please stop music before starting a meeting session."
                    )
                    return
        except Exception:
            pass

        if guild.id in self._connecting_guilds:
            await ctx.send_warning("A voice connection attempt is already in progress for this server. Please wait a moment.")
            return

        self._connecting_guilds.add(guild.id)
        try:
            # Cleanly disconnect any idle, stale, or existing voice connection before attaching VoiceRecvClient
            had_previous_voice = bool(guild.voice_client or (guild.me.voice and guild.me.voice.channel))
            if had_previous_voice:
                try:
                    music_cog = self.bot.get_cog("Music")
                    if music_cog and hasattr(music_cog, "controller"):
                        m_player = music_cog.controller.get_player(guild.id)
                        if m_player:
                            m_player.cancel_empty_vc_timer(auto_resume=False)
                            m_player.voice_client = None
                except Exception:
                    pass

                existing_vc = guild.voice_client
                if existing_vc:
                    try:
                        if hasattr(existing_vc, "stop_listening"):
                            existing_vc.stop_listening()
                    except Exception:
                        pass
                    try:
                        await asyncio.wait_for(existing_vc.disconnect(force=True), timeout=3.0)
                    except Exception:
                        pass
                    try:
                        existing_vc.cleanup()
                    except Exception:
                        pass
                try:
                    self.bot._connection._remove_voice_client(guild.id)
                except Exception:
                    pass
                await asyncio.sleep(0.5)

            # Auto-ensure meeting channel if not yet created
            settings = await self._get_meeting_settings(guild.id)
            if not settings.get("channel_id"):
                target_ch, _ = await ensure_meeting_channel(
                    self.bot, guild, author, privacy_mode=settings.get("privacy_mode", "locked")
                )
                if target_ch:
                    await self.repo.set_channel(
                        guild.id,
                        target_ch.id,
                        privacy_mode=settings.get("privacy_mode", "locked"),
                    )

            # Check voice receiver module availability
            if not VOICE_RECV_AVAILABLE or voice_recv is None:
                await ctx.send_warning(
                    "Voice receiver module (`discord-ext-voice-recv`) is not active in this bot environment.\n"
                    "Please run `pip install discord-ext-voice-recv` on the server."
                )
                return

            # Connect with VoiceRecvClient (automated retry & reconnect=True for Discord 4006 session recovery)
            voice_client: Optional[voice_recv.VoiceRecvClient] = None
            last_conn_err: Optional[Exception] = None

            for attempt in range(3):
                try:
                    if hasattr(self.bot._connection, "_voice_clients"):
                        self.bot._connection._remove_voice_client(guild.id)

                    voice_client = await vc.connect(
                        cls=voice_recv.VoiceRecvClient, timeout=20.0, reconnect=True, self_deaf=False, self_mute=False
                    )
                    if voice_client and voice_client.is_connected():
                        break
                except Exception as e:
                    last_conn_err = e
                    logger.warning(f"Guild {guild.id}: VoiceRecvClient connect attempt {attempt + 1} notice: {e}")
                    try:
                        if guild.voice_client:
                            await asyncio.wait_for(guild.voice_client.disconnect(force=True), timeout=3.0)
                    except Exception:
                        pass
                    try:
                        self.bot._connection._remove_voice_client(guild.id)
                    except Exception:
                        pass
                    await asyncio.sleep(1.0 + attempt * 0.5)

            if not voice_client or not voice_client.is_connected():
                logger.error(f"Failed to connect to VC for meeting in guild {guild.id}: {last_conn_err}", exc_info=True)
                await ctx.send_error(f"Could not connect to voice channel: `{last_conn_err}`", ephemeral=False)
                return

            # Proactively ensure DAVE session is initialized if Discord requested DAVE protocol
            try:
                conn = getattr(voice_client, "_connection", None)
                dave_ver = getattr(conn, "dave_protocol_version", 0)
                if conn and dave_ver > 0 and getattr(conn, "dave_session", None) is None:
                    await conn.reinit_dave_session()
                    logger.info(f"Initialized DAVE v{dave_ver} session and transmitted MLS Key Package.")
            except Exception as e:
                logger.warning(f"Notice during DAVE init: {e}")

            # Wait up to 3s for initial voice gateway secret_key (XSalsa20 session established)
            for _ in range(30):
                if voice_client.is_connected() and getattr(voice_client, "secret_key", None):
                    break
                await asyncio.sleep(0.1)

            if not (voice_client.is_connected() and getattr(voice_client, "secret_key", None)):
                try:
                    await voice_client.disconnect(force=True)
                except Exception:
                    pass
                await ctx.send_error("Could not complete Discord voice encryption handshake. Please try again.", ephemeral=False)
                return

            # Wait up to 3.5s for DAVE MLS session to become ready if DAVE was initiated by Discord
            handshake_ok = False
            conn = getattr(voice_client, "_connection", None)
            for _ in range(35):
                dave_ver = getattr(conn, "dave_protocol_version", 0)
                dave = getattr(conn, "dave_session", None)
                dave_ready = getattr(dave, "ready", False) if dave else False
                if dave_ready:
                    handshake_ok = True
                    logger.info(f"DAVE session ready (v{dave_ver}), starting meeting sink.")
                    break
                if dave_ver == 0 and dave is None:
                    # Standard non-E2EE voice channel - no MLS handshake delay needed
                    handshake_ok = True
                    logger.info("Non-E2EE voice channel, proceeding immediately with standard audio pipeline.")
                    break
                await asyncio.sleep(0.1)

            if not handshake_ok:
                dave_ver = getattr(conn, "dave_protocol_version", 0)
                dave = getattr(conn, "dave_session", None)
                dave_ready = getattr(dave, "ready", False) if dave else False
                if dave_ver == 0 and dave is None:
                    handshake_ok = True
                    logger.info("Non-E2EE voice channel, proceeding with standard audio pipeline.")
                elif dave is not None and not dave_ready:
                    try:
                        dave.set_passthrough_mode(True, 120)
                        handshake_ok = True
                        logger.info(f"DAVE v{dave_ver} MLS transition: enabled passthrough mode.")
                    except Exception as _pte:
                        logger.debug(f"Failed to set DAVE passthrough mode: {_pte}")

            if not handshake_ok:
                try:
                    await voice_client.disconnect(force=True)
                except Exception:
                    pass
                await ctx.send_error("Could not complete Discord voice encryption handshake (DAVE). Please try again.", ephemeral=False)
                return

            sink = MeetingAudioSink(noise_gate=0)
            sink._voice_client = voice_client
            try:
                voice_client.listen(sink)
            except Exception as e:
                logger.error(f"Failed to attach sink in guild {guild.id}: {e}", exc_info=True)
                try:
                    await voice_client.disconnect(force=True)
                except Exception:
                    pass
                await ctx.send_error(f"Failed to initiate voice receive pipeline: `{e}`", ephemeral=False)
                return

            # Force-resume discord.py SocketReader to guarantee UDP packet loop is unblocked
            try:
                sock_reader = getattr(voice_client._connection, "_socket_reader", None)
                if sock_reader:
                    # SocketReader.resume() takes no arguments — our monkey-patch in the
                    # imports section already cleared _idle_paused and set _running on register().
                    # Calling resume() here ensures it stays unblocked if it ever re-paused.
                    sock_reader.resume()
                    logger.info(f"Unblocked and force-resumed SocketReader (running={sock_reader._running.is_set()})")
            except Exception as _sr_err:
                logger.warning(f"Failed to force-resume SocketReader: {_sr_err}")

            # Prime Discord Voice SFU and punch UDP firewall hole to start receiving participant audio
            try:
                if hasattr(voice_client, "ws") and voice_client.ws:
                    await voice_client.ws.speak(discord.gateway.SpeakingState.voice)
                    for _ in range(5):
                        voice_client.send_audio_packet(b"\xf8\xff\xfe", encode=False)
                        await asyncio.sleep(0.02)
                    await voice_client.ws.speak(discord.gateway.SpeakingState.none)
            except Exception as e:
                logger.debug(f"Notice priming voice gateway speaking state: {e}")

            new_session = MeetingSession(
                guild_id=guild.id,
                voice_channel_id=vc.id,
                text_channel_id=ctx.channel.id,
                host_id=author.id,
                start_time=time.time(),
                voice_client=voice_client,
                sink=sink,
            )
            new_session.monitor_task = asyncio.create_task(self._live_session_monitor(new_session))
            self._sessions[guild.id] = new_session

            dot = self.bot.custom_emojis.get("heart_dot", "•")
            sw_on = self.bot.custom_emojis.get("icon_switch_on", "[ON]")

            # Fetch destination channel mention
            settings = await self._get_meeting_settings(guild.id)
            ch_id = settings.get("channel_id")
            dest_str = f"<#{ch_id}>" if ch_id else ctx.channel.mention

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=f"**Kyro Meeting Started**\n> *Connected to **{vc.name}**. Voice intelligence is active.*"
            )
            container.add_separator(divider=True)
            container.add_text(
                f"> {dot} **Room:** {vc.mention}\n"
                f"> {dot} **Recording Status:** {sw_on} `Listening & Diarizing`\n"
                f"> {dot} **Summary Destination:** {dest_str}\n"
                f"> {dot} **How to finish:** Use `,meeting stop` when your meeting concludes."
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Started by {author.display_name} • <t:{int(time.time())}:f>")
            await send_container_response(ctx, container)
        finally:
            self._connecting_guilds.discard(guild.id)

    @meeting_group.command(name="stop", aliases=["end"], description="Stop the meeting and generate summary.")
    async def meeting_stop(self, ctx: CustomContext) -> None:
        """Stop voice listening, disconnect VC, and generate executive summary."""
        guild = ctx.guild
        session = self._sessions.get(guild.id)

        if not session:
            await ctx.send_warning("There is no active meeting session in this server.")
            return

        # Restrict stop command to host, administrators, or current VC participants
        is_host = ctx.author.id == session.host_id
        is_admin = (
            ctx.author.guild_permissions.administrator
            or ctx.author.guild_permissions.manage_guild
            or ctx.author.id == guild.owner_id
        )
        in_vc = (
            isinstance(ctx.author, discord.Member)
            and ctx.author.voice
            and ctx.author.voice.channel
            and ctx.author.voice.channel.id == session.voice_channel_id
        )
        if not (is_host or is_admin or in_vc):
            await ctx.send_warning(
                "Only the meeting host, an administrator, or members in the meeting VC can stop this session."
            )
            return

        self._sessions.pop(guild.id, None)

        # Disconnect gracefully
        try:
            session.voice_client.stop_listening()
            await asyncio.wait_for(session.voice_client.disconnect(force=True), timeout=2.0)
            session.voice_client.cleanup()
        except Exception as e:
            logger.debug(f"Notice during meeting disconnect: {e}")
        try:
            self.bot._connection._remove_voice_client(guild.id)
        except Exception:
            pass
        try:
            await guild.change_voice_state(channel=None)
        except Exception:
            pass

        duration = int(time.time() - session.start_time)
        if duration < 10:
            if session.monitor_task and not session.monitor_task.done():
                session.monitor_task.cancel()
            for t in session.pending_tasks:
                if not t.done():
                    t.cancel()
            session.sink.destroy()
            container = KyroContainer(accent_color=None)
            container.add_section(
                content="**Meeting Concluded**\n> The meeting was stopped after less than 10 seconds. Session discarded without generating a summary."
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Stopped by {ctx.author.display_name} • Duration: `{duration}s`")
            await send_container_response(ctx, container)
            return

        dot = self.bot.custom_emojis.get("heart_dot", "•")

        # Inform channel that AI processing is underway
        toast = await ctx.send(f"-# {dot} Finalizing meeting audio and synthesizing executive report...")

        # Process in background task
        async def _run_process() -> None:
            try:
                await self._process_meeting_completion(session)
            finally:
                try:
                    await toast.delete()
                except Exception:
                    pass

        asyncio.create_task(_run_process())

    @commands.Cog.listener("on_voice_state_update")
    async def on_voice_state_update_handler(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Auto-finish meeting if all members leave the meeting VC."""
        # Ignore voice state updates where channel did not change (mute/unmute/deafen/stream)
        if before.channel == after.channel:
            return

        guild = member.guild
        session = self._sessions.get(guild.id)
        if not session:
            return

        # Check if the bot itself was disconnected from voice
        if self.bot.user and member.id == self.bot.user.id:
            if after.channel is None:
                # Guard against spurious / delayed gateway disconnect events when client is still alive
                if session.voice_client and session.voice_client.is_connected():
                    logger.debug(f"Guild {guild.id}: Received null voice state but VoiceRecvClient is still connected. Ignoring.")
                    return

                logger.info(f"Bot was disconnected from meeting VC in guild {guild.id}. Finalizing session...")
                active_s = self._sessions.pop(guild.id, None)
                if active_s:
                    try:
                        active_s.voice_client.stop_listening()
                        active_s.voice_client.cleanup()
                    except Exception:
                        pass
                    # Only synthesize AI completion if meeting ran for at least 10 seconds
                    if time.time() - active_s.start_time >= 10.0:
                        asyncio.create_task(self._process_meeting_completion(active_s))
                    else:
                        if active_s.monitor_task and not active_s.monitor_task.done():
                            active_s.monitor_task.cancel()
                        for t in active_s.pending_tasks:
                            if not t.done():
                                t.cancel()
                        active_s.sink.destroy()
                        logger.info(f"Guild {guild.id}: Meeting disconnected <10s after start ({time.time() - active_s.start_time:.1f}s); cleanly discarded.")
            return

        if member.bot:
            return

        # Check if auto_leave is enabled in guild settings
        settings = await self._get_meeting_settings(guild.id)
        if "auto_leave" not in settings.get("modules", set()):
            return

        # Check if change affected our meeting VC
        if before.channel and before.channel.id == session.voice_channel_id:
            non_bots = [m for m in before.channel.members if not m.bot]
            if len(non_bots) == 0:
                logger.info(f"Auto-stopping meeting in guild {guild.id} because VC is now empty.")
                active_s = self._sessions.pop(guild.id, None)
                if active_s:
                    try:
                        active_s.voice_client.stop_listening()
                        await asyncio.wait_for(active_s.voice_client.disconnect(force=True), timeout=2.0)
                        active_s.voice_client.cleanup()
                    except Exception:
                        pass
                    try:
                        self.bot._connection._remove_voice_client(guild.id)
                    except Exception:
                        pass
                    try:
                        await guild.change_voice_state(channel=None)
                    except Exception:
                        pass
                    if time.time() - active_s.start_time >= 10.0:
                        asyncio.create_task(self._process_meeting_completion(active_s))
                    else:
                        if active_s.monitor_task and not active_s.monitor_task.done():
                            active_s.monitor_task.cancel()
                        for t in active_s.pending_tasks:
                            if not t.done():
                                t.cancel()
                        active_s.sink.destroy()
                        logger.info(f"Guild {guild.id}: Meeting ended due to empty VC in <10s; cleanly discarded.")


async def setup(bot: KyroBot) -> None:
    """Register MeetingCog."""
    await bot.add_cog(MeetingCog(bot))
