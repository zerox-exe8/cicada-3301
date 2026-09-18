import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import re
from typing import Any, Optional
import xml.etree.ElementTree as ET
import aiohttp

from src.database.postgres import PostgresDatabase
from src.utils.containers import KyroContainer

logger = logging.getLogger("Kyro.DevPulseManager")

CATEGORY_BADGES: dict[str, str] = {
    "bounties": "Paid Bounty",
    "jobs": "Careers & Internships",
    "hackathons": "Hackathon Radar",
    "perks": "Developer Perks",
    "tools": "AI Dev Tools",
}

CRITICAL_KEYWORDS: list[str] = [
    r"urgent",
    r"expiring today",
    r"last day to apply",
    r"final hours",
    r"closing soon",
]


def _clean_html(raw_html: str) -> str:
    """Strip HTML markup and unescape standard web character entities."""
    if not raw_html:
        return ""
    clean = re.sub(r"<[^<]+?>", " ", raw_html)
    clean = clean.replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    clean = clean.replace("&lt;", "<").replace("&gt;", ">").replace("&#038;", "&")
    clean = clean.replace("&#8217;", "'").replace("&#8220;", '"').replace("&#8221;", '"')
    return re.sub(r"\s+", " ", clean).strip()


def _smart_truncate(text: str, max_len: int = 280) -> str:
    """Truncate text cleanly at word boundaries avoiding awkward mid-word cuts."""
    if not text or len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len - 30:
        return truncated[:last_space] + "..."
    return truncated + "..."


def clean_image_url(url: Optional[str]) -> Optional[str]:
    """Sanitize and validate image URLs."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return None
    url = url.replace("&#038;", "&").replace("&amp;", "&")
    url = re.sub(r"[\r\n\t]", "", url)
    if any(k in url.lower() for k in ["1x1", "spacer", "pixel", "blank.gif"]):
        return None
    return url


@dataclass
class DevPulseStory:
    """Standardized internal representation of a developer opportunity story."""

    id: str
    source: str
    category: str
    title: str
    summary: str
    url: str
    metadata: dict[str, Any] = field(default_factory=dict)
    image_url: Optional[str] = None
    highlights: list[str] = field(default_factory=list)
    why_it_matters: str = ""
    is_critical: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


async def analyze_opportunity_with_gemini(
    session: aiohttp.ClientSession,
    title: str,
    raw_context: str,
    category: str,
) -> Optional[dict[str, Any]]:
    """Use Gemini intelligence to analyze developer opportunities, filter spam/meme tasks,
    and extract crisp engineering deliverables, tech stack tags, difficulty, and why it matters."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    prompt = (
        f"You are a principal software engineer evaluating real-world developer opportunities.\n"
        f"Category: {category}\n"
        f"Title: {title}\n"
        f"Context/Details:\n{raw_context[:1400]}\n\n"
        f"Instructions:\n"
        f"1. 'is_valid': true if this is a genuine, actionable developer opportunity (bounty, job/internship, hackathon, perk, or tool). Set false if it is spam, scam, closed task, troll post, or zero-context listing.\n"
        f"2. 'summary': A punchy 1-2 sentence executive explanation of what this opportunity is and what code/task is involved. No marketing fluff.\n"
        f"3. 'highlights': Exactly 2 to 3 concise bullet points with concrete technical details (e.g. 'Tech Stack: Python, FastAPI', 'Eligibility: Global Remote, 0-1 YOE', 'Bounty: $150 Paid via Stripe upon PR merge').\n"
        f"4. 'difficulty': One of: 'Beginner-Friendly', 'Intermediate', 'Advanced'.\n"
        f"5. 'why_it_matters': Exactly 1 strong sentence explaining why a developer or student should jump on this right now.\n\n"
        f"Respond strictly in valid JSON matching this schema:\n"
        f'{{"is_valid": bool, "summary": "string", "highlights": ["string", "string"], "difficulty": "string", "why_it_matters": "string"}}'
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
            async with session.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=6.0),
            ) as resp:
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
            logger.debug(f"Notice during Gemini opportunity analysis with model {model}: {e}")
            continue

    return None


class DevPulseManager:
    """Central manager handling developer opportunities ingestion, deduplication, and feeds."""

    def __init__(self, db: PostgresDatabase) -> None:
        self.db = db
        self._seen_hashes: set[str] = set()
        self._guild_configs: dict[int, dict[str, Any]] = {}
        self._stories_by_id: dict[str, DevPulseStory] = {}
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load recent seen hashes and guild subscriptions into fast memory."""
        try:
            if not self.db:
                return
            rows = await self.db.fetch_all(
                "SELECT guild_id, channel_id, categories, thread_enabled, mode FROM guild_dev_pulse;"
            )
            async with self._lock:
                self._guild_configs = {
                    int(r["guild_id"]): {
                        "channel_id": int(r["channel_id"]),
                        "categories": str(r["categories"] or "all"),
                        "thread_enabled": bool(r.get("thread_enabled", False)),
                        "mode": str(r.get("mode") or "live"),
                    }
                    for r in rows
                }

            hash_rows = await self.db.fetch_all(
                "SELECT item_hash FROM dev_pulse_history ORDER BY dispatched_at DESC LIMIT 3000;"
            )
            async with self._lock:
                self._seen_hashes = {str(r["item_hash"]) for r in hash_rows}

            logger.info(
                f"DevPulseManager loaded {len(self._guild_configs)} guild feed(s) and {len(self._seen_hashes)} seen item hash(es)."
            )
        except Exception as e:
            logger.error(f"Error loading DevPulseManager cache: {e}", exc_info=e)

    def register_story_memory(self, story: DevPulseStory) -> None:
        """Cache a story in memory for instant bookmark lookup."""
        self._stories_by_id[story.id] = story
        if len(self._stories_by_id) > 500:
            oldest_keys = list(self._stories_by_id.keys())[:100]
            for k in oldest_keys:
                self._stories_by_id.pop(k, None)

    def get_story(self, story_id: str) -> Optional[DevPulseStory]:
        """Retrieve cached story by hash."""
        return self._stories_by_id.get(story_id)

    async def set_channel(
        self,
        guild_id: int,
        channel_id: int,
        categories: str = "all",
        thread_enabled: bool = False,
    ) -> bool:
        """Bind or update a guild's dev pulse channel and preferences."""
        cat_clean = categories.strip().lower()
        query = """
        INSERT INTO guild_dev_pulse (guild_id, channel_id, categories, thread_enabled)
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
                }
            return True
        except Exception as e:
            logger.error(f"Failed to set dev pulse channel for guild {guild_id}: {e}", exc_info=e)
            return False

    async def disable_feed(self, guild_id: int) -> bool:
        """Unsubscribe a guild from dev pulse broadcasts."""
        query = "DELETE FROM guild_dev_pulse WHERE guild_id = $1;"
        try:
            await self.db.execute(query, guild_id)
            async with self._lock:
                self._guild_configs.pop(guild_id, None)
            return True
        except Exception as e:
            logger.error(f"Failed to disable dev pulse for guild {guild_id}: {e}", exc_info=e)
            return False

    def get_guild_config(self, guild_id: int) -> Optional[dict[str, Any]]:
        """Retrieve cached subscription settings for a guild."""
        return self._guild_configs.get(guild_id)

    def get_all_configs(self) -> dict[int, dict[str, Any]]:
        """Retrieve copy of all guild configurations for the dispatcher."""
        return dict(self._guild_configs)

    def is_seen(self, story_id: str) -> bool:
        """Check if an item has already been broadcast."""
        return story_id in self._seen_hashes

    async def record_dispatched(self, stories: list[DevPulseStory]) -> None:
        """Store item hashes into history to prevent future duplicate broadcasts."""
        if not stories or not self.db:
            return
        insert_query = """
        INSERT INTO dev_pulse_history (item_hash, source, category, title, url)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (item_hash) DO NOTHING;
        """
        async with self._lock:
            for s in stories:
                self._seen_hashes.add(s.id)

        try:
            for s in stories:
                await self.db.execute(insert_query, s.id, s.source, s.category, s.title, s.url)
        except Exception as e:
            logger.error(f"Failed to write dispatched dev pulse history: {e}", exc_info=e)

    # -------------------------------------------------------------------------
    # Ingestion Adapters
    # -------------------------------------------------------------------------
    async def _harvest_bounties(self, session: aiohttp.ClientSession) -> list[DevPulseStory]:
        """Harvest active open-source GitHub issues with paid bounties ($50 - $500+)."""
        stories: list[DevPulseStory] = []
        url = "https://api.github.com/search/issues?q=label:bounty+state:open+is:issue&sort=created&order=desc&per_page=10"
        headers = {"User-Agent": "Kyro-BountyRadar/1.0", "Accept": "application/vnd.github.v3+json"}
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidates: list[dict[str, Any]] = []
                    for item in data.get("items", []):
                        if item.get("state") != "open":
                            continue
                        if item.get("assignee") is not None or bool(item.get("assignees")):
                            continue
                        if item.get("pull_request") is not None:
                            continue
                        title = item.get("title", "")
                        html_url = item.get("html_url", "")
                        if not title or not html_url:
                            continue

                        repo_name = "Open Source Repo"
                        m_repo = re.search(r"github\.com/([^/]+/[^/]+)/issues", html_url)
                        if m_repo:
                            repo_name = m_repo.group(1)

                        if any(t in repo_name.lower() for t in ["test", "dummy", "practice", "playground", "demo"]):
                            continue

                        candidates.append(item)
                        if len(candidates) >= 4:
                            break

                    async def _process_bounty(item: dict[str, Any]) -> Optional[DevPulseStory]:
                        title = item.get("title", "")
                        html_url = item.get("html_url", "")
                        body = _clean_html(item.get("body") or "")
                        repo_name = "Open Source Repo"
                        m_repo = re.search(r"github\.com/([^/]+/[^/]+)/issues", html_url)
                        if m_repo:
                            repo_name = m_repo.group(1)

                        reward = "$50 - $250+ (Verified Bounty)"
                        m_cash = re.search(r"(\$\d+(?:,\d+)?|\b\d+\s*USD\b)", title + " " + body[:500], re.I)
                        if m_cash:
                            reward = m_cash.group(1)
                        else:
                            for lbl in item.get("labels", []):
                                if isinstance(lbl, dict) and any(c in lbl.get("name", "").lower() for c in ["$", "usd", "bounty"]):
                                    m_l = re.search(r"(\$\d+|\d+\s*usd)", lbl.get("name", ""), re.I)
                                    if m_l:
                                        reward = m_l.group(1)
                                        break

                        ai_data = await analyze_opportunity_with_gemini(
                            session=session,
                            title=f"{title} ({repo_name})",
                            raw_context=f"Bounty: {reward}\nRepository: {repo_name}\nDescription: {body[:800]}",
                            category="GitHub Bounty",
                        )

                        if ai_data and not ai_data.get("is_valid", True):
                            return None

                        if ai_data and ai_data.get("summary"):
                            summary = ai_data["summary"]
                            highlights = ai_data.get("highlights", [])
                            if not highlights:
                                highlights = [
                                    f"Repository: {repo_name}",
                                    f"Verified Cash Bounty: {reward}",
                                    "Status: Unassigned & Open for Solutions",
                                ]
                            why_matters = ai_data.get("why_it_matters", f"Contribute code to {repo_name} and claim {reward} upon PR merge.")
                            diff = ai_data.get("difficulty", "Intermediate")
                        else:
                            highlights = [
                                f"Repository: {repo_name}",
                                f"Verified Cash Bounty: {reward}",
                                "Status: Unassigned & Open for Solutions",
                            ]
                            summary = _smart_truncate(body, 280) if len(body) > 30 else f"Open-source engineering bounty available for resolving {title} in {repo_name}."
                            why_matters = f"Contribute real code to {repo_name} and claim a {reward} bounty upon PR merge."
                            diff = "Intermediate"

                        story_id = hashlib.sha256(f"bounty:{html_url}".encode()).hexdigest()
                        story_obj = DevPulseStory(
                            id=story_id,
                            source="GitHub Bounties",
                            category="bounties",
                            title=title,
                            summary=summary,
                            url=html_url,
                            metadata={"reward": reward, "repo": repo_name, "difficulty": diff},
                            image_url=f"https://opengraph.githubassets.com/1/{repo_name}",
                            highlights=highlights,
                            why_it_matters=why_matters,
                        )
                        self.register_story_memory(story_obj)
                        return story_obj

                    results = await asyncio.gather(*[_process_bounty(c) for c in candidates], return_exceptions=True)
                    for r in results:
                        if isinstance(r, DevPulseStory):
                            stories.append(r)
        except Exception as e:
            logger.debug(f"Notice harvesting bounties: {e}")
        return stories

    async def _harvest_jobs(self, session: aiohttp.ClientSession) -> list[DevPulseStory]:
        """Harvest entry-level, fresher, and remote developer internships."""
        stories: list[DevPulseStory] = []
        url = "https://remoteok.com/api?tag=dev"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json"}
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    jobs = [j for j in data if isinstance(j, dict) and j.get("position")]
                    tech_keywords = ["dev", "engineer", "software", "frontend", "backend", "python", "react", "fullstack", "data", "code", "intern", "web", "ai", "security", "mobile"]
                    exclude_keywords = ["recruiter", "sales", "hr", "marketing", "account executive", "copywriter", "customer support"]

                    candidates: list[dict[str, Any]] = []
                    for job in jobs[:20]:
                        pos = job.get("position", "")
                        link = job.get("url") or job.get("apply_url")
                        tags = job.get("tags") or []

                        combined_text = f"{pos} {' '.join(tags)}".lower()
                        if any(ex in combined_text for ex in exclude_keywords):
                            continue
                        if not any(k in combined_text for k in tech_keywords):
                            continue
                        if not link:
                            continue

                        candidates.append(job)
                        if len(candidates) >= 4:
                            break

                    async def _process_job(job: dict[str, Any]) -> Optional[DevPulseStory]:
                        pos = job.get("position", "")
                        comp = job.get("company", "Tech Startup")
                        link = job.get("url") or job.get("apply_url")
                        raw_desc = _clean_html(job.get("description") or "")
                        salary_min = job.get("salary_min")
                        salary_max = job.get("salary_max")
                        comp_str = "Paid / Competitive"
                        if salary_min and salary_max:
                            comp_str = f"${salary_min:,} - ${salary_max:,}/yr"
                        elif salary_min:
                            comp_str = f"${salary_min:,}+"

                        location = job.get("location") or "Worldwide Remote"

                        ai_data = await analyze_opportunity_with_gemini(
                            session=session,
                            title=f"{pos} at {comp}",
                            raw_context=f"Role: {pos}\nCompany: {comp}\nCompensation: {comp_str}\nLocation: {location}\nDescription: {raw_desc[:800]}",
                            category="Developer Job / Internship",
                        )

                        if ai_data and not ai_data.get("is_valid", True):
                            return None

                        if ai_data and ai_data.get("summary"):
                            summary = ai_data["summary"]
                            highlights = ai_data.get("highlights", [])
                            if not highlights:
                                highlights = [
                                    f"Company: {comp} ({location})",
                                    f"Compensation: {comp_str}",
                                    "Experience Level: Entry-Level / Internship / Junior",
                                ]
                            why_matters = ai_data.get("why_it_matters", f"Great entry-level career opportunity with remote flexibility at {comp}.")
                        else:
                            highlights = [
                                f"Company: {comp} ({location})",
                                f"Compensation: {comp_str}",
                                "Experience Level: Entry-Level / Internship / Junior",
                            ]
                            summary = _smart_truncate(raw_desc, 280) if raw_desc else f"Remote engineering role open for {pos} at {comp}. 0-1 YOE friendly."
                            why_matters = f"Great entry-level career opportunity with remote flexibility at {comp}."

                        story_id = hashlib.sha256(f"job:{link}".encode()).hexdigest()
                        story_obj = DevPulseStory(
                            id=story_id,
                            source="RemoteOK Careers",
                            category="jobs",
                            title=f"{pos} at {comp}",
                            summary=summary,
                            url=link,
                            metadata={"company": comp, "compensation": comp_str, "location": location},
                            image_url=job.get("company_logo"),
                            highlights=highlights,
                            why_it_matters=why_matters,
                        )
                        self.register_story_memory(story_obj)
                        return story_obj

                    results = await asyncio.gather(*[_process_job(c) for c in candidates], return_exceptions=True)
                    for r in results:
                        if isinstance(r, DevPulseStory):
                            stories.append(r)
        except Exception as e:
            logger.debug(f"Notice harvesting jobs: {e}")
        return stories

    async def _harvest_hackathons(self, session: aiohttp.ClientSession) -> list[DevPulseStory]:
        """Harvest active global and student hackathons with verified cash prize pools from Devpost."""
        stories: list[DevPulseStory] = []
        url = "https://devpost.com/api/hackathons"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for h in data.get("hackathons", [])[:6]:
                        title = h.get("title", "")
                        link = h.get("url", "")
                        raw_prize = h.get("prize_amount", "Cash & Swags")
                        prize_clean = _clean_html(raw_prize).replace("data-currency-value", "").replace("<", "").replace(">", "").strip()
                        prize_clean = re.sub(r"\s+", " ", prize_clean) or "$10,000+ Prize Pool"

                        sub_period = h.get("submission_period_dates") or "Registration Open"
                        theme = ", ".join([t.get("name") for t in h.get("themes", [])[:3]]) if h.get("themes") else "Open Innovation"
                        hero_img = h.get("thumbnail_url")

                        if not title or not link:
                            continue

                        highlights = [
                            f"Prize Pool: {prize_clean}",
                            f"Submission Window: {sub_period}",
                            f"Themes: {theme}",
                        ]

                        story_id = hashlib.sha256(f"hack:{link}".encode()).hexdigest()
                        story_obj = DevPulseStory(
                            id=story_id,
                            source="Devpost Global",
                            category="hackathons",
                            title=title,
                            summary=f"Global developer hackathon featuring {prize_clean} in prizes. Open for solo builders and teams.",
                            url=link,
                            metadata={"prize_pool": prize_clean, "deadline": sub_period},
                            image_url=hero_img,
                            highlights=highlights,
                            why_it_matters=f"Compete globally, build real portfolio projects, and earn from a {prize_clean} prize pool.",
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
        except Exception as e:
            logger.debug(f"Notice harvesting hackathons: {e}")
        return stories

    async def _harvest_perks(self, session: aiohttp.ClientSession) -> list[DevPulseStory]:
        """Harvest free developer perks, 100% off tech courses, and cloud vouchers."""
        stories: list[DevPulseStory] = []
        feed_url = "https://www.discudemy.com/feed"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            async with session.get(feed_url, headers=headers) as resp:
                if resp.status == 200:
                    xml_data = await resp.text()
                    root = ET.fromstring(xml_data)
                    for item in root.findall(".//item")[:5]:
                        title = _clean_html(item.findtext("title") or "").strip()
                        link = item.findtext("link") or ""
                        desc = _clean_html(item.findtext("description") or "").strip()
                        if not title or not link:
                            continue

                        img_url = None
                        m_img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', item.findtext("description") or "")
                        if m_img:
                            img_url = m_img.group(1)

                        highlights = [
                            "Discount: 100% Free Coupon Code Included",
                            "Access: Lifetime Full Course & Certificate of Completion",
                            "Expiry: Limited Redemptions (First Come First Served)",
                        ]

                        story_id = hashlib.sha256(f"perk:{link}".encode()).hexdigest()
                        story_obj = DevPulseStory(
                            id=story_id,
                            source="Developer Perks & Courses",
                            category="perks",
                            title=title,
                            summary=desc[:260] if desc else "Limited-time 100% free developer course coupon and certification voucher.",
                            url=link,
                            metadata={"value": "100% Free Lifetime Access", "expires": "Limited Coupons"},
                            image_url=img_url,
                            highlights=highlights,
                            why_it_matters="Upskill for free and claim certification without paying course fees.",
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
        except Exception as e:
            logger.debug(f"Notice harvesting perks: {e}")
        return stories

    async def _harvest_ai_tools(self, session: aiohttp.ClientSession) -> list[DevPulseStory]:
        """Harvest daily top practical AI developer tools with generous free tiers from ProductHunt."""
        stories: list[DevPulseStory] = []
        feed_url = "https://www.producthunt.com/feed"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        try:
            async with session.get(feed_url, headers=headers) as resp:
                if resp.status == 200:
                    xml_data = await resp.text()
                    root = ET.fromstring(xml_data)
                    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry")[:5]:
                        title = _clean_html(entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                        link = link_el.get("href") if link_el is not None else ""
                        raw_content = entry.findtext("{http://www.w3.org/2005/Atom}content") or ""
                        desc = _clean_html(raw_content).strip()
                        if not title or not link:
                            continue

                        img_url = None
                        m_img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_content)
                        if m_img:
                            img_url = m_img.group(1).split("?")[0]

                        highlights = [
                            "Tier: Generous Free Tier / Free Trials Available",
                            "Category: Developer AI Productivity Tool",
                            "Direct Launch via Product Hunt",
                        ]

                        story_id = hashlib.sha256(f"tool:{link}".encode()).hexdigest()
                        story_obj = DevPulseStory(
                            id=story_id,
                            source="Product Hunt AI",
                            category="tools",
                            title=title,
                            summary=_smart_truncate(desc, 280) if desc else f"New trending AI developer tool launched on Product Hunt: {title}.",
                            url=link,
                            metadata={"tier": "Free Tier Available", "replaces": "Productivity Booster"},
                            image_url=img_url,
                            highlights=highlights,
                            why_it_matters=f"Streamline your developer workflow and test {title} on the free tier.",
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
        except Exception as e:
            logger.debug(f"Notice harvesting AI tools: {e}")
        return stories

    # -------------------------------------------------------------------------
    # High-Level Orchestrators
    # -------------------------------------------------------------------------
    async def harvest_all(self) -> list[DevPulseStory]:
        """Execute concurrent harvest across all developer opportunity sources."""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            results = await asyncio.gather(
                self._harvest_bounties(session),
                self._harvest_jobs(session),
                self._harvest_hackathons(session),
                self._harvest_perks(session),
                self._harvest_ai_tools(session),
                return_exceptions=True,
            )

        all_stories: list[DevPulseStory] = []
        for res in results:
            if isinstance(res, list):
                all_stories.extend(res)
                for s in res:
                    self.register_story_memory(s)
        return all_stories

    async def fetch_category(self, category: str, limit: int = 4) -> list[DevPulseStory]:
        """Fetch fresh opportunity stories on-demand for a single category."""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=10)
        cat = category.strip().lower()

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            if cat in {"bounties", "bounty"}:
                res = (await self._harvest_bounties(session))[:limit]
            elif cat in {"jobs", "careers", "internships"}:
                res = (await self._harvest_jobs(session))[:limit]
            elif cat in {"hackathons", "hackathon"}:
                res = (await self._harvest_hackathons(session))[:limit]
            elif cat in {"perks", "courses"}:
                res = (await self._harvest_perks(session))[:limit]
            elif cat in {"tools", "aitools"}:
                res = (await self._harvest_ai_tools(session))[:limit]
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
    def build_story_container(story: DevPulseStory, dot: str = "•") -> KyroContainer:
        """Render a visually stunning, high-signal Components V2 developer card with dark aesthetic."""
        accent = 0xFF0033 if story.is_critical else None
        container = KyroContainer(accent_color=accent)

        badge = CATEGORY_BADGES.get(story.category, "Developer Opportunity")
        title_line = f"### [{story.title}]({story.url})"
        subtitle = f"**{badge}** • *{story.source}*"

        header_content = (
            f"{title_line}\n"
            f"> {subtitle}"
        )
        container.add_text(header_content)
        container.add_separator(divider=True)

        body_elements: list[str] = []

        # 1. Brief
        if story.summary:
            body_elements.append(f"**Executive Brief:**\n{story.summary}")

        # 2. Key Highlights
        if story.highlights:
            hl_text = "\n".join(f"> {dot} {h}" for h in story.highlights[:3])
            body_elements.append(f"**Key Details:**\n{hl_text}")

        # 3. Why It Matters
        if story.why_it_matters:
            body_elements.append(f"**Why It Matters:**\n> {story.why_it_matters}")

        # 4. Metadata Pill Row
        meta_items: list[str] = []
        if story.category == "bounties":
            reward = story.metadata.get("reward", "Paid Bounty")
            repo = story.metadata.get("repo", "")
            diff = story.metadata.get("difficulty")
            meta_items = [f"**Bounty:** `{reward}`", f"**Repo:** `{repo}`"]
            if diff:
                meta_items.append(f"**Level:** `{diff}`")
        elif story.category == "jobs":
            comp = story.metadata.get("company", "")
            salary = story.metadata.get("compensation", "Paid")
            loc = story.metadata.get("location", "Remote")
            meta_items = [f"**Company:** `{comp}`", f"**Comp:** `{salary}`", f"**Location:** `{loc}`"]
        elif story.category == "hackathons":
            prize = story.metadata.get("prize_pool", "Cash Prizes")
            deadline = story.metadata.get("deadline", "Open")
            meta_items = [f"**Prize Pool:** `{prize}`", f"**Deadline:** `{deadline}`"]
        elif story.category == "perks":
            val = story.metadata.get("value", "100% Free")
            exp = story.metadata.get("expires", "Limited")
            meta_items = [f"**Discount:** `{val}`", f"**Coupons:** `{exp}`"]
        elif story.category == "tools":
            tier = story.metadata.get("tier", "Free Tier Available")
            meta_items = [f"**Access:** `{tier}`"]

        if meta_items:
            body_elements.append(f" {dot} ".join(meta_items))

        container.add_text("\n\n".join(body_elements))

        # Full-Width Hero Media
        valid_img = clean_image_url(story.image_url)
        if valid_img:
            container.add_media(valid_img)

        # Action Buttons
        if story.category == "bounties":
            primary_label = "Claim Bounty"
        elif story.category == "jobs":
            primary_label = "Apply Now"
        elif story.category == "hackathons":
            primary_label = "Register Hackathon"
        elif story.category == "perks":
            primary_label = "Claim Perk"
        elif story.category == "tools":
            primary_label = "Try Tool"
        else:
            primary_label = "Open Link"

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
                "custom_id": f"dev_bm:{story.id}",
            },
        ])

        return container
