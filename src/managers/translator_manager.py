"""
Kyro Discord Bot - Translator Manager
High-performance translation engine supporting flag reaction detection, Google GTX, and Gemini intelligence fallback.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import urllib.parse
from typing import Any, Optional
import aiohttp

from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyro.Managers.Translator")

# Unicode regional indicator flag pairs to ISO language code mapping
FLAG_TO_LANG: dict[str, str] = {
    # Hindi / India
    "🇮🇳": "hi",
    # English
    "🇺🇸": "en",
    "🇬🇧": "en",
    "🇨🇦": "en",
    "🇦🇺": "en",
    # Spanish
    "🇪🇸": "es",
    "🇲🇽": "es",
    # French
    "🇫🇷": "fr",
    # German
    "🇩🇪": "de",
    # Japanese
    "🇯🇵": "ja",
    # Russian
    "🇷🇺": "ru",
    # Chinese
    "🇨🇳": "zh-CN",
    "🇹🇼": "zh-TW",
    # Arabic
    "🇦🇪": "ar",
    "🇸🇦": "ar",
    "🇪🇬": "ar",
    # Italian
    "🇮🇹": "it",
    # Portuguese
    "🇵🇹": "pt",
    "🇧🇷": "pt",
    # Korean
    "🇰🇷": "ko",
    # Turkish
    "🇹🇷": "tr",
    # Indonesian
    "🇮🇩": "id",
    # Dutch
    "🇳🇱": "nl",
    # Vietnamese
    "🇻🇳": "vi",
    # Thai
    "🇹🇭": "th",
    # Polish
    "🇵🇱": "pl",
    # Ukrainian
    "🇺🇦": "uk",
    # Swedish
    "🇸🇪": "sv",
}

LANGUAGE_NAMES: dict[str, str] = {
    "hi": "Hindi",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ja": "Japanese",
    "ru": "Russian",
    "zh-CN": "Chinese (Simplified)",
    "zh-TW": "Chinese (Traditional)",
    "ar": "Arabic",
    "it": "Italian",
    "pt": "Portuguese",
    "ko": "Korean",
    "tr": "Turkish",
    "id": "Indonesian",
    "nl": "Dutch",
    "vi": "Vietnamese",
    "th": "Thai",
    "pl": "Polish",
    "uk": "Ukrainian",
    "sv": "Swedish",
}


class TranslatorManager:
    """Manages translation engine, guild configuration, and caching."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        # guild_id -> settings dict
        self._guild_settings: dict[int, dict[str, Any]] = {}
        # hash(text + lang) -> (translated_text, detected_lang)
        self._translation_cache: dict[str, tuple[str, str]] = {}
        # debounce tracking set: f"{message_id}:{user_id}:{lang}"
        self._recent_reactions: set[str] = set()
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load guild translator settings from database."""
        try:
            rows = await self.db.fetch_all("SELECT * FROM guild_translator_settings;")
            async with self._lock:
                self._guild_settings.clear()
                for r in rows:
                    gid = int(r["guild_id"])
                    disabled = [int(c) for c in (r.get("disabled_channels") or [])]
                    self._guild_settings[gid] = {
                        "is_enabled": bool(r.get("is_enabled", True)),
                        "reaction_enabled": bool(r.get("reaction_enabled", True)),
                        "target_mode": str(r.get("target_mode") or "ephemeral"),
                        "disabled_channels": set(disabled),
                    }
            logger.info(f"Loaded {len(self._guild_settings)} guild translator configuration(s).")
        except Exception as e:
            logger.error(f"Failed to load translator cache: {e}", exc_info=e)

    def get_settings(self, guild_id: int) -> dict[str, Any]:
        """Get guild translator configuration with sensible defaults."""
        return self._guild_settings.get(
            guild_id,
            {
                "is_enabled": True,
                "reaction_enabled": True,
                "target_mode": "ephemeral",
                "disabled_channels": set(),
            },
        )

    def is_channel_enabled(self, guild_id: int, channel_id: int) -> bool:
        """Verify if translation features are allowed in the specified channel."""
        conf = self.get_settings(guild_id)
        if not conf["is_enabled"] or not conf["reaction_enabled"]:
            return False
        return channel_id not in conf["disabled_channels"]

    async def update_settings(
        self,
        guild_id: int,
        is_enabled: Optional[bool] = None,
        reaction_enabled: Optional[bool] = None,
        target_mode: Optional[str] = None,
        disabled_channels: Optional[set[int]] = None,
    ) -> None:
        """Update guild translation settings."""
        curr = self.get_settings(guild_id)
        new_enabled = is_enabled if is_enabled is not None else curr["is_enabled"]
        new_reaction = reaction_enabled if reaction_enabled is not None else curr["reaction_enabled"]
        new_mode = target_mode if target_mode is not None else curr["target_mode"]
        new_disabled = list(disabled_channels) if disabled_channels is not None else list(curr["disabled_channels"])

        query = """
        INSERT INTO guild_translator_settings (guild_id, is_enabled, reaction_enabled, target_mode, disabled_channels)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (guild_id) DO UPDATE SET
            is_enabled = EXCLUDED.is_enabled,
            reaction_enabled = EXCLUDED.reaction_enabled,
            target_mode = EXCLUDED.target_mode,
            disabled_channels = EXCLUDED.disabled_channels,
            updated_at = CURRENT_TIMESTAMP;
        """
        await self.db.execute(query, guild_id, new_enabled, new_reaction, new_mode, new_disabled)

        async with self._lock:
            self._guild_settings[guild_id] = {
                "is_enabled": new_enabled,
                "reaction_enabled": new_reaction,
                "target_mode": new_mode,
                "disabled_channels": set(new_disabled),
            }

    def is_debounce_active(self, message_id: int, user_id: int, target_lang: str) -> bool:
        """Prevent reaction spam for the same user, message, and target language."""
        key = f"{message_id}:{user_id}:{target_lang}"
        if key in self._recent_reactions:
            return True
        self._recent_reactions.add(key)
        # Auto clear key after 10 seconds
        asyncio.get_event_loop().call_later(10.0, self._recent_reactions.discard, key)
        return False

    async def translate(
        self,
        text: str,
        target_lang: str,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> tuple[str, str]:
        """
        Translate input text into target language code.
        Returns: (translated_text, detected_source_language)
        """
        clean_text = text.strip()
        if not clean_text:
            return ("", "unknown")

        cache_key = hashlib.sha256(f"{clean_text}:{target_lang}".encode("utf-8")).hexdigest()
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]

        # 1. Primary Engine: Google GTX Endpoint (Fast & Free)
        local_session = False
        if session is None:
            session = aiohttp.ClientSession()
            local_session = True

        try:
            encoded_query = urllib.parse.quote(clean_text)
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={encoded_query}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Kyro-Translator/1.0"}

            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # data format: [[["translated", "source", null, null]], null, "detected_lang"]
                    translated_chunks = []
                    detected_lang = "auto"
                    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                        for chunk in data[0]:
                            if isinstance(chunk, list) and len(chunk) > 0 and chunk[0]:
                                translated_chunks.append(str(chunk[0]))
                    if len(data) > 2 and isinstance(data[2], str):
                        detected_lang = data[2]

                    final_result = "".join(translated_chunks).strip()
                    if final_result:
                        res = (final_result, detected_lang)
                        self._translation_cache[cache_key] = res
                        return res
        except Exception as e:
            logger.debug(f"Notice during Google GTX translation: {e}")
        finally:
            if local_session:
                await session.close()

        # 2. Fallback Engine: Gemini Language Intelligence
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if api_key:
            try:
                target_name = LANGUAGE_NAMES.get(target_lang, target_lang)
                prompt = (
                    f"Translate the following message into natural, fluent {target_name}. "
                    f"Preserve all emojis, mentions, formatting, and tone. "
                    f"Respond strictly in valid JSON matching this schema: {{\"translated\": \"string\", \"detected\": \"string\"}}\n\n"
                    f"Message:\n{clean_text[:2000]}"
                )
                headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
                }
                async with aiohttp.ClientSession() as gemini_session:
                    async with gemini_session.post(
                        "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent",
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=5.0),
                    ) as g_resp:
                        if g_resp.status == 200:
                            g_data = await g_resp.json()
                            parts = g_data.get("candidates", [])[0].get("content", {}).get("parts", [])
                            if parts:
                                parsed = json.loads(parts[0].get("text", "{}"))
                                if parsed.get("translated"):
                                    res = (parsed["translated"], parsed.get("detected", "auto"))
                                    self._translation_cache[cache_key] = res
                                    return res
            except Exception as e:
                logger.debug(f"Notice during Gemini translation fallback: {e}")

        # If everything fails, return original text
        return (clean_text, "unknown")
