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


@dataclass
class TechStory:
    """Unified structure representing a verified tech intelligence story."""
    id: str
    source: str
    category: str  # 'github', 'ai', 'security', 'systems', 'hardware'
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


CATEGORY_COLORS: dict[str, int] = {
    "github": 0x00A8FC,     # Electric Blue
    "ai": 0x9945FF,         # Deep Violet
    "security": 0xFF3333,   # Alert Red
    "systems": 0x00FF66,    # Terminal Green
    "hardware": 0xFFA500,   # Silicon Amber
}

CATEGORY_BADGES: dict[str, str] = {
    "github": "GITHUB REPO",
    "ai": "AI RESEARCH",
    "security": "SECURITY ADVISORY",
    "systems": "ENGINEERING INTEL",
    "hardware": "SILICON & KERNEL",
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
    source_type: str = "repo",
) -> Optional[dict[str, Any]]:
    """Use Gemini intelligence to filter spam/memes and extract concrete engineering explanations."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    prompt = (
        f"You are a principal engineer analyzing an open-source technical item for a developer audience.\n"
        f"Item Type: {source_type}\n"
        f"Title: {title}\n"
        f"Context/README/Abstract:\n{raw_context[:1400]}\n\n"
        f"Instructions:\n"
        f"1. 'is_meme': true if this is a joke, troll, empty, opinion poll, or low-effort repo (e.g. 'if you think X sucks star this'), otherwise false.\n"
        f"2. 'what_it_does': One clear, concrete sentence explaining the exact functional mechanism or practical problem solved (no hype, no robotic marketing).\n"
        f"3. 'what_is_inside': Key architecture, supported tools, or core capabilities (short phrase or list).\n"
        f"4. 'target_audience': Specific engineer discipline this is built for (e.g. 'Backend & ML Engineers').\n\n"
        f"Respond strictly in valid JSON matching this schema:\n"
        f'{{"is_meme": bool, "what_it_does": "string", "what_is_inside": "string", "target_audience": "string"}}'
    )

    models_to_try = ["gemini-3-flash-preview", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-flash-latest"]
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
            async with session.post(endpoint, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
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
        self._guild_configs: dict[int, dict[str, Any]] = {}
        self._stories_by_id: dict[str, TechStory] = {}
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load recent seen hashes and guild subscriptions into fast memory."""
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

            # 2. Load recent dispatched article hashes (last 3,000 items)
            hash_rows = await self.db.fetch_all(
                "SELECT article_hash FROM tech_news_history ORDER BY dispatched_at DESC LIMIT 3000;"
            )
            async with self._lock:
                self._seen_hashes = {str(r["article_hash"]) for r in hash_rows}

            logger.info(
                f"TechNewsManager loaded {len(self._guild_configs)} guild feed(s) and {len(self._seen_hashes)} seen article hash(es)."
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

    def is_hash_seen(self, article_hash: str) -> bool:
        """Check if an article hash has already been dispatched."""
        return article_hash in self._seen_hashes

    async def mark_dispatched(self, stories: list[TechStory]) -> None:
        """Record dispatched stories in database and memory cache."""
        if not stories:
            return

        insert_query = """
        INSERT INTO tech_news_history (article_hash, source, category, title, url)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (article_hash) DO NOTHING;
        """
        async with self._lock:
            for s in stories:
                self._seen_hashes.add(s.id)

        try:
            for s in stories:
                await self.db.execute(insert_query, s.id, s.source, s.category, s.title, s.url)
        except Exception as e:
            logger.error(f"Failed to write dispatched tech news history: {e}", exc_info=e)

    # -------------------------------------------------------------------------
    # Ingestion Adapters (High-Signal Zero-Scraping Harvesters)
    # -------------------------------------------------------------------------
    async def _harvest_github(self, session: aiohttp.ClientSession) -> list[TechStory]:
        """Harvest top trending open-source repositories created recently."""
        stories: list[TechStory] = []
        since_date = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        url = f"https://api.github.com/search/repositories?q=created:>{since_date}+stars:>100&sort=stars&order=desc&per_page=6"
        headers = {"User-Agent": "Kyro-TechPulse/1.0", "Accept": "application/vnd.github.v3+json"}
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("items", []):
                        full_name = item.get("full_name")
                        link = item.get("html_url")
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

                        # Deep AI Intelligence Analysis
                        what_is_inside = ""
                        target_aud = resolve_target_audience(topics, lang)
                        final_summary = desc

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
                            if ai_intel.get("what_it_does"):
                                final_summary = ai_intel["what_it_does"]
                            if ai_intel.get("what_is_inside"):
                                what_is_inside = ai_intel["what_is_inside"]
                            if ai_intel.get("target_audience"):
                                target_aud = ai_intel["target_audience"]
                        else:
                            # Heuristic fallback if AI unavailable
                            if readme_summary and readme_summary.lower() != desc.lower():
                                final_summary = _smart_truncate(f"{desc} • {readme_summary}", 300) if desc else _smart_truncate(readme_summary, 300)
                            elif not final_summary:
                                final_summary = f"{full_name} open-source implementation and development toolkit."

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

                        story_id = hashlib.sha256(f"github:{link}".encode()).hexdigest()
                        story_obj = TechStory(
                            id=story_id,
                            source="GitHub",
                            category="github",
                            title=f"{full_name}",
                            summary=_smart_truncate(final_summary, 320),
                            url=link,
                            metadata={"stars": stars, "language": lang, "forks": forks, "topics": topics[:4]},
                            owner_avatar=owner_avatar,
                            target_audience=target_aud,
                            license_info=license_info,
                            maturity=maturity,
                            what_is_inside=what_is_inside,
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
        except Exception as e:
            logger.debug(f"Notice harvesting GitHub: {e}")
        return stories

    async def _harvest_hackernews(self, session: aiohttp.ClientSession) -> list[TechStory]:
        """Harvest high-score technical stories from Hacker News Firebase API with real article context."""
        stories: list[TechStory] = []
        top_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        try:
            async with session.get(top_url) as resp:
                if resp.status == 200:
                    ids = (await resp.json())[:12]
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
                                if not link or score < 80:
                                    continue

                                # Fetch real OpenGraph/meta description from destination article
                                real_summary = ""
                                try:
                                    art_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Kyro-Reader/1.0"}
                                    async with session.get(link, headers=art_headers, timeout=aiohttp.ClientTimeout(total=2.5)) as art_resp:
                                        if art_resp.status == 200:
                                            raw_body = await art_resp.text()
                                            m_desc = re.search(r'<meta\s+(?:property|name)=[\'"](?:og:description|description)[\'"]\s+content=[\'"](.*?)[\'"]', raw_body, re.I)
                                            if not m_desc:
                                                m_desc = re.search(r'<meta\s+content=[\'"](.*?)[\'"]\s+(?:property|name)=[\'"](?:og:description|description)[\'"]', raw_body, re.I)
                                            if m_desc:
                                                real_summary = _clean_html(m_desc.group(1)).strip()
                                except Exception:
                                    pass

                                # If no meta description, check if story has author text (e.g. Ask HN / Show HN)
                                if not real_summary and data.get("text"):
                                    real_summary = _clean_html(data["text"]).strip()

                                if not real_summary:
                                    real_summary = f"Technical analysis and engineering report regarding {title}."

                                is_crit = any(re.search(kw, title, re.IGNORECASE) for kw in CRITICAL_KEYWORDS)
                                story_id = hashlib.sha256(f"hn:{link}".encode()).hexdigest()
                                story_obj = TechStory(
                                    id=story_id,
                                    source="Hacker News",
                                    category="systems",
                                    title=title,
                                    summary=_smart_truncate(real_summary, 320),
                                    url=link,
                                    metadata={"score": score, "comments": data.get("descendants", 0)},
                                    is_critical=is_crit,
                                )
                                self.register_story_memory(story_obj)
                                stories.append(story_obj)
                                if len(stories) >= 3:
                                    break
        except Exception as e:
            logger.debug(f"Notice harvesting Hacker News: {e}")
        return stories

    async def _harvest_huggingface(self, session: aiohttp.ClientSession) -> list[TechStory]:
        """Harvest top daily AI research papers and weights from ArXiv and peer-reviewed releases."""
        stories: list[TechStory] = []
        url = "https://huggingface.co/api/papers"
        headers = {"User-Agent": "Kyro-TechPulse/1.0"}
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data[:6]:
                        paper = item.get("paper", {})
                        title = paper.get("title") or item.get("title")
                        paper_id = paper.get("id") or item.get("id")
                        raw_summary = _clean_html(paper.get("summary") or "")
                        upvotes = paper.get("upvotes") or item.get("upvotes", 0)
                        if not title or not paper_id:
                            continue

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
                        final_summary = _smart_truncate(abstract, 320) if abstract else f"Frontier AI paper analyzing novel machine learning methodologies in {title}."
                        ai_intel = await analyze_with_gemini(session, title, abstract or title, source_type="AI research paper")
                        if ai_intel:
                            if ai_intel.get("what_it_does"):
                                final_summary = ai_intel["what_it_does"]
                            if ai_intel.get("what_is_inside"):
                                what_is_inside = ai_intel["what_is_inside"]

                        link = f"https://arxiv.org/abs/{paper_id}"
                        story_id = hashlib.sha256(f"arxiv:{link}".encode()).hexdigest()
                        story_obj = TechStory(
                            id=story_id,
                            source="ArXiv & AI Frontier",
                            category="ai",
                            title=title,
                            summary=_smart_truncate(final_summary, 320),
                            url=link,
                            metadata={"upvotes": upvotes, "paper_id": paper_id},
                            what_is_inside=what_is_inside,
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
        except Exception as e:
            logger.debug(f"Notice harvesting Hugging Face: {e}")
        return stories

    async def _harvest_security_rss(self, session: aiohttp.ClientSession) -> list[TechStory]:
        """Harvest critical cybersecurity bulletins and zero-days."""
        stories: list[TechStory] = []
        feed_url = "https://feeds.feedburner.com/TheHackersNews"
        headers = {"User-Agent": "Kyro-TechPulse/1.0"}
        try:
            async with session.get(feed_url, headers=headers) as resp:
                if resp.status == 200:
                    xml_data = await resp.text()
                    root = ET.fromstring(xml_data)
                    for item in root.findall(".//item")[:4]:
                        title = _clean_html(item.findtext("title") or "")
                        link = item.findtext("link") or ""
                        desc = _clean_html(item.findtext("description") or "")
                        if not title or not link:
                            continue
                        is_crit = any(re.search(kw, title, re.IGNORECASE) or re.search(kw, desc, re.IGNORECASE) for kw in CRITICAL_KEYWORDS)
                        story_id = hashlib.sha256(f"thn:{link}".encode()).hexdigest()
                        story_obj = TechStory(
                            id=story_id,
                            source="The Hacker News",
                            category="security",
                            title=title,
                            summary=_smart_truncate(desc, 300),
                            url=link,
                            metadata={"severity": "Critical Exploit" if is_crit else "Security Advisory"},
                            is_critical=is_crit,
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
        except Exception as e:
            logger.debug(f"Notice harvesting Security RSS: {e}")
        return stories

    async def _harvest_phoronix(self, session: aiohttp.ClientSession) -> list[TechStory]:
        """Harvest silicon architecture, Linux kernel patches, and hardware updates."""
        stories: list[TechStory] = []
        feed_url = "https://www.phoronix.com/rss.php"
        headers = {"User-Agent": "Kyro-TechPulse/1.0"}
        try:
            async with session.get(feed_url, headers=headers) as resp:
                if resp.status == 200:
                    xml_data = await resp.text()
                    root = ET.fromstring(xml_data)
                    for item in root.findall(".//item")[:4]:
                        title = _clean_html(item.findtext("title") or "")
                        link = item.findtext("link") or ""
                        desc = _clean_html(item.findtext("description") or "")
                        if not title or not link:
                            continue
                        story_id = hashlib.sha256(f"phoronix:{link}".encode()).hexdigest()
                        story_obj = TechStory(
                            id=story_id,
                            source="Phoronix",
                            category="hardware",
                            title=title,
                            summary=_smart_truncate(desc, 300),
                            url=link,
                            metadata={"type": "Linux/Silicon"},
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
        except Exception as e:
            logger.debug(f"Notice harvesting Phoronix: {e}")
        return stories

    # -------------------------------------------------------------------------
    # High-Level Orchestrator
    # -------------------------------------------------------------------------
    async def harvest_all(self) -> list[TechStory]:
        """Execute concurrent harvest across all high-signal sources."""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            results = await asyncio.gather(
                self._harvest_github(session),
                self._harvest_hackernews(session),
                self._harvest_huggingface(session),
                self._harvest_security_rss(session),
                self._harvest_phoronix(session),
                return_exceptions=True,
            )

        all_stories: list[TechStory] = []
        for res in results:
            if isinstance(res, list):
                all_stories.extend(res)
                for s in res:
                    self.register_story_memory(s)
        return all_stories

    async def fetch_category(self, category: str, limit: int = 4) -> list[TechStory]:
        """Fetch fresh stories on-demand for a single category."""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=8)
        cat = category.strip().lower()

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            if cat == "github":
                res = (await self._harvest_github(session))[:limit]
            elif cat == "ai":
                res = (await self._harvest_huggingface(session))[:limit]
            elif cat == "security":
                res = (await self._harvest_security_rss(session))[:limit]
            elif cat == "systems":
                res = (await self._harvest_hackernews(session))[:limit]
            elif cat == "hardware":
                res = (await self._harvest_phoronix(session))[:limit]
            else:
                all_s = await self.harvest_all()
                res = all_s[:limit]

        for s in res:
            self.register_story_memory(s)
        return res

    # -------------------------------------------------------------------------
    # Components V2 Card Formatters
    # -------------------------------------------------------------------------
    @staticmethod
    def build_story_container(story: TechStory, dot: str = "•") -> KyroContainer:
        """Render an authentic, borderless Components V2 card matching GitHub and Nitro native style."""
        # Default accent (None) removes the harsh side-border, blending seamlessly like Nitro
        accent = 0xFF0033 if story.is_critical else None
        container = KyroContainer(accent_color=accent)

        # High-contrast white GitHub icon added by user in emoji2
        github_icon_url = "https://raw.githubusercontent.com/zerox-exe8/cicada-3301/main/assets/emoji2/github.png"

        if story.category == "github":
            accessory = {"type": 11, "media": {"url": github_icon_url}}

            if "/" in story.title:
                owner_part, repo_part = story.title.split("/", 1)
                title_line = f"**[{owner_part.strip()}](https://github.com/{owner_part.strip()}) / [{repo_part.strip()}]({story.url})**"
            else:
                title_line = f"**[{story.title}]({story.url})**"

            # Section header contains only Title & Subtitle next to 64px icon to avoid Discord line-clamp
            header_content = (
                f"{title_line}\n"
                f"> **GitHub Repository** • *Trending Open Source*"
            )
            container.add_section(content=header_content, accessory=accessory)
            container.add_separator(divider=True)

            body_elements: list[str] = []

            # Full-width technical overview
            if story.summary:
                body_elements.append(f"**Technical Overview:**\n{story.summary}")

            if story.what_is_inside:
                body_elements.append(f"**Key Capabilities & Stack:**\n> {story.what_is_inside}")

            # GitHub topic tags
            topics = story.metadata.get("topics", [])
            if topics:
                tags = " ".join(f"`{t}`" for t in topics[:5])
                body_elements.append(tags)

            if story.target_audience:
                body_elements.append(f"> *Engineered for {story.target_audience}*")

            # Native GitHub metadata row (Language, Stars, License, Maturity)
            lang = story.metadata.get("language", "General")
            stars = story.metadata.get("stars", 0)
            lic = story.license_info or "Open Source"
            mat = story.maturity or "Active Community"
            stats_line = f"{dot} `{lang}`  {dot} `{stars:,}` stars  {dot} {lic}  {dot} `{mat}`"
            body_elements.append(stats_line)

            container.add_text("\n\n".join(body_elements))
            container.add_separator(divider=True)
            container.add_text("-# GitHub Open Source Intelligence • Kyro Realtime Feed")

            primary_label = "View Repository"

        elif story.category == "ai":
            accessory = {"type": 11, "media": {"url": github_icon_url}}

            # Section header contains Title & Badge next to icon
            header_content = (
                f"**[{story.title}]({story.url})**\n"
                f"> **Frontier AI Research** • *Peer-Reviewed Pre-print*"
            )
            container.add_section(content=header_content, accessory=accessory)
            container.add_separator(divider=True)

            body_elements: list[str] = []

            # Full-width abstract and findings
            if story.summary:
                body_elements.append(f"**Abstract & Core Findings:**\n{story.summary}")

            if story.what_is_inside:
                body_elements.append(f"**Methodology & Key Architecture:**\n> {story.what_is_inside}")

            upvotes = story.metadata.get("upvotes", 0)
            body_elements.append(f"{dot} **Citation & Source:** ArXiv  {dot} **Community Traction:** `{upvotes}` upvotes")

            container.add_text("\n\n".join(body_elements))
            container.add_separator(divider=True)
            container.add_text("-# Frontier AI Intelligence • Kyro Realtime Feed")
            primary_label = "Read Research Paper"

        elif story.category == "security":
            header_content = (
                f"**[{story.title}]({story.url})**\n"
                f"> **Security Advisory** • *The Hacker News*"
            )
            accessory = {"type": 11, "media": {"url": "https://raw.githubusercontent.com/zerox-exe8/cicada-3301/main/assets/emoji2/icons_locked.png"}}
            container.add_section(content=header_content, accessory=accessory)
            container.add_separator(divider=True)

            sev = story.metadata.get("severity", "General")
            body_elements = [
                story.summary,
                f"{dot} **Threat Level:** `{sev}`  {dot} **Source:** The Hacker News"
            ]
            container.add_text("\n\n".join(body_elements))
            container.add_separator(divider=True)
            container.add_text("-# Cyber Threat Intelligence • Kyro Realtime Feed")
            primary_label = "Read Advisory"

        else:
            header_content = (
                f"**[{story.title}]({story.url})**\n"
                f"> **{story.source}** • *Technical Intelligence*"
            )
            if story.category == "hardware":
                accessory = {"type": 11, "media": {"url": "https://raw.githubusercontent.com/zerox-exe8/cicada-3301/main/assets/emoji2/icons_globe.png"}}
            else:
                accessory = {"type": 11, "media": {"url": github_icon_url}}
            container.add_section(content=header_content, accessory=accessory)
            container.add_separator(divider=True)

            meta_parts: list[str] = []
            if "score" in story.metadata:
                meta_parts.append(f"{dot} **HN Score:** `{story.metadata['score']}` pts")
            if "type" in story.metadata:
                meta_parts.append(f"{dot} **Focus:** `{story.metadata['type']}`")

            body_elements = [story.summary]
            if meta_parts:
                body_elements.append("  ".join(meta_parts))
            container.add_text("\n\n".join(body_elements))
            container.add_separator(divider=True)
            container.add_text(f"-# {story.source} • Kyro Realtime Feed")
            primary_label = "Read Article"

            body_elements = [story.summary]
            if meta_parts:
                body_elements.append("  ".join(meta_parts))

            container.add_text("\n\n".join(body_elements))
            container.add_separator(divider=True)
            container.add_text(f"-# {story.source} Intel • Kyro Realtime Feed")
            primary_label = "View Origin"

        # Action row: Primary link button + Save to DM interactive button
        container.add_action_row([
            {
                "type": 2,
                "style": 5,
                "label": primary_label,
                "url": story.url,
            },
            {
                "type": 2,
                "style": 2,  # Secondary grey
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
