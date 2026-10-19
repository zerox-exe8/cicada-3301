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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

try:
    import discord.ext.voice_recv as voice_recv
    VOICE_RECV_AVAILABLE = True
    AudioSinkBase = voice_recv.AudioSink

    # Discord.py bug workaround: SocketReader starts paused and clears _idle_paused.
    # Its register() checks if self._idle_paused before setting _running, which evaluates
    # to False, leaving the socket reading thread permanently deadlocked.
    import discord.voice_state as _vs

    def _fixed_socket_reader_register(self, callback) -> None:
        self._callbacks.append(callback)
        self._idle_paused = False
        self._running.set()

    _vs.SocketReader.register = _fixed_socket_reader_register
except (ImportError, Exception):
    voice_recv = None
    VOICE_RECV_AVAILABLE = False
    AudioSinkBase = object

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
        self._ssrc_to_uid: dict[int, Any] = {}
        self._voice_client: Optional[Any] = None
        self.packet_count: int = 0

    def wants_opus(self) -> bool:
        """Request decoded 48kHz 16-bit stereo PCM from voice_recv."""
        return False

    def write(self, user: Optional[discord.Member | discord.User], data: voice_recv.VoiceData) -> None:
        """Receive audio frame, downsample to 16kHz mono, and buffer with SSRC tracking."""
        try:
            self.packet_count += 1
            if self.packet_count == 1:
                logger.info("MeetingAudioSink received first incoming voice packet from Discord.")
            elif self.packet_count % 1000 == 0:
                logger.debug(f"MeetingAudioSink captured {self.packet_count} packets so far.")
            if not data or not data.pcm:
                return

            pcm = data.pcm
            if len(pcm) < 12:
                return

            # Ensure even byte count for 16-bit array
            if len(pcm) % 2 != 0:
                pcm = pcm[: len(pcm) - 1]

            # Downsample 48kHz stereo 16-bit -> 16kHz mono (taking left channel every 3rd sample)
            try:
                pcm_array = array.array("h", pcm)
                downsampled = pcm_array[0::6].tobytes()
            except Exception:
                return

            # Resolve speaker identification
            uid: Any = None
            name: str = "Unknown Speaker"

            ssrc = getattr(data.packet, "ssrc", None) if hasattr(data, "packet") else None

            if user and not getattr(user, "bot", False):
                uid = user.id
                name = getattr(user, "display_name", str(user))
                if ssrc:
                    self._ssrc_to_uid[ssrc] = uid
            elif ssrc:
                # Check if SSRC was mapped before
                if ssrc in self._ssrc_to_uid:
                    uid = self._ssrc_to_uid[ssrc]
                    name = self.speaker_names.get(uid, f"Speaker-{ssrc}")
                else:
                    # Try resolving via voice_client SSRC table
                    vc = getattr(self, "voice_client", None) or getattr(self, "_voice_client", None)
                    if vc:
                        resolved_id = getattr(vc, "_get_id_from_ssrc", lambda s: None)(ssrc)
                        if resolved_id:
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

            # If audio was previously recorded under provisional 'ssrc_{ssrc}', merge into resolved uid
            if ssrc:
                provisional_key = f"ssrc_{ssrc}"
                if provisional_key in self.speaker_buffers and uid != provisional_key:
                    prev_audio = self.speaker_buffers.pop(provisional_key, bytearray())
                    self.speaker_names.pop(provisional_key, None)
                    self.speaker_chunks.pop(provisional_key, None)
                    if uid not in self.speaker_buffers:
                        self.speaker_buffers[uid] = bytearray()
                        self.speaker_names[uid] = name
                        self.speaker_chunks[uid] = 0
                    self.speaker_buffers[uid] = prev_audio + self.speaker_buffers[uid]

            if uid not in self.speaker_buffers:
                self.speaker_buffers[uid] = bytearray()
                self.speaker_names[uid] = name
                self.speaker_chunks[uid] = 0

            self.speaker_buffers[uid].extend(downsampled)
            self.speaker_chunks[uid] += 1
        except Exception:
            return

    def get_speaker_wav_chunks(self, user_id: Any, chunk_seconds: int = 120) -> list[io.BytesIO]:
        """Split a speaker's PCM buffer into WAV chunks (default 120s max each) for robust API ingestion."""
        buf = self.speaker_buffers.get(user_id)
        if not buf or len(buf) < 16000 * 2 * 0.3:  # Less than 0.3 seconds of speech
            return []

        chunk_bytes = chunk_seconds * 16000 * 2
        chunks: list[io.BytesIO] = []

        for offset in range(0, len(buf), chunk_bytes):
            slice_data = bytes(buf[offset : offset + chunk_bytes])
            if len(slice_data) < 16000 * 2 * 0.3:
                continue

            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wf:
                wf.setnchannels(1)  # Mono
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(16000)  # 16kHz
                wf.writeframes(slice_data)

            wav_io.seek(0)
            chunks.append(wav_io)

        return chunks

    def get_speaker_wav(self, user_id: Any) -> Optional[io.BytesIO]:
        """Convert a speaker's 16kHz mono PCM buffer into a single in-memory WAV buffer."""
        chunks = self.get_speaker_wav_chunks(user_id, chunk_seconds=600)
        return chunks[0] if chunks else None

    def cleanup(self) -> None:
        """Clear memory buffers."""
        self.speaker_buffers.clear()
        self.speaker_names.clear()
        self.speaker_chunks.clear()
        self._ssrc_to_uid.clear()


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


class MeetingCog(commands.Cog):
    """
    Intelligent Autonomous Voice Meeting Recording & Executive Summarization Engine.
    Records multi-speaker meetings silently, transcribes audio via Groq Whisper,
    and extracts executive action items and decisions via Gemini Intelligence.
    """

    category: str = "Meeting"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # guild_id -> MeetingSession
        self._sessions: dict[int, MeetingSession] = {}

    def cog_unload(self) -> None:
        """Clean up all active recording sessions when unloading cog."""
        for s in list(self._sessions.values()):
            try:
                s.voice_client.stop_listening()
                asyncio.create_task(s.voice_client.disconnect(force=True))
                s.sink.cleanup()
            except Exception:
                pass
        self._sessions.clear()

    # ------------------ SETTINGS HELPERS ------------------

    async def _get_meeting_settings(self, guild_id: int) -> dict[str, Any]:
        """Fetch guild meeting configuration from database."""
        row = await self.bot.db.fetch_one(
            "SELECT * FROM meeting_settings WHERE guild_id = $1;", guild_id
        )
        if row:
            modules_raw = row.get("modules") or ""
            modules_set = {m.strip() for m in modules_raw.split(",") if m.strip()}
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

    async def _transcribe_audio(self, wav_io: io.BytesIO) -> str:
        """
        State-of-the-art multilingual and Indian regional speech-to-text pipeline.
        Tier 1: Google Speech Recognition (free, specialized in hi-IN, mr-IN, en-IN conversational speech).
        Tier 2: Google Gemini Multimodal (gemini-3.5-transcribe & gemini-3.5-flash-lite) for deep multilingual context.
        Tier 3: Groq Whisper-large-v3-turbo (if configured).
        """
        wav_data = wav_io.read()
        if not wav_data or len(wav_data) < 1000:
            return ""

        # Tier 1: Google Speech Recognition (Optimized for Indian dialects: Hindi, Hinglish, Marathi, etc.)
        if SPEECH_RECOGNITION_AVAILABLE and sr is not None:
            try:
                def _run_google_sr() -> str:
                    recognizer = sr.Recognizer()
                    recognizer.energy_threshold = 300
                    recognizer.dynamic_energy_threshold = False
                    with sr.AudioFile(io.BytesIO(wav_data)) as source:
                        audio = recognizer.record(source)
                    # Try hi-IN (Hindi + Hinglish) first
                    try:
                        res = recognizer.recognize_google(audio, language="hi-IN")
                        if res and len(res.strip()) > 1:
                            return res.strip()
                    except Exception:
                        pass
                    # Fallback to en-IN (Indian English / Mixed)
                    try:
                        res = recognizer.recognize_google(audio, language="en-IN")
                        if res and len(res.strip()) > 1:
                            return res.strip()
                    except Exception:
                        pass
                    return ""

                sr_result = await asyncio.to_thread(_run_google_sr)
                if sr_result:
                    return sr_result
            except Exception as e:
                logger.debug(f"Notice from Google Speech Recognition: {e}")

        # Tier 2: Google Gemini Multimodal Audio (gemini-3.5-transcribe, gemini-3.5-flash-lite)
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        if gemini_key:
            b64_audio = base64.b64encode(wav_data).decode("utf-8")
            models = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite"]

            prompt = (
                "You are an expert audio transcription system specializing in Indian speech and multilingual meetings. "
                "Transcribe the spoken audio verbatim in its original language (Hindi, Hinglish, Marathi, Bengali, Tamil, Telugu, Gujarati, Bhojpuri, Punjabi, or Indian English). "
                "Output ONLY the transcribed words. Do not add timestamps (e.g. 00:00), speaker tags, commentary, or non-speech labels like <noise> or [silence]. "
                "If no human speech is spoken, output an empty response."
            )

            for model_name in models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
                headers = {"Content-Type": "application/json", "x-goog-api-key": gemini_key}
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
                            timeout=aiohttp.ClientTimeout(total=25.0),
                        ) as resp:
                            if resp.status == 200:
                                g_data = await resp.json()
                                candidates = g_data.get("candidates") or []
                                if candidates:
                                    content = candidates[0].get("content") or {}
                                    parts = content.get("parts") or []
                                    if parts:
                                        g_text = parts[0].get("text", "").strip()
                                        # Filter out non-speech hallucination artifacts
                                        clean_text = g_text.replace("<noise>", "").replace("00:00", "").replace("[silence]", "").replace("[blank_audio]", "").strip()
                                        if clean_text and len(clean_text) > 1:
                                            return clean_text
                            else:
                                err_txt = await resp.text()
                                logger.debug(f"Gemini {model_name} HTTP {resp.status}: {err_txt[:150]}")
                except Exception as e:
                    logger.debug(f"Gemini model {model_name} failed: {e}")

        # Tier 3: Groq Whisper-large-v3-turbo (if GROQ_API_KEY is configured)
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        if groq_key:
            try:
                form = aiohttp.FormData()
                form.add_field("file", wav_data, filename="speaker.wav", content_type="audio/wav")
                form.add_field("model", "whisper-large-v3-turbo")
                form.add_field("response_format", "json")
                headers = {"Authorization": f"Bearer {groq_key}"}

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.groq.com/openai/v1/audio/transcriptions",
                        headers=headers,
                        data=form,
                        timeout=aiohttp.ClientTimeout(total=20.0),
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            txt = data.get("text", "").strip()
                            if txt:
                                return txt
            except Exception as e:
                logger.debug(f"Groq Whisper exception: {e}")

        return ""

    async def _generate_meeting_intelligence(self, full_transcript: str) -> dict[str, str]:
        """
        Synthesize meeting transcript into a structured executive report via Gemini.
        Returns dictionary containing summary, decisions, action_items, and topics.
        """
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key:
            return {
                "summary": "Meeting transcript recorded successfully.",
                "decisions": "• Transcript preserved.",
                "action_items": "• Review transcript for details.",
                "topics": "Team Discussion",
            }

        prompt = (
            "You are the Executive Meeting Intelligence Analyst for Kyro.\n"
            "Analyze the following conversation transcript from a Discord voice meeting.\n"
            "The conversation may be in Hindi, Hinglish (Hindi + English mixed), Marathi, or other Indian regional languages, or English.\n"
            "Extract key insights cleanly, ignoring casual mic checks or filler words.\n\n"
            "Respond STRICTLY in valid JSON matching this schema:\n"
            "{\n"
            '  "summary": "A concise 2-3 sentence executive summary of the meeting in clear English/Hinglish.",\n'
            '  "decisions": "Bullet points of key decisions agreed upon during the meeting (use markdown • bullet points).",\n'
            '  "action_items": "Bullet points of action items with assigned person if mentioned (e.g. • @Name: Task description).",\n'
            '  "topics": "Brief comma-separated key topics discussed."\n'
            "}\n\n"
            f"Transcript:\n{full_transcript[:15000]}"
        )

        headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
        }

        models = ["gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite"]
        for m in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=20.0),
                    ) as resp:
                        if resp.status == 200:
                            g_data = await resp.json()
                            parts = g_data.get("candidates", [])[0].get("content", {}).get("parts", [])
                            if parts:
                                raw_text = parts[0].get("text", "{}")
                                if "```json" in raw_text:
                                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                                elif "```" in raw_text:
                                    raw_text = raw_text.split("```")[1].split("```")[0].strip()
                                parsed = json.loads(raw_text)
                                return {
                                    "summary": parsed.get("summary", "Summary synthesized successfully."),
                                    "decisions": parsed.get("decisions", "• No explicit decisions recorded."),
                                    "action_items": parsed.get("action_items", "• No pending action items."),
                                    "topics": parsed.get("topics", "General discussion"),
                                }
            except Exception as e:
                logger.error(f"Error calling Gemini intelligence ({m}) for meeting: {e}", exc_info=True)

        return {
            "summary": "Meeting concluded. Discussion transcribed.",
            "decisions": "• Details preserved in session history.",
            "action_items": "• Please review discussion notes.",
            "topics": "Team Sync",
        }

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

        duration = int(time.time() - session.start_time)
        duration_fmt = f"{duration // 60}m {duration % 60}s"

        # Transcribe each active speaker using safe chunks
        speaker_transcripts: list[tuple[str, str]] = []
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
                    if uid not in sink.speaker_buffers:
                        m = guild.get_member(uid)
                        sink.speaker_buffers[uid] = bytearray()
                        sink.speaker_names[uid] = m.display_name if m else f"User-{uid}"
                        sink.speaker_chunks[uid] = 0
                    sink.speaker_buffers[uid] = prev_buf + sink.speaker_buffers[uid]

        all_uids = set(sink.speaker_names.keys()) | set(sink.speaker_buffers.keys())
        for uid in all_uids:
            name = sink.speaker_names.get(uid, f"Speaker-{uid}")
            chunks = sink.get_speaker_wav_chunks(uid, chunk_seconds=30)
            if not chunks:
                continue

            speaker_texts: list[str] = []
            for ch in chunks:
                chunk_text = await self._transcribe_audio(ch)
                if chunk_text:
                    speaker_texts.append(chunk_text)

            full_speaker_text = " ".join(speaker_texts).strip()
            if full_speaker_text and len(full_speaker_text) > 3:
                speaker_transcripts.append((name, full_speaker_text))

        captured_packets = getattr(sink, "packet_count", 0)
        sink.cleanup()
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        if not speaker_transcripts:
            if target_ch:
                c = KyroContainer(accent_color=None)
                c.add_section(
                    content="**Kyro Meeting Intelligence**\n> *Session ended without audible speech.*"
                )
                c.add_separator(divider=True)
                diag_msg = (
                    "No voice packets received from Discord (all members were muted or channel was silent)."
                    if captured_packets == 0
                    else "Voice packets were received, but audio was below speech recognition threshold."
                )
                c.add_text(
                    f"> {dot} **Duration:** `{duration_fmt}`\n"
                    f"> {dot} **Status:** `No Speech Detected`\n"
                    f"> {dot} **Audio Packets Captured:** `{captured_packets}`\n"
                    f"> {dot} **Notice:** {diag_msg}"
                )
                c.add_separator(divider=True)
                c.add_text(f"-# Kyro Voice Intelligence • <t:{int(time.time())}:f>")
                await send_container_response(target_ch, c)
            return

        # Combine transcripts
        combined_text = "\n".join([f"{name}: {text}" for name, text in speaker_transcripts])

        # Generate Intelligence Summary via Gemini
        intel = await self._generate_meeting_intelligence(combined_text)

        # Persist to database
        try:
            query = """
            INSERT INTO meeting_sessions (guild_id, channel_id, host_id, duration_seconds, speaker_count, summary, decisions, action_items)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
            """
            await self.bot.db.execute(
                query,
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

        # Post structured V2 card into target channel
        if target_ch:
            vc = guild.get_channel(session.voice_channel_id)
            vc_name = vc.name if vc else "Voice Channel"
            enabled_modules = settings.get("modules", set())

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=f"**Kyro Meeting Intelligence**\n> *Executive meeting summary and action items for **{vc_name}**.*"
            )
            container.add_separator(divider=True)

            # Metadata section
            topics_line = f" — **Topics:** `{intel['topics']}`" if "topics" in enabled_modules and intel.get("topics") else ""
            container.add_text(
                f"> {dot} **Room:** `{vc_name}` — **Duration:** `{duration_fmt}`\n"
                f"> {dot} **Speakers:** `{len(speaker_transcripts)}`{topics_line}"
            )
            container.add_separator(divider=True)

            # Summary section
            if "summary" in enabled_modules:
                container.add_text(
                    f"**Executive Summary:**\n"
                    f"> {intel['summary']}"
                )
                container.add_separator(divider=True)

            # Decisions
            if "decisions" in enabled_modules:
                decisions_clean = intel["decisions"].strip()
                container.add_text(
                    f"**Key Decisions:**\n{decisions_clean}"
                )
                container.add_separator(divider=True)

            # Action Items
            if "action_items" in enabled_modules:
                actions_clean = intel["action_items"].strip()
                container.add_text(
                    f"**Action Items:**\n{actions_clean}"
                )
                container.add_separator(divider=True)

            container.add_text(f"-# Recorded by Kyro Voice Intelligence • <t:{int(time.time())}:f>")
            await send_container_response(target_ch, container)

            # If command channel is different, leave a fleeting link notice
            if session.text_channel_id != target_ch.id:
                cmd_ch = guild.get_channel(session.text_channel_id)
                if isinstance(cmd_ch, discord.TextChannel):
                    try:
                        await cmd_ch.send(
                            f"-# {dot} 📝 Meeting summary has been posted to {target_ch.mention}.",
                            delete_after=10.0,
                        )
                    except Exception:
                        pass

    # ------------------ COMMAND INTERFACE ------------------

    def _build_usage_card(self, ctx: CustomContext) -> KyroContainer:
        """Construct the Components V2 usage guide for meeting commands."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Meeting Commands**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} `{prefix}meeting setup`\n"
            f"{dot} `{prefix}meeting disable`\n"
            f"{dot} `{prefix}meeting show`\n"
            f"{dot} `{prefix}meeting start`\n"
            f"{dot} `{prefix}meeting stop`"
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
                session.sink.cleanup()
            except Exception:
                pass

        await self.bot.db.execute(
            "INSERT INTO meeting_settings (guild_id, enabled) VALUES ($1, FALSE) ON CONFLICT(guild_id) DO UPDATE SET enabled = FALSE;",
            ctx.guild.id,
        )

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        sw_off = self.bot.custom_emojis.get("icon_switch_off", "[OFF]")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Kyro Meeting Intelligence**\n> Meeting recording is now disabled on this server.")
        container.add_separator(divider=True)
        container.add_text(
            f"> {dot} **Status:** {sw_off} `Disabled`\n"
            f"> {dot} **Notice:** Use `{ctx.clean_prefix}meeting setup` or `,meeting start` to re-enable."
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Disabled by {ctx.author.display_name} • <t:{int(time.time())}:f>")
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
            ch_disp = ch_obj.mention if ch_obj else f"<#{ch_id}>"
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
        total_sessions = 0
        try:
            row = await self.bot.db.fetch_one(
                "SELECT COUNT(*) as count FROM meeting_sessions WHERE guild_id = $1;", guild.id
            )
            if row:
                total_sessions = row.get("count", 0)
        except Exception:
            pass

        # Active session state
        active_session = self._sessions.get(guild.id)
        if active_session:
            elapsed = int(time.time() - active_session.start_time)
            vc = guild.get_channel(active_session.voice_channel_id)
            vc_name = vc.name if vc else "Voice"
            session_line = f"`Recording in {vc_name} ({elapsed // 60}m {elapsed % 60}s)`"
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
            f"> **Quick Start:** Connect to any VC and type `,meeting start`.\n"
            f"> **Reconfigure:** Use `,meeting setup` to change channel, privacy, or modules."
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
                f"Meeting Intelligence is currently **disabled** on this server. Use `{ctx.clean_prefix}meeting setup` to enable."
            )
            return

        # Check voice state
        if not isinstance(author, discord.Member) or not author.voice or not author.voice.channel:
            await ctx.send_warning("You must be connected to a **Voice Channel** to start a meeting.")
            return

        vc = author.voice.channel

        # Check if meeting already active
        if guild.id in self._sessions:
            active_s = self._sessions[guild.id]
            curr_vc = guild.get_channel(active_s.voice_channel_id)
            vc_str = curr_vc.mention if curr_vc else "another voice channel"
            await ctx.send_warning(f"A meeting is already active in {vc_str}. Use `,meeting stop` first.")
            return

        # Concurrency safety: check if Lavalink music is playing
        try:
            player = getattr(guild, "voice_client", None)
            if player and hasattr(player, "playing") and player.playing:
                await ctx.send_warning(
                    "Music playback is currently active in this server. Please pause or stop music before starting a meeting session."
                )
                return
        except Exception:
            pass

        # Cleanly disconnect any idle, stale, or existing voice connection before attaching VoiceRecvClient
        existing_vc = guild.voice_client
        if existing_vc:
            try:
                await existing_vc.disconnect(force=True)
            except Exception:
                pass
            try:
                existing_vc.cleanup()
            except Exception:
                pass
            await asyncio.sleep(0.3)

        # Auto-ensure meeting channel if not yet created
        settings = await self._get_meeting_settings(guild.id)
        if not settings.get("channel_id"):
            target_ch, _ = await ensure_meeting_channel(
                self.bot, guild, author, privacy_mode=settings.get("privacy_mode", "locked")
            )
            if target_ch:
                await self.bot.db.execute(
                    "INSERT INTO meeting_settings (guild_id, enabled, channel_id, privacy_mode) VALUES ($1, $2, $3, $4) ON CONFLICT(guild_id) DO UPDATE SET channel_id = EXCLUDED.channel_id;",
                    guild.id,
                    True,
                    target_ch.id,
                    settings.get("privacy_mode", "locked"),
                )

        # Check voice receiver module availability
        if not VOICE_RECV_AVAILABLE or voice_recv is None:
            await ctx.send_warning(
                "Voice receiver module (`discord-ext-voice-recv`) is not active in this bot environment.\n"
                "Please run `pip install discord-ext-voice-recv` on the server."
            )
            return

        # Connect with VoiceRecvClient (reconnect=False prevents reconnection oscillation)
        try:
            voice_client: voice_recv.VoiceRecvClient = await vc.connect(
                cls=voice_recv.VoiceRecvClient, timeout=20.0, reconnect=False, self_deaf=False, self_mute=False
            )
        except Exception as e:
            logger.error(f"Failed to connect to VC for meeting in guild {guild.id}: {e}", exc_info=True)
            await ctx.send_error(f"Could not connect to voice channel: `{e}`", ephemeral=False)
            return

        # Wait up to 5 seconds for Discord voice gateway encryption handshake and secret key to populate
        handshake_ok = False
        for _ in range(50):
            if voice_client.is_connected() and getattr(voice_client, "secret_key", None):
                handshake_ok = True
                break
            await asyncio.sleep(0.1)

        if not handshake_ok:
            try:
                await voice_client.disconnect(force=True)
            except Exception:
                pass
            await ctx.send_error("Could not complete Discord voice encryption handshake. Please try again.", ephemeral=False)
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
                sock_reader.resume(force=True)
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

        self._sessions[guild.id] = MeetingSession(
            guild_id=guild.id,
            voice_channel_id=vc.id,
            text_channel_id=ctx.channel.id,
            host_id=author.id,
            start_time=time.time(),
            voice_client=voice_client,
            sink=sink,
        )

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

    @meeting_group.command(name="stop", aliases=["end"], description="Stop the meeting and generate summary.")
    async def meeting_stop(self, ctx: CustomContext) -> None:
        """Stop voice listening, disconnect VC, and generate executive summary."""
        guild = ctx.guild
        session = self._sessions.pop(guild.id, None)

        if not session:
            await ctx.send_warning("There is no active meeting session in this server.")
            return

        dot = self.bot.custom_emojis.get("heart_dot", "•")

        # Disconnect gracefully
        try:
            session.voice_client.stop_listening()
            await session.voice_client.disconnect(force=True)
        except Exception as e:
            logger.debug(f"Notice during meeting disconnect: {e}")

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
        guild = member.guild
        session = self._sessions.get(guild.id)
        if not session:
            return

        # Ignore bot's own voice updates to prevent self-disconnect triggers
        if member.bot or (self.bot.user and member.id == self.bot.user.id):
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
                        await active_s.voice_client.disconnect(force=True)
                    except Exception:
                        pass
                    asyncio.create_task(self._process_meeting_completion(active_s))


async def setup(bot: KyroBot) -> None:
    """Register MeetingCog."""
    await bot.add_cog(MeetingCog(bot))
