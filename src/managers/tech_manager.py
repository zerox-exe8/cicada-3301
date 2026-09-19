"""
Kyro Discord Bot - Tech Intelligence & News Manager
Harvester engine connecting GitHub, Hacker News, Hugging Face, Cybersecurity feeds, and Kernel updates.
Provides deduplication, database persistence, and card generation.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING, Any, Optional

import aiohttp
from src.utils.containers import KyroContainer

if TYPE_CHECKING:
    from src.database.postgres import PostgresDatabase

logger = logging.getLogger("Kyro.Managers.TechNews")


def _clean_html(text: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _smart_truncate(text: str, max_len: int = 240) -> str:
    """Safely truncate text at word boundaries without cutting off words mid-sentence."""
    if not text or len(text) <= max_len:
        return text.strip() if text else ""
    truncated = text[:max_len]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return f"{truncated.rstrip(' ,;:-.')}..."


def canonicalize_url(raw_url: str) -> str:
    """Normalize URL by stripping tracking params (utm, ref, etc.), trailing slashes, and lowercasing domain."""
    if not raw_url:
        return ""
    try:
        from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
        parsed = urlparse(raw_url.strip())
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = parsed.path.rstrip("/")
        if not path:
            path = "/"

        drop_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "ref", "source", "fbclid", "gclid", "token", "_hsenc", "_hsmi", "mc_eid",
            "campaign", "feature", "tracking"
        }
        filtered_q = [(k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in drop_params]
        query = urlencode(filtered_q)
        return urlunparse((parsed.scheme.lower() or "https", netloc, path, "", query, ""))
    except Exception:
        return raw_url.strip().rstrip("/")


def compute_title_fingerprint(raw_title: str) -> str:
    """Compute normalized alphanumeric title fingerprint stripped of editorial prefixes and punctuation."""
    if not raw_title:
        return ""
    t = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", raw_title)
    t = re.sub(r"[^a-zA-Z0-9\s]", " ", t).lower()
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def clean_image_url(url: Optional[str]) -> Optional[str]:
    """Clean, unescape, and validate image URL for seamless Discord rendering."""
    if not url or not isinstance(url, str):
        return None
    cleaned = html.unescape(url.strip().strip("'\""))
    if not cleaned or not cleaned.startswith(("http://", "https://")):
        return None
    # Filter out tracking pixels, badges, avatars, or spacers
    lower = cleaned.lower()
    if any(k in lower for k in ["tracking", "spacer.gif", "1x1", "pixel.gif", "badge", "shields.io", "avatar"]):
        return None
    return cleaned


@dataclass
class TechStory:
    """Unified structure representing a verified tech intelligence story."""
    id: str
    source: str
    category: str  # 'github', 'tech', 'ai', 'security', 'systems', 'hardware'
    title: str
    summary: str
    url: str
    metadata: dict[str, Any] = field(default_factory=dict)
    published_at: float = field(default_factory=time.time)
    is_critical: bool = False
    owner_avatar: Optional[str] = None
    target_audience: str = ""
    use_case: str = ""
    license_info: str = ""
    maturity: str = ""
    what_is_inside: str = ""
    image_url: Optional[str] = None
    highlights: list[str] = field(default_factory=list)
    why_it_matters: str = ""
    title_hash: str = ""
    entity_hash: str = ""


CATEGORY_COLORS: dict[str, int] = {
    "github": 0x00A8FC,     # Electric Blue
    "tech": 0xF59E0B,       # Amber Gold
    "ai": 0xA855F7,         # Deep Violet
    "security": 0xEF4444,   # Alert Red
    "systems": 0x10B981,    # Emerald Green
    "hardware": 0xF97316,   # Silicon Orange
}

CATEGORY_BADGES: dict[str, str] = {
    "github": "Open Source",
    "tech": "Consumer Tech",
    "ai": "AI Research",
    "security": "Security Advisory",
    "systems": "Engineering Intel",
    "hardware": "Hardware & Silicon",
}

CRITICAL_KEYWORDS: list[str] = [
    r"\brce\b",
    r"zero-day",
    r"0-day",
    r"cve-\d{4}-\d+",
    r"active(?:ly)? exploit",
    r"critical vulnerability",
    r"unauthenticated remote",
    r"major outage",
    r"bgp leak",
    r"infrastructure outage",
    r"catastrophic",
]


def resolve_target_audience(topics: list[str], language: str) -> str:
    """Heuristic mapping from repo topics and primary language to target developer audience."""
    top_str = " ".join(topics).lower()
    if any(k in top_str for k in ["llm", "ai", "machine-learning", "deep-learning", "gpt", "rag", "embedding"]):
        return "AI Engineers & Model Builders"
    elif any(k in top_str for k in ["frontend", "react", "vue", "svelte", "css", "ui", "web"]):
        return "Frontend & Web Developers"
    elif any(k in top_str for k in ["docker", "k8s", "kubernetes", "cloud", "devops", "ci-cd", "infra"]):
        return "DevOps & Cloud Engineers"
    elif any(k in top_str for k in ["security", "cve", "exploit", "pentest", "auth", "crypto"]):
        return "Security Researchers & Pentesters"
    elif any(k in top_str for k in ["flutter", "react-native", "android", "ios", "swift", "kotlin"]):
        return "Mobile App Developers"
    elif any(k in top_str for k in ["database", "sql", "redis", "postgres", "distributed", "backend", "api"]):
        return "Backend & Database Architects"
    elif language:
        return f"{language} Developers & System Engineers"
    return "Software Engineers & Tech Enthusiasts"


def resolve_license(spdx_id: Optional[str]) -> str:
    """Classify open-source license into clear commercial permissibility terms."""
    if not spdx_id:
        return "Unspecified License"
    s = spdx_id.upper()
    if any(k in s for k in ["MIT", "APACHE", "BSD", "ISC"]):
        return f"{spdx_id} (Commercial Friendly)"
    elif any(k in s for k in ["GPL", "AGPL", "LGPL"]):
        return f"{spdx_id} (Open-Source Required)"
    return spdx_id


def resolve_maturity(stars: int, open_issues: int) -> str:
    """Assess project readiness from traction and issue metrics."""
    if stars >= 2500:
        return "Battle-Tested Production"
    elif stars >= 500:
        return "Active & Stable Community"
    elif stars >= 150:
        return "Trending Emerging Tool"
    return "Early Prototype"


async def validate_url_live(session: aiohttp.ClientSession, url: str) -> bool:
    """Pre-flight verification: ensure link returns HTTP 200/300 before publishing."""
    try:
        async with session.head(url, timeout=aiohttp.ClientTimeout(total=2.5), allow_redirects=True) as resp:
            return resp.status < 400
    except Exception:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=2.5), allow_redirects=True) as resp:
                return resp.status < 400
        except Exception:
            return False


async def analyze_with_gemini(
    session: aiohttp.ClientSession,
    title: str,
    raw_context: str,
    source_type: str = "technology article",
) -> Optional[dict[str, Any]]:
    """Use Gemini intelligence to filter spam/memes and extract crisp, structured engineering explanations."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    prompt = (
        f"You are a principal tech intelligence analyst briefing a community of developers, students, and tech enthusiasts.\n"
        f"Item Type: {source_type}\n"
        f"Title: {title}\n"
        f"Context/Details:\n{raw_context[:1400]}\n\n"
        f"Instructions:\n"
        f"1. 'is_meme': true if this is a troll, joke, empty spam, or low-effort post, otherwise false.\n"
        f"2. 'tldr': A direct, punchy 1-2 sentence executive explanation of what this actually is, what problem it solves, or what happened. No robotic marketing jargon.\n"
        f"3. 'highlights': A list of 2 to 3 concise bullet points with concrete technical specs, architecture, key capabilities, or numbers (e.g. '144 Armv9 cores', '3D chiplet packaging', 'Runs 100% locally with zero cloud dependencies', 'Free MIT License').\n"
        f"4. 'why_it_matters': Exactly 1 clear sentence explaining why someone should care, practical developer/user impact, or community consensus.\n"
        f"5. 'target_audience': Specific audience (e.g. 'Software Developers & Self-Hosters', 'Gamers & PC Enthusiasts', 'System Engineers').\n\n"
        f"Respond strictly in valid JSON matching this schema:\n"
        f'{{"is_meme": bool, "tldr": "string", "highlights": ["string", "string"], "why_it_matters": "string", "target_audience": "string"}}'
    )

    models_to_try = ["gemini-flash-lite-latest", "gemma-4-26b-a4b-it", "gemini-flash-latest"]
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
    }

    for model in models_to_try:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            async with session.post(endpoint, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            raw_txt = parts[0].get("text", "{}").strip()
                            if raw_txt.startswith("```"):
                                raw_txt = re.sub(r"^```(?:json)?\s*", "", raw_txt)
                                raw_txt = re.sub(r"\s*```$", "", raw_txt)
                            res_json = json.loads(raw_txt)
                            return res_json
                elif resp.status in (404, 503, 429):
                    continue
        except Exception as e:
            logger.debug(f"Notice during Gemini analysis with model {model}: {e}")
            continue

    return None


class TechNewsManager:
    """Central manager handling tech news ingestion, deduplication, and guild subscriptions."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        self._seen_hashes: set[str] = set()
        self._seen_title_hashes: set[str] = set()
        self._seen_entity_hashes: set[str] = set()
        self._guild_configs: dict[int, dict[str, Any]] = {}
        self._stories_by_id: dict[str, TechStory] = {}
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load recent seen hashes, title hashes, entity hashes, and guild subscriptions into fast memory."""
        try:
            # 1. Load active guild channel configurations
            rows = await self.db.fetch_all(
                "SELECT guild_id, channel_id, categories, thread_enabled, mode, alert_role_id, last_digest_date FROM guild_tech_news;"
            )
            async with self._lock:
                self._guild_configs = {
                    int(r["guild_id"]): {
                        "channel_id": int(r["channel_id"]),
                        "categories": str(r["categories"] or "all"),
                        "thread_enabled": bool(r.get("thread_enabled", False)),
                        "mode": str(r.get("mode") or "live"),
                        "alert_role_id": int(r["alert_role_id"]) if r.get("alert_role_id") else None,
                        "last_digest_date": str(r.get("last_digest_date") or ""),
                    }
                    for r in rows
                }

            # 2. Load recent dispatched article hashes, title hashes, and entity hashes (up to 50,000 items)
            hash_rows = await self.db.fetch_all(
                "SELECT article_hash, title_hash, entity_hash FROM tech_news_history ORDER BY dispatched_at DESC LIMIT 50000;"
            )
            async with self._lock:
                self._seen_hashes = {str(r["article_hash"]) for r in hash_rows if r.get("article_hash")}
                self._seen_title_hashes = {str(r["title_hash"]) for r in hash_rows if r.get("title_hash")}
                self._seen_entity_hashes = {str(r["entity_hash"]) for r in hash_rows if r.get("entity_hash")}

            logger.info(
                f"TechNewsManager loaded {len(self._guild_configs)} guild feed(s), {len(self._seen_hashes)} seen article hash(es), {len(self._seen_title_hashes)} title hash(es), and {len(self._seen_entity_hashes)} entity hash(es)."
            )
        except Exception as e:
            logger.error(f"Error loading TechNewsManager cache: {e}", exc_info=e)

    def register_story_memory(self, story: TechStory) -> None:
        """Cache a story in memory for instant bookmark lookup."""
        self._stories_by_id[story.id] = story
        # Keep memory bounds under 500 items
        if len(self._stories_by_id) > 500:
            oldest_keys = list(self._stories_by_id.keys())[:100]
            for k in oldest_keys:
                self._stories_by_id.pop(k, None)

    def get_story(self, story_id: str) -> Optional[TechStory]:
        """Retrieve cached story by hash."""
        return self._stories_by_id.get(story_id)

    # -------------------------------------------------------------------------
    # Guild Configuration Operations
    # -------------------------------------------------------------------------
    async def set_channel(
        self,
        guild_id: int,
        channel_id: int,
        categories: str = "all",
        thread_enabled: bool = False,
    ) -> bool:
        """Bind or update a guild's tech news channel and preferences."""
        cat_clean = categories.strip().lower()
        query = """
        INSERT INTO guild_tech_news (guild_id, channel_id, categories, thread_enabled)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (guild_id) DO UPDATE
        SET channel_id = EXCLUDED.channel_id,
            categories = EXCLUDED.categories,
            thread_enabled = EXCLUDED.thread_enabled;
        """
        try:
            await self.db.execute(query, guild_id, channel_id, cat_clean, thread_enabled)
            async with self._lock:
                existing = self._guild_configs.get(guild_id, {})
                self._guild_configs[guild_id] = {
                    "channel_id": channel_id,
                    "categories": cat_clean,
                    "thread_enabled": thread_enabled,
                    "mode": existing.get("mode", "live"),
                    "alert_role_id": existing.get("alert_role_id"),
                    "last_digest_date": existing.get("last_digest_date", ""),
                }
            return True
        except Exception as e:
            logger.error(f"Failed to set tech news channel for guild {guild_id}: {e}", exc_info=e)
            return False

    async def set_mode(self, guild_id: int, mode: str) -> bool:
        """Set delivery mode: 'live' or 'digest'."""
        m = mode.strip().lower()
        if m not in {"live", "digest"}:
            m = "live"
        query = "UPDATE guild_tech_news SET mode = $1 WHERE guild_id = $2;"
        try:
            await self.db.execute(query, m, guild_id)
            async with self._lock:
                if guild_id in self._guild_configs:
                    self._guild_configs[guild_id]["mode"] = m
            return True
        except Exception as e:
            logger.error(f"Failed to set tech news mode for guild {guild_id}: {e}", exc_info=e)
            return False

    async def set_alert_role(self, guild_id: int, role_id: Optional[int]) -> bool:
        """Set or clear the priority alert role for critical threat broadcasts."""
        query = "UPDATE guild_tech_news SET alert_role_id = $1 WHERE guild_id = $2;"
        try:
            await self.db.execute(query, role_id, guild_id)
            async with self._lock:
                if guild_id in self._guild_configs:
                    self._guild_configs[guild_id]["alert_role_id"] = role_id
            return True
        except Exception as e:
            logger.error(f"Failed to set alert role for guild {guild_id}: {e}", exc_info=e)
            return False

    async def update_last_digest(self, guild_id: int, date_str: str) -> None:
        """Record the date of the latest dispatched morning digest."""
        query = "UPDATE guild_tech_news SET last_digest_date = $1 WHERE guild_id = $2;"
        try:
            await self.db.execute(query, date_str, guild_id)
            async with self._lock:
                if guild_id in self._guild_configs:
                    self._guild_configs[guild_id]["last_digest_date"] = date_str
        except Exception as e:
            logger.error(f"Failed to update last digest date for guild {guild_id}: {e}", exc_info=e)

    async def remove_channel(self, guild_id: int) -> bool:
        """Unbind and disable tech news broadcasting for a guild."""
        query = "DELETE FROM guild_tech_news WHERE guild_id = $1;"
        try:
            await self.db.execute(query, guild_id)
            async with self._lock:
                self._guild_configs.pop(guild_id, None)
            return True
        except Exception as e:
            logger.error(f"Failed to remove tech news channel for guild {guild_id}: {e}", exc_info=e)
            return False

    def get_config(self, guild_id: int) -> Optional[dict[str, Any]]:
        """Retrieve cached config for a guild."""
        return self._guild_configs.get(guild_id)

    def get_all_configs(self) -> dict[int, dict[str, Any]]:
        """Retrieve copy of all guild subscriptions."""
        return dict(self._guild_configs)

    def is_hash_seen(self, article: TechStory | str) -> bool:
        """Check if an article has already been dispatched by canonical URL hash, title fingerprint, or entity hash."""
        if isinstance(article, str):
            return article in self._seen_hashes or article in self._seen_title_hashes or article in self._seen_entity_hashes
        if article.id in self._seen_hashes:
            return True
        if article.title_hash and article.title_hash in self._seen_title_hashes:
            return True
        if article.entity_hash and article.entity_hash in self._seen_entity_hashes:
            return True
        return False

    async def mark_dispatched(self, stories: list[TechStory]) -> None:
        """Record dispatched stories in database and memory cache."""
        if not stories:
            return

        insert_query = """
        INSERT INTO tech_news_history (article_hash, source, category, title, url, is_critical, title_hash, entity_hash)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (article_hash) DO UPDATE
        SET is_critical = EXCLUDED.is_critical, title_hash = EXCLUDED.title_hash, entity_hash = EXCLUDED.entity_hash;
        """
        async with self._lock:
            for s in stories:
                self._seen_hashes.add(s.id)
                if s.title_hash:
                    self._seen_title_hashes.add(s.title_hash)
                if s.entity_hash:
                    self._seen_entity_hashes.add(s.entity_hash)

        try:
            for s in stories:
                await self.db.execute(insert_query, s.id, s.source, s.category, s.title, s.url, s.is_critical, s.title_hash, s.entity_hash)
        except Exception as e:
            logger.error(f"Failed to write dispatched tech news history: {e}", exc_info=e)

    # -------------------------------------------------------------------------
    # Ingestion Adapters (High-Signal Zero-Scraping Harvesters)
    # -------------------------------------------------------------------------
    async def _harvest_github(self, session: aiohttp.ClientSession, limit: int = 6) -> list[TechStory]:
        """Harvest top trending open-source repositories created recently."""
        stories: list[TechStory] = []
        since_date = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")
        url = f"https://api.github.com/search/repositories?q=created:>{since_date}+stars:>40&sort=stars&order=desc&per_page=30"
        headers = {"User-Agent": "Kyro-TechPulse/1.0", "Accept": "application/vnd.github.v3+json"}
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("items", []):
                        full_name = item.get("full_name")
                        link = item.get("html_url")
                        if not full_name or not link:
                            continue

                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(full_name)
                        entity_h = hashlib.sha256(f"github:{full_name.lower()}".encode()).hexdigest()

                        if story_id in self._seen_hashes or title_h in self._seen_title_hashes or entity_h in self._seen_entity_hashes:
                            continue

                        raw_desc = (item.get("description") or "").strip()
                        desc = _clean_html(raw_desc) if raw_desc else ""

                        # Fetch author's actual README introductory context for real technical explanation
                        readme_summary = ""
                        try:
                            readme_url = f"https://raw.githubusercontent.com/{full_name}/HEAD/README.md"
                            async with session.get(readme_url, timeout=aiohttp.ClientTimeout(total=2.0)) as r_resp:
                                if r_resp.status == 200:
                                    r_text = await r_resp.text()
                                    clean_md = re.sub(r'\[!\[.*?\]\(.*?\)\]\(.*?\)', '', r_text)
                                    clean_md = re.sub(r'!\[.*?\]\(.*?\)', '', clean_md)
                                    clean_md = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', clean_md)
                                    clean_md = re.sub(r'#+\s*', '', clean_md)
                                    clean_md = re.sub(r'<.*?>', '', clean_md)
                                    clean_md = re.sub(r'```.*?```', '', clean_md, flags=re.DOTALL)
                                    for line in clean_md.split('\n'):
                                        l_str = line.strip()
                                        if len(l_str) > 35 and not l_str.startswith(('---', '===', '>', '|', '*')):
                                            if not any(k in l_str.lower() for k in ['license', 'badge', 'install', 'npm', 'pip']):
                                                readme_summary = l_str
                                                break
                        except Exception:
                            pass

                        # Pre-filter out obvious meme/joke repos
                        combined_raw = f"{desc} {readme_summary}".lower()
                        if any(k in combined_raw for k in ["star the repo", "star this repo", "sucks ass", "sucks butt", "shitpost", "for the memes"]):
                            logger.info(f"Filtered meme/joke repository: {full_name}")
                            continue

                        stars = item.get("stargazers_count", 0)
                        lang = item.get("language") or "General"
                        forks = item.get("forks_count", 0)
                        open_issues = item.get("open_issues_count", 0)

                        owner = item.get("owner") or {}
                        owner_avatar = owner.get("avatar_url")
                        topics = item.get("topics") or []
                        license_dict = item.get("license") or {}
                        spdx_id = license_dict.get("spdx_id") if isinstance(license_dict, dict) else None

                        license_info = resolve_license(spdx_id)
                        maturity = resolve_maturity(stars, open_issues)
                        image_url = f"https://opengraph.githubassets.com/1/{full_name}"

                        # Deep AI Intelligence Analysis
                        what_is_inside = ""
                        target_aud = resolve_target_audience(topics, lang)
                        final_summary = desc
                        highlights: list[str] = []
                        why_it_matters = ""

                        ai_intel = await analyze_with_gemini(
                            session,
                            full_name,
                            f"{desc}\n{readme_summary}",
                            source_type="open-source repository"
                        )
                        if ai_intel:
                            if ai_intel.get("is_meme"):
                                logger.info(f"Gemini flagged meme/joke repository, discarding: {full_name}")
                                continue
                            if ai_intel.get("tldr"):
                                final_summary = ai_intel["tldr"]
                            elif ai_intel.get("what_it_does"):
                                final_summary = ai_intel["what_it_does"]

                            if isinstance(ai_intel.get("highlights"), list):
                                highlights = [str(h).strip() for h in ai_intel["highlights"] if str(h).strip()]

                            if ai_intel.get("why_it_matters"):
                                why_it_matters = str(ai_intel["why_it_matters"]).strip()

                            if ai_intel.get("target_audience"):
                                target_aud = ai_intel["target_audience"]
                        else:
                            # Heuristic fallback if AI unavailable
                            if readme_summary and readme_summary.lower() != desc.lower():
                                final_summary = _smart_truncate(f"{desc} • {readme_summary}", 300) if desc else _smart_truncate(readme_summary, 300)
                            elif not final_summary:
                                final_summary = f"{full_name} open-source implementation and development toolkit."

                        story_obj = TechStory(
                            id=story_id,
                            source="GitHub",
                            category="github",
                            title=f"{full_name}",
                            summary=_smart_truncate(final_summary, 320),
                            url=canon_url,
                            metadata={"stars": stars, "language": lang, "forks": forks, "topics": topics[:4]},
                            owner_avatar=owner_avatar,
                            target_audience=target_aud,
                            license_info=license_info,
                            maturity=maturity,
                            what_is_inside=what_is_inside,
                            image_url=image_url,
                            highlights=highlights,
                            why_it_matters=why_it_matters,
                            title_hash=title_h,
                            entity_hash=entity_h,
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
                        if len(stories) >= limit:
                            break
        except Exception as e:
            logger.debug(f"Notice harvesting GitHub: {e}")
        return stories

    async def _harvest_hackernews(self, session: aiohttp.ClientSession, limit: int = 6) -> list[TechStory]:
        """Harvest top trending engineering and systems architecture stories from Hacker News. Firebase API with real article context."""
        stories: list[TechStory] = []
        top_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        try:
            async with session.get(top_url) as resp:
                if resp.status == 200:
                    ids = (await resp.json())[:30]
                    for item_id in ids:
                        detail_url = f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json"
                        async with session.get(detail_url) as d_resp:
                            if d_resp.status == 200:
                                data = await d_resp.json()
                                if not data or data.get("type") != "story":
                                    continue
                                title = data.get("title", "")
                                link = data.get("url")
                                score = data.get("score", 0)
                                if not link or score < 60:
                                    continue

                                canon_url = canonicalize_url(link)
                                story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                                title_h = compute_title_fingerprint(title)
                                entity_h = hashlib.sha256(f"tech:{title_h[:24]}".encode()).hexdigest()

                                if story_id in self._seen_hashes or title_h in self._seen_title_hashes or entity_h in self._seen_entity_hashes:
                                    continue

                                # Fetch real OpenGraph/meta description and image from destination article
                                real_summary = ""
                                article_img = None
                                try:
                                    art_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Kyro-Reader/1.0"}
                                    async with session.get(link, headers=art_headers, timeout=aiohttp.ClientTimeout(total=3.0)) as art_resp:
                                        if art_resp.status == 200:
                                            raw_body = await art_resp.text()
                                            m_desc = re.search(r'<meta\s+(?:property|name)=[\'"](?:og:description|description)[\'"]\s+content=[\'"](.*?)[\'"]', raw_body, re.I)
                                            if not m_desc:
                                                m_desc = re.search(r'<meta\s+content=[\'"](.*?)[\'"]\s+(?:property|name)=[\'"](?:og:description|description)[\'"]', raw_body, re.I)
                                            if m_desc:
                                                real_summary = _clean_html(m_desc.group(1)).strip()

                                            m_img = re.search(r'<meta\s+(?:property|name)=[\'"](?:og:image)[\'"]\s+content=[\'"](.*?)[\'"]', raw_body, re.I)
                                            if not m_img:
                                                m_img = re.search(r'<meta\s+content=[\'"](.*?)[\'"]\s+(?:property|name)=[\'"](?:og:image)[\'"]', raw_body, re.I)
                                            if m_img:
                                                article_img = m_img.group(1).strip()
                                except Exception:
                                    pass

                                # If no meta description, check if story has author text (e.g. Ask HN / Show HN)
                                if not real_summary and data.get("text"):
                                    real_summary = _clean_html(data["text"]).strip()

                                # Extract destination domain for clean attribution
                                domain = ""
                                try:
                                    from urllib.parse import urlparse
                                    domain = urlparse(link).netloc.replace("www.", "")
                                except Exception:
                                    pass

                                # Deep Gemini intelligence analysis
                                what_is_inside = ""
                                highlights: list[str] = []
                                why_it_matters = ""

                                ai_intel = await analyze_with_gemini(
                                    session,
                                    title,
                                    f"Headline: {title}\nSource: {domain}\nContext: {real_summary}",
                                    source_type="technical engineering news"
                                )
                                if ai_intel:
                                    if ai_intel.get("tldr"):
                                        real_summary = ai_intel["tldr"]
                                    elif ai_intel.get("what_it_does"):
                                        real_summary = ai_intel["what_it_does"]

                                    if isinstance(ai_intel.get("highlights"), list):
                                        highlights = [str(h).strip() for h in ai_intel["highlights"] if str(h).strip()]

                                    if ai_intel.get("why_it_matters"):
                                        why_it_matters = str(ai_intel["why_it_matters"]).strip()

                                    if ai_intel.get("what_is_inside"):
                                        what_is_inside = ai_intel["what_is_inside"]

                                if not real_summary or real_summary.strip().lower() == title.strip().lower():
                                    real_summary = f"Key systems engineering developments and architecture discussion regarding {title}."

                                is_crit = any(re.search(kw, title, re.IGNORECASE) for kw in CRITICAL_KEYWORDS)

                                story_obj = TechStory(
                                    id=story_id,
                                    source="Hacker News",
                                    category="systems",
                                    title=title,
                                    summary=_smart_truncate(real_summary, 320),
                                    url=canon_url,
                                    metadata={"score": score, "comments": data.get("descendants", 0), "domain": domain},
                                    is_critical=is_crit,
                                    what_is_inside=what_is_inside,
                                    image_url=article_img,
                                    highlights=highlights,
                                    why_it_matters=why_it_matters,
                                    title_hash=title_h,
                                    entity_hash=entity_h,
                                )
                                self.register_story_memory(story_obj)
                                stories.append(story_obj)
                                if len(stories) >= limit:
                                    break
        except Exception as e:
            logger.debug(f"Notice harvesting Hacker News: {e}")
        return stories

    async def _harvest_huggingface(self, session: aiohttp.ClientSession, limit: int = 6) -> list[TechStory]:
        """Harvest top daily AI research papers and weights from ArXiv and peer-reviewed releases."""
        stories: list[TechStory] = []
        url = "https://huggingface.co/api/papers"
        headers = {"User-Agent": "Kyro-TechPulse/1.0"}
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data:
                        paper = item.get("paper", {})
                        title = paper.get("title") or item.get("title")
                        paper_id = paper.get("id") or item.get("id")
                        if not title or not paper_id:
                            continue

                        link = f"https://arxiv.org/abs/{paper_id}"
                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(title)
                        entity_h = hashlib.sha256(f"arxiv:{paper_id.lower()}".encode()).hexdigest()

                        if story_id in self._seen_hashes or title_h in self._seen_title_hashes or entity_h in self._seen_entity_hashes:
                            continue

                        raw_summary = _clean_html(paper.get("summary") or "")
                        upvotes = paper.get("upvotes") or item.get("upvotes", 0)

                        # If summary is missing or too short, fetch real abstract from ArXiv
                        abstract = raw_summary
                        if not abstract or len(abstract) < 40:
                            try:
                                arxiv_url = f"https://arxiv.org/abs/{paper_id}"
                                async with session.get(arxiv_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=aiohttp.ClientTimeout(total=2.5)) as ax_resp:
                                    if ax_resp.status == 200:
                                        ax_html = await ax_resp.text()
                                        m_ax = re.search(r'class=[\'"]abstract[^\'"]*[\'"]>(.*?)</blockquote>', ax_html, re.DOTALL)
                                        if m_ax:
                                            abstract = re.sub(r'<.*?>', '', m_ax.group(1)).replace("Abstract:", "").strip()
                            except Exception:
                                pass

                        # AI Deep Analysis for real breakthrough context
                        what_is_inside = ""
                        highlights: list[str] = []
                        why_it_matters = ""
                        final_summary = _smart_truncate(abstract, 320) if abstract else f"Frontier AI paper analyzing novel machine learning methodologies in {title}."

                        ai_intel = await analyze_with_gemini(session, title, abstract or title, source_type="AI research paper")
                        if ai_intel:
                            if ai_intel.get("tldr"):
                                final_summary = ai_intel["tldr"]
                            elif ai_intel.get("what_it_does"):
                                final_summary = ai_intel["what_it_does"]

                            if isinstance(ai_intel.get("highlights"), list):
                                highlights = [str(h).strip() for h in ai_intel["highlights"] if str(h).strip()]

                            if ai_intel.get("why_it_matters"):
                                why_it_matters = str(ai_intel["why_it_matters"]).strip()

                            if ai_intel.get("what_is_inside"):
                                what_is_inside = ai_intel["what_is_inside"]

                        # Hugging Face provides official social thumbnail gradient
                        img_url = clean_image_url(item.get("thumbnailUrl")) or f"https://cdn-thumbnails.huggingface.co/social-thumbnails/papers/{paper_id}/gradient.png"

                        story_obj = TechStory(
                            id=story_id,
                            source="ArXiv & AI Frontier",
                            category="ai",
                            title=title,
                            summary=_smart_truncate(final_summary, 320),
                            url=canon_url,
                            metadata={"upvotes": upvotes, "paper_id": paper_id},
                            what_is_inside=what_is_inside,
                            image_url=img_url,
                            highlights=highlights,
                            why_it_matters=why_it_matters,
                            title_hash=title_h,
                            entity_hash=entity_h,
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
                        if len(stories) >= limit:
                            break
        except Exception as e:
            logger.debug(f"Notice harvesting Hugging Face: {e}")
        return stories

    async def _harvest_security_rss(self, session: aiohttp.ClientSession, limit: int = 6) -> list[TechStory]:
        """Harvest critical cybersecurity bulletins, zero-days, and scams from BleepingComputer and THN."""
        stories: list[TechStory] = []
        feed_url = "https://www.bleepingcomputer.com/feed/"
        headers = {"User-Agent": "Mozilla/5.0 Kyro-TechPulse/1.0"}
        try:
            async with session.get(feed_url, headers=headers) as resp:
                if resp.status == 200:
                    xml_data = await resp.text()
                    root = ET.fromstring(xml_data)
                    for item in root.findall(".//item"):
                        title = _clean_html(item.findtext("title") or "")
                        link = item.findtext("link") or ""
                        desc = _clean_html(item.findtext("description") or "")
                        if not title or not link:
                            continue

                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(title)
                        entity_h = hashlib.sha256(f"tech:{title_h[:24]}".encode()).hexdigest()

                        if story_id in self._seen_hashes or title_h in self._seen_title_hashes or entity_h in self._seen_entity_hashes:
                            continue

                        # Extract hero image from destination article
                        img_url = None
                        try:
                            async with session.get(link, headers=headers, timeout=aiohttp.ClientTimeout(total=2.5)) as art_resp:
                                if art_resp.status == 200:
                                    art_text = await art_resp.text()
                                    m_img = re.search(r'<meta\s+(?:property|name)=["\'](?:og:image)["\']\s+content=["\']([^"\']+)["\']', art_text, re.I)
                                    if not m_img:
                                        m_img = re.search(r'<meta\s+content=["\']([^"\']+)["\']\s+(?:property|name)=["\'](?:og:image)["\']', art_text, re.I)
                                    if m_img:
                                        img_url = m_img.group(1).strip()
                        except Exception:
                            pass

                        is_crit = any(re.search(kw, title, re.IGNORECASE) or re.search(kw, desc, re.IGNORECASE) for kw in CRITICAL_KEYWORDS)
                        highlights: list[str] = []
                        why_it_matters = ""
                        final_summary = desc

                        ai_intel = await analyze_with_gemini(session, title, desc, source_type="security bulletin")
                        if ai_intel:
                            if ai_intel.get("tldr"):
                                final_summary = ai_intel["tldr"]
                            if isinstance(ai_intel.get("highlights"), list):
                                highlights = [str(h).strip() for h in ai_intel["highlights"] if str(h).strip()]
                            if ai_intel.get("why_it_matters"):
                                why_it_matters = str(ai_intel["why_it_matters"]).strip()

                        story_obj = TechStory(
                            id=story_id,
                            source="BleepingComputer",
                            category="security",
                            title=title,
                            summary=_smart_truncate(final_summary, 300),
                            url=canon_url,
                            metadata={"severity": "Critical Exploit / Outage" if is_crit else "Security Advisory"},
                            is_critical=is_crit,
                            image_url=img_url,
                            highlights=highlights,
                            why_it_matters=why_it_matters,
                            title_hash=title_h,
                            entity_hash=entity_h,
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
                        if len(stories) >= limit:
                            break
        except Exception as e:
            logger.debug(f"Notice harvesting Security RSS: {e}")
        return stories

    async def _harvest_verge_tech(self, session: aiohttp.ClientSession, limit: int = 6) -> list[TechStory]:
        """Harvest mainstream consumer tech, gadgets, AI tools, and frontier culture from The Verge, Wired, and Engadget."""
        stories: list[TechStory] = []
        feeds = [
            ("The Verge", "https://www.theverge.com/rss/index.xml", "atom"),
            ("Wired", "https://www.wired.com/feed/rss", "rss"),
            ("Engadget", "https://www.engadget.com/rss.xml", "rss"),
        ]
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Kyro-TechPulse/1.0"}

        for source_name, feed_url, feed_type in feeds:
            try:
                async with session.get(feed_url, headers=headers, timeout=aiohttp.ClientTimeout(total=4.0)) as resp:
                    if resp.status != 200:
                        continue
                    xml_data = await resp.text()
                    root = ET.fromstring(xml_data)

                    items = root.findall(".//{http://www.w3.org/2005/Atom}entry") if feed_type == "atom" else root.findall(".//item")
                    for entry in items:
                        if feed_type == "atom":
                            title = _clean_html(entry.findtext("{http://www.w3.org/2005/Atom}title") or "")
                            link_elem = entry.find("{http://www.w3.org/2005/Atom}link")
                            link = link_elem.get("href") if link_elem is not None else ""
                            raw_content = entry.findtext("{http://www.w3.org/2005/Atom}content") or ""
                            desc = _clean_html(raw_content)
                            img_url = None
                            m_img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_content)
                            if m_img:
                                img_url = m_img.group(1).split("?")[0]
                        else:
                            title = _clean_html(entry.findtext("title") or "")
                            link = entry.findtext("link") or ""
                            desc = _clean_html(entry.findtext("description") or "")
                            img_url = None
                            thumb = entry.find("{http://search.yahoo.com/mrss/}thumbnail")
                            if thumb is not None and thumb.get("url"):
                                img_url = thumb.get("url")
                            if not img_url:
                                enc = entry.find("enclosure")
                                if enc is not None and enc.get("url"):
                                    img_url = enc.get("url")
                            if not img_url and desc:
                                m_img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', entry.findtext("description") or "")
                                if m_img:
                                    img_url = m_img.group(1).split("?")[0]

                        if not title or not link:
                            continue

                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(title)
                        entity_h = hashlib.sha256(f"tech:{title_h[:24]}".encode()).hexdigest()

                        if story_id in self._seen_hashes or title_h in self._seen_title_hashes or entity_h in self._seen_entity_hashes:
                            continue

                        # Avoid duplicates within this batch
                        if any(s.id == story_id or s.title_hash == title_h or s.entity_hash == entity_h for s in stories):
                            continue

                        highlights: list[str] = []
                        why_it_matters = ""
                        final_summary = desc

                        ai_intel = await analyze_with_gemini(session, title, desc[:1000], source_type="consumer technology article")
                        if ai_intel:
                            if ai_intel.get("tldr"):
                                final_summary = ai_intel["tldr"]
                            if isinstance(ai_intel.get("highlights"), list):
                                highlights = [str(h).strip() for h in ai_intel["highlights"] if str(h).strip()]
                            if ai_intel.get("why_it_matters"):
                                why_it_matters = str(ai_intel["why_it_matters"]).strip()

                        story_obj = TechStory(
                            id=story_id,
                            source=source_name,
                            category="tech",
                            title=title,
                            summary=_smart_truncate(final_summary, 320),
                            url=canon_url,
                            metadata={"tag": "Consumer & Culture"},
                            image_url=clean_image_url(img_url),
                            highlights=highlights,
                            why_it_matters=why_it_matters,
                            title_hash=title_h,
                            entity_hash=entity_h,
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
                        if len(stories) >= limit:
                            break
            except Exception as e:
                logger.debug(f"Notice harvesting {source_name}: {e}")
            if len(stories) >= limit:
                break
        return stories

    async def _harvest_phoronix(self, session: aiohttp.ClientSession, limit: int = 6) -> list[TechStory]:
        """Harvest silicon architecture, Linux kernel patches, and hardware updates."""
        stories: list[TechStory] = []
        feed_url = "https://www.phoronix.com/rss.php"
        headers = {"User-Agent": "Kyro-TechPulse/1.0"}
        try:
            async with session.get(feed_url, headers=headers) as resp:
                if resp.status == 200:
                    xml_data = await resp.text()
                    root = ET.fromstring(xml_data)
                    for item in root.findall(".//item"):
                        title = _clean_html(item.findtext("title") or "")
                        link = item.findtext("link") or ""
                        desc = _clean_html(item.findtext("description") or "")
                        if not title or not link:
                            continue

                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(title)
                        entity_h = hashlib.sha256(f"tech:{title_h[:24]}".encode()).hexdigest()

                        if story_id in self._seen_hashes or title_h in self._seen_title_hashes or entity_h in self._seen_entity_hashes:
                            continue

                        story_obj = TechStory(
                            id=story_id,
                            source="Phoronix",
                            category="hardware",
                            title=title,
                            summary=_smart_truncate(desc, 300),
                            url=canon_url,
                            metadata={"type": "Linux/Silicon"},
                            title_hash=title_h,
                            entity_hash=entity_h,
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
                        if len(stories) >= limit:
                            break
        except Exception as e:
            logger.debug(f"Notice harvesting Phoronix: {e}")
        return stories

    # -------------------------------------------------------------------------
    # High-Level Orchestrator
    # -------------------------------------------------------------------------
    async def harvest_all(self) -> list[TechStory]:
        """Execute concurrent harvest across all high-signal sources with in-batch cross-deduplication."""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            results = await asyncio.gather(
                self._harvest_github(session),
                self._harvest_hackernews(session),
                self._harvest_verge_tech(session),
                self._harvest_security_rss(session),
                self._harvest_huggingface(session),
                return_exceptions=True,
            )

        raw_stories: list[TechStory] = []
        for res in results:
            if isinstance(res, list):
                raw_stories.extend(res)

        # In-batch cross-source multi-layer deduplication
        deduped: list[TechStory] = []
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        seen_entities: set[str] = set()

        for s in raw_stories:
            if s.id in seen_urls or self.is_hash_seen(s):
                continue
            if s.title_hash and (s.title_hash in seen_titles or s.title_hash in self._seen_title_hashes):
                continue
            if s.entity_hash and (s.entity_hash in seen_entities or s.entity_hash in self._seen_entity_hashes):
                continue

            seen_urls.add(s.id)
            if s.title_hash:
                seen_titles.add(s.title_hash)
            if s.entity_hash:
                seen_entities.add(s.entity_hash)
            self.register_story_memory(s)
            deduped.append(s)

        return deduped

    async def harvest_balanced_batch(self, target_total: int = 10) -> list[TechStory]:
        """Harvest high-signal tech stories across all 5 key categories (AI, GitHub, Security, Consumer Tech, Systems/Hardware),
        enforcing strict multi-layer deduplication and balanced distribution (2 per category to total 10 items)."""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            ai_res, gh_res, sec_res, tech_res, hn_res, phor_res = await asyncio.gather(
                self._harvest_huggingface(session, limit=6),
                self._harvest_github(session, limit=6),
                self._harvest_security_rss(session, limit=6),
                self._harvest_verge_tech(session, limit=6),
                self._harvest_hackernews(session, limit=6),
                self._harvest_phoronix(session, limit=6),
                return_exceptions=True,
            )

        def _clean_pool(raw: Any) -> list[TechStory]:
            if not isinstance(raw, list):
                return []
            return [s for s in raw if isinstance(s, TechStory)]

        ai_items = _clean_pool(ai_res)
        gh_items = _clean_pool(gh_res)
        sec_items = _clean_pool(sec_res)
        tech_items = _clean_pool(tech_res)
        sys_items = _clean_pool(hn_res) + _clean_pool(phor_res)

        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        seen_entities: set[str] = set()

        def _filter_unseen(items: list[TechStory]) -> list[TechStory]:
            result: list[TechStory] = []
            for s in items:
                if s.id in seen_urls or self.is_hash_seen(s):
                    continue
                if s.title_hash and (s.title_hash in seen_titles or s.title_hash in self._seen_title_hashes):
                    continue
                if s.entity_hash and (s.entity_hash in seen_entities or s.entity_hash in self._seen_entity_hashes):
                    continue
                seen_urls.add(s.id)
                if s.title_hash:
                    seen_titles.add(s.title_hash)
                if s.entity_hash:
                    seen_entities.add(s.entity_hash)
                result.append(s)
            return result

        pools: dict[str, list[TechStory]] = {
            "ai": _filter_unseen(ai_items),
            "github": _filter_unseen(gh_items),
            "security": _filter_unseen(sec_items),
            "tech": _filter_unseen(tech_items),
            "systems": _filter_unseen(sys_items),
        }

        selected: list[TechStory] = []
        target_per_cat = max(1, target_total // len(pools))

        for cat_name, items in pools.items():
            chosen = items[:target_per_cat]
            selected.extend(chosen)
            pools[cat_name] = items[target_per_cat:]

        if len(selected) < target_total:
            remaining: list[TechStory] = []
            for items in pools.values():
                remaining.extend(items)

            def _score_key(s: TechStory) -> int:
                if s.is_critical:
                    return 1_000_000
                if s.category == "github":
                    return int(s.metadata.get("stars", 0))
                if s.category == "systems":
                    return int(s.metadata.get("score", 0))
                if s.category == "ai":
                    return int(s.metadata.get("upvotes", 0))
                return 100

            remaining.sort(key=_score_key, reverse=True)
            needed = target_total - len(selected)
            selected.extend(remaining[:needed])

        for s in selected:
            self.register_story_memory(s)

        return selected[:target_total]

    async def fetch_category(self, category: str, limit: int = 4) -> list[TechStory]:
        """Fetch fresh stories on-demand for a single category, filtering out seen items."""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=10)
        cat = category.strip().lower()

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            if cat == "github":
                res = await self._harvest_github(session)
            elif cat in {"tech", "gadgets"}:
                res = await self._harvest_verge_tech(session)
            elif cat == "ai":
                res = await self._harvest_huggingface(session)
            elif cat == "security":
                res = await self._harvest_security_rss(session)
            elif cat in {"systems", "hn"}:
                res = await self._harvest_hackernews(session)
            elif cat == "hardware":
                res = await self._harvest_phoronix(session)
            else:
                res = await self.harvest_all()

        unseen = [s for s in res if not self.is_hash_seen(s)]
        final_res = unseen[:limit] if unseen else res[:limit]
        for s in final_res:
            self.register_story_memory(s)
        return final_res

    # -------------------------------------------------------------------------
    # Components V2 Card Formatters
    # -------------------------------------------------------------------------
    @staticmethod
    def build_story_container(story: TechStory, dot: str = "•") -> KyroContainer:
        """Render a visually stunning, high-signal Components V2 intelligence card with full-width hero media."""
        # Color set to None for seamless, native dark mode blending (red only for critical alerts)
        accent = 0xFF0033 if story.is_critical else None
        container = KyroContainer(accent_color=accent)

        # Header Title and Subtitle
        if story.category == "github" and "/" in story.title:
            owner_part, repo_part = story.title.split("/", 1)
            title_line = f"### [{owner_part.strip()}](https://github.com/{owner_part.strip()}) / [{repo_part.strip()}]({story.url})"
            subtitle = "**GitHub Repository** • *Open Source*"
        elif story.category == "github":
            title_line = f"### [{story.title}]({story.url})"
            subtitle = "**GitHub Repository** • *Open Source*"
        else:
            title_line = f"### [{story.title}]({story.url})"
            badge = CATEGORY_BADGES.get(story.category, "Tech Intel")
            subtitle = f"**{badge}** • *{story.source}*"

        header_content = (
            f"{title_line}\n"
            f"> {subtitle}"
        )
        container.add_text(header_content)
        container.add_separator(divider=True)

        body_elements: list[str] = []

        # 1. AI Executive Brief
        if story.summary:
            body_elements.append(f"**AI Executive Brief:**\n{story.summary}")

        # 2. Key Highlights / Specs / Architecture
        if story.highlights:
            hl_text = "\n".join(f"> {dot} {h}" for h in story.highlights[:3])
            body_elements.append(f"**Key Highlights & Architecture:**\n{hl_text}")
        elif story.what_is_inside:
            body_elements.append(f"**Key Capabilities & Stack:**\n> {dot} {story.what_is_inside}")

        # 3. Why It Matters
        if story.why_it_matters:
            body_elements.append(f"**Why It Matters:**\n> {story.why_it_matters}")

        # 4. Audience / Topics
        if story.target_audience:
            body_elements.append(f"> *Engineered for {story.target_audience}*")

        topics = story.metadata.get("topics", [])
        if topics:
            body_elements.append(" ".join(f"`{t}`" for t in topics[:5]))

        # 5. Metadata Pill Row
        meta_items: list[str] = []
        if story.category == "github":
            lang = story.metadata.get("language", "General")
            stars = story.metadata.get("stars", 0)
            lic = story.license_info or "Open Source"
            mat = story.maturity or "Active Community"
            meta_items = [f"`{lang}`", f"`{stars:,}` stars", lic, f"`{mat}`"]
        elif story.category == "systems":
            score = story.metadata.get("score", 0)
            comments = story.metadata.get("comments", 0)
            domain = story.metadata.get("domain", "")
            meta_items = [f"**HN Score:** `{score}` pts", f"**Comments:** `{comments}`"]
            if domain:
                meta_items.append(f"**Source:** `{domain}`")
        elif story.category == "ai":
            upvotes = story.metadata.get("upvotes", 0)
            meta_items = ["**Citation:** ArXiv", f"**Community Traction:** `{upvotes}` upvotes"]
        elif story.category == "security":
            sev = story.metadata.get("severity", "Security Advisory")
            meta_items = [f"**Threat:** `{sev}`", f"**Source:** {story.source}"]
        elif story.category == "tech":
            tag = story.metadata.get("tag", "Consumer Tech")
            meta_items = [f"**Category:** `{tag}`", f"**Source:** {story.source}"]
        elif story.category == "hardware":
            meta_items = [f"**Focus:** `{story.metadata.get('type', 'Silicon')}`", f"**Source:** {story.source}"]

        if meta_items:
            body_elements.append(f" {dot} ".join(meta_items))

        container.add_text("\n\n".join(body_elements))

        # Full-Width Hero Media Gallery (Type 12 banner placed cleanly below text)
        valid_img = clean_image_url(story.image_url)
        if valid_img:
            container.add_media(valid_img)

        # Action row: Primary link button + Save to DM button
        primary_label = "Open Tool" if story.category == "github" else "Read Article"
        container.add_action_row([
            {
                "type": 2,
                "style": 5,
                "label": primary_label,
                "url": story.url,
            },
            {
                "type": 2,
                "style": 2,
                "label": "Save to DM",
                "custom_id": f"tech_bm:{story.id}",
            },
        ])

        return container

    @staticmethod
    def build_digest_container(stories: list[TechStory], date_str: str, dot: str = "•") -> KyroContainer:
        """Render a unified Morning 9:00 AM Tech Briefing container card."""
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**[DAILY TECH BRIEFING] Top Global Intel**\n"
                f"> Morning Digest for **{date_str}**"
            )
        )
        container.add_separator(divider=True)

        story_blocks: list[str] = []
        for s in stories[:4]:
            badge = CATEGORY_BADGES.get(s.category, "INTEL")
            story_blocks.append(
                f"{dot} **[{badge}] [{s.title}]({s.url})** ({s.source})\n"
                f"> {s.summary[:140]}..."
            )

        container.add_text("\n\n".join(story_blocks))
        container.add_separator(divider=True)
        container.add_text("-# Kyro Morning Intel • Published Daily at 9:00 AM")

        # Action row linking to top story
        if stories:
            container.add_action_row([{
                "type": 2,
                "style": 5,
                "label": "Read Top Breakthrough",
                "url": stories[0].url,
            }])

        return container
