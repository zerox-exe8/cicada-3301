"""
Kyro Discord Bot - AI Voice Recognition & Wake-Word Engine
Captures live voice audio in Discord voice channels, performs silence detection,
resamples to 16kHz mono PCM, and transcribes speech using SpeechRecognition
to execute hands-free voice commands ("Kyro play <song>", "Kyro pause", etc.).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Callable, Dict, Optional

import discord

try:
    import discord.ext.voice_recv as voice_recv
    HAS_VOICE_RECV = True
except ImportError:
    HAS_VOICE_RECV = False
    voice_recv = None

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False
    sr = None

try:
    import audioop
except ImportError:
    try:
        import audioop_lts as audioop
    except ImportError:
        audioop = None

if TYPE_CHECKING:
    from src.cogs.music._player import GuildPlayer

logger = logging.getLogger("Kyro.Music.VoiceListener")

# Wake-word command patterns
# e.g., "kyro play believer", "play kesariya", "kyro pause", "kyro skip", "kyro volume 80"
VOICE_CMD_PATTERNS = [
    (r"^(?:kyro\s+)?play\s+(.+)$", "play"),
    (r"^(?:kyro\s+)?pause$", "pause"),
    (r"^(?:kyro\s+)?resume$", "resume"),
    (r"^(?:kyro\s+)?skip$", "skip"),
    (r"^(?:kyro\s+)?stop$", "stop"),
    (r"^(?:kyro\s+)?volume\s+(\d+)$", "volume"),
]


class VoiceCommandSink(voice_recv.AudioSink if HAS_VOICE_RECV else object):
    """
    Real-Time Discord Voice Audio Sink with Silence Detection & Speech-to-Text Parsing.
    """

    def __init__(self, player: GuildPlayer, on_command_callback: Callable) -> None:
        super().__init__()
        self.player = player
        self.on_command_callback = on_command_callback
        self.bot = player.bot

        # Buffers: user_id -> bytearray of 48kHz 16-bit stereo PCM
        self._buffers: Dict[int, bytearray] = {}
        self._last_speech_time: Dict[int, float] = {}
        self._speech_start_time: Dict[int, float] = {}
        self._recognizer = sr.Recognizer() if HAS_SR else None

        self._stopped = False
        self._watcher_task: Optional[asyncio.Task] = None
        try:
            loop = player.bot.loop if player and player.bot else asyncio.get_running_loop()
            self._watcher_task = loop.create_task(self._silence_watcher())
        except Exception:
            try:
                self._watcher_task = asyncio.create_task(self._silence_watcher())
            except Exception:
                pass

    def wants_opus(self) -> bool:
        # We want decoded raw PCM for direct speech recognition
        return False

    def write(self, user: Optional[discord.Member | discord.User], data: voice_recv.VoiceData) -> None:
        """Receive real-time 20ms PCM audio packets from speaking users."""
        if self._stopped or not user or user.bot or not data.pcm:
            return

        now = time.time()
        uid = user.id

        if uid not in self._buffers:
            self._buffers[uid] = bytearray()
            self._speech_start_time[uid] = now

        self._buffers[uid].extend(data.pcm)
        self._last_speech_time[uid] = now

    async def _silence_watcher(self) -> None:
        """Periodically check for completed utterances (silence > 0.7s) and dispatch to STT."""
        while not self._stopped:
            try:
                await asyncio.sleep(0.2)
                now = time.time()
                finished_users = []

                for uid, last_time in list(self._last_speech_time.items()):
                    # If silence detected for 0.7 seconds after speaking
                    if (now - last_time) >= 0.7:
                        finished_users.append(uid)

                for uid in finished_users:
                    buf = self._buffers.pop(uid, bytearray())
                    start_t = self._speech_start_time.pop(uid, 0.0)
                    self._last_speech_time.pop(uid, None)

                    # Only process audio if duration >= 0.8s (avoids mic noise, coughing, breathing)
                    # 48000 Hz * 2 channels * 2 bytes/sample = 192,000 bytes per second
                    if len(buf) >= 153600:
                        asyncio.create_task(self._process_utterance(uid, bytes(buf)))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Silence watcher exception: {e}")

    async def _process_utterance(self, user_id: int, pcm_48k_stereo: bytes) -> None:
        """Resample PCM audio and perform speech-to-text in worker thread."""
        if not HAS_SR or not self._recognizer or not audioop:
            return

        user = self.player.guild.get_member(user_id)
        if not user:
            return

        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, self._transcribe, pcm_48k_stereo)
        if not text:
            return

        clean_text = text.lower().strip()
        logger.info(f"Voice Recognition [Guild {self.player.guild.id}]: User {user.name} said: '{clean_text}'")

        # Parse wake-word and voice intent
        for pattern, action in VOICE_CMD_PATTERNS:
            match = re.match(pattern, clean_text, re.IGNORECASE)
            if match:
                arg = match.group(1).strip() if match.groups() else ""
                logger.info(f"Voice Command Matched: action='{action}', arg='{arg}', user={user.name}")
                await self.on_command_callback(user, action, arg)
                return

    def _transcribe(self, pcm_48k_stereo: bytes) -> str | None:
        """Convert 48kHz stereo to 16kHz mono and transcribe via SpeechRecognition."""
        try:
            # 1. Convert stereo to mono
            mono_pcm = audioop.tomono(pcm_48k_stereo, 2, 0.5, 0.5)
            # 2. Downsample from 48000Hz to 16000Hz for speech recognition
            resampled_pcm, _ = audioop.ratecv(mono_pcm, 2, 1, 48000, 16000, None)

            audio_data = sr.AudioData(resampled_pcm, 16000, 2)
            # Recognize speech using Google's speech recognition engine (fast, cloud-grade)
            try:
                text = self._recognizer.recognize_google(audio_data, language="en-IN")
            except Exception:
                # Fallback to English (US)
                text = self._recognizer.recognize_google(audio_data, language="en-US")
            return text
        except (sr.UnknownValueError, sr.RequestError):
            return None
        except Exception as e:
            logger.debug(f"Transcription error: {e}")
            return None

    def cleanup(self) -> None:
        """Clean up background watcher and active audio buffers."""
        self._stopped = True
        if self._watcher_task and not self._watcher_task.done():
            self._watcher_task.cancel()
        self._buffers.clear()
        self._last_speech_time.clear()
        self._speech_start_time.clear()
