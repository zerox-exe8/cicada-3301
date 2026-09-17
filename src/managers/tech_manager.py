"""
Kyro Discord Bot - Tech Intelligence & News Manager
Harvester engine connecting GitHub, Hacker News, Hugging Face, Cybersecurity feeds, and Kernel updates.
Provides deduplication, database persistence, and card generation.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
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


class TechNewsManager:
    """Central manager handling tech news ingestion, deduplication, and guild subscriptions."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        self._seen_hashes: set[str] = set()
        self._guild_configs: dict[int, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load recent seen hashes and guild subscriptions into fast memory."""
        try:
            # 1. Load active guild channel configurations
            rows = await self.db.fetch_all(
                "SELECT guild_id, channel_id, categories, thread_enabled FROM guild_tech_news;"
            )
            async with self._lock:
                self._guild_configs = {
                    int(r["guild_id"]): {
                        "channel_id": int(r["channel_id"]),
                        "categories": str(r["categories"] or "all"),
                        "thread_enabled": bool(r.get("thread_enabled", False)),
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
                self._guild_configs[guild_id] = {
                    "channel_id": channel_id,
                    "categories": cat_clean,
                    "thread_enabled": thread_enabled,
                }
            return True
        except Exception as e:
            logger.error(f"Failed to set tech news channel for guild {guild_id}: {e}", exc_info=e)
            return False

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
                        desc = _clean_html(item.get("description") or "Open-source development repository.")
                        stars = item.get("stargazers_count", 0)
                        lang = item.get("language") or "General"
                        forks = item.get("forks_count", 0)

                        story_id = hashlib.sha256(f"github:{link}".encode()).hexdigest()
                        stories.append(
                            TechStory(
                                id=story_id,
                                source="GitHub",
                                category="github",
                                title=f"{full_name}",
                                summary=desc[:220],
                                url=link,
                                metadata={"stars": stars, "language": lang, "forks": forks},
                            )
                        )
        except Exception as e:
            logger.debug(f"Notice harvesting GitHub: {e}")
        return stories

    async def _harvest_hackernews(self, session: aiohttp.ClientSession) -> list[TechStory]:
        """Harvest high-score technical stories from Hacker News Firebase API."""
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

                                story_id = hashlib.sha256(f"hn:{link}".encode()).hexdigest()
                                stories.append(
                                    TechStory(
                                        id=story_id,
                                        source="Hacker News",
                                        category="systems",
                                        title=title,
                                        summary=f"Community technical debate with {score} points and {data.get('descendants', 0)} comments on Y Combinator Hacker News.",
                                        url=link,
                                        metadata={"score": score, "comments": data.get("descendants", 0)},
                                    )
                                )
                                if len(stories) >= 3:
                                    break
        except Exception as e:
            logger.debug(f"Notice harvesting Hacker News: {e}")
        return stories

    async def _harvest_huggingface(self, session: aiohttp.ClientSession) -> list[TechStory]:
        """Harvest top daily AI research papers and weights from Hugging Face API."""
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
                        summary = _clean_html(paper.get("summary") or "AI frontier research paper.")
                        upvotes = paper.get("upvotes") or item.get("upvotes", 0)
                        if not title or not paper_id:
                            continue

                        link = f"https://huggingface.co/papers/{paper_id}"
                        story_id = hashlib.sha256(f"hf:{link}".encode()).hexdigest()
                        stories.append(
                            TechStory(
                                id=story_id,
                                source="Hugging Face",
                                category="ai",
                                title=title,
                                summary=summary[:220],
                                url=link,
                                metadata={"upvotes": upvotes, "paper_id": paper_id},
                            )
                        )
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
                        story_id = hashlib.sha256(f"thn:{link}".encode()).hexdigest()
                        stories.append(
                            TechStory(
                                id=story_id,
                                source="The Hacker News",
                                category="security",
                                title=title,
                                summary=desc[:220],
                                url=link,
                                metadata={"severity": "High/Critical"},
                            )
                        )
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
                        stories.append(
                            TechStory(
                                id=story_id,
                                source="Phoronix",
                                category="hardware",
                                title=title,
                                summary=desc[:220],
                                url=link,
                                metadata={"type": "Linux/Silicon"},
                            )
                        )
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
        return all_stories

    async def fetch_category(self, category: str, limit: int = 4) -> list[TechStory]:
        """Fetch fresh stories on-demand for a single category."""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=8)
        cat = category.strip().lower()

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            if cat == "github":
                return (await self._harvest_github(session))[:limit]
            elif cat == "ai":
                return (await self._harvest_huggingface(session))[:limit]
            elif cat == "security":
                return (await self._harvest_security_rss(session))[:limit]
            elif cat == "systems":
                return (await self._harvest_hackernews(session))[:limit]
            elif cat == "hardware":
                return (await self._harvest_phoronix(session))[:limit]
            else:
                all_s = await self.harvest_all()
                return all_s[:limit]

    # -------------------------------------------------------------------------
    # Components V2 Card Formatter
    # -------------------------------------------------------------------------
    @staticmethod
    def build_story_container(story: TechStory, dot: str = "•") -> KyroContainer:
        """Render a clean, high-signal Components V2 card for a technical story."""
        accent = CATEGORY_COLORS.get(story.category, 0x5865F2)
        badge = CATEGORY_BADGES.get(story.category, "TECH INTEL")

        container = KyroContainer(accent_color=accent)
        container.add_section(
            content=(
                f"**[{badge}] {story.title}**\n"
                f"> Source: **{story.source}**"
            )
        )
        container.add_separator(divider=True)

        # Body & Metrics
        meta_parts: list[str] = []
        if "stars" in story.metadata:
            meta_parts.append(f"{dot} **Stars:** `{story.metadata['stars']:,}`")
        if "language" in story.metadata:
            meta_parts.append(f"{dot} **Language:** `{story.metadata['language']}`")
        if "score" in story.metadata:
            meta_parts.append(f"{dot} **HN Score:** `{story.metadata['score']}` pts")
        if "upvotes" in story.metadata:
            meta_parts.append(f"{dot} **Upvotes:** `{story.metadata['upvotes']}`")
        if "severity" in story.metadata:
            meta_parts.append(f"{dot} **Advisory:** `{story.metadata['severity']}`")

        content_lines = [f"{story.summary}"]
        if meta_parts:
            content_lines.append(" • ".join(meta_parts))

        container.add_text("\n\n".join(content_lines))
        container.add_separator(divider=True)
        container.add_text("-# Kyro Tech Intelligence • Realtime Feed")

        # Action row link button directly to the origin URL
        container.add_action_row([{
            "type": 2,
            "style": 5,
            "label": "View Origin / Repository",
            "url": story.url,
        }])

        return container
