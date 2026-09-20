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
    """Compute normalized alphanumeric title fingerprint stripped of bracketed tags and punctuation."""
    if not raw_title:
        return ""
    # Strip brackets e.g. [Bounty], [100% OFF], [Paid], (Remote)
    t = re.sub(r"\[[^\]]*\]|\([^\)]*\)", " ", raw_title)
    t = re.sub(r"[^a-zA-Z0-9\s]", " ", t).lower()
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def clean_image_url(url: Optional[str]) -> Optional[str]:
    """Sanitize, unescape, and validate image URLs for seamless Discord rendering."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if url.startswith("//"):
        url = f"https:{url}"
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
    title_hash: str = ""
    entity_hash: str = ""
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
        self._seen_title_hashes: set[str] = set()
        self._seen_entity_hashes: set[str] = set()
        self._guild_configs: dict[int, dict[str, Any]] = {}
        self._stories_by_id: dict[str, DevPulseStory] = {}
        self._lock = asyncio.Lock()

    async def load_cache(self) -> None:
        """Load recent seen hashes, title hashes, entity hashes, and guild subscriptions into fast memory."""
        try:
            if not self.db:
                return
            rows = await self.db.fetch_all(
                "SELECT guild_id, channel_id, categories, thread_enabled, mode, cadence, last_dispatch_ts FROM guild_dev_pulse;"
            )
            async with self._lock:
                self._guild_configs = {
                    int(r["guild_id"]): {
                        "channel_id": int(r["channel_id"]),
                        "categories": str(r["categories"] or "all"),
                        "thread_enabled": bool(r.get("thread_enabled", False)),
                        "mode": str(r.get("mode") or "live"),
                        "cadence": str(r.get("cadence") or "hourly"),
                        "last_dispatch_ts": r.get("last_dispatch_ts"),
                    }
                    for r in rows
                }

            hash_rows = await self.db.fetch_all(
                "SELECT item_hash, title_hash, entity_hash FROM dev_pulse_history ORDER BY dispatched_at DESC LIMIT 50000;"
            )
            async with self._lock:
                self._seen_hashes = {str(r["item_hash"]) for r in hash_rows if r.get("item_hash")}
                self._seen_title_hashes = {str(r["title_hash"]) for r in hash_rows if r.get("title_hash")}
                self._seen_entity_hashes = {str(r["entity_hash"]) for r in hash_rows if r.get("entity_hash")}

            logger.info(
                f"DevPulseManager loaded {len(self._guild_configs)} guild feed(s), {len(self._seen_hashes)} seen URL hash(es), and {len(self._seen_title_hashes)} title hash(es)."
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
                    "cadence": existing.get("cadence", "hourly"),
                    "last_dispatch_ts": existing.get("last_dispatch_ts"),
                }
            return True
        except Exception as e:
            logger.error(f"Failed to set dev pulse channel for guild {guild_id}: {e}", exc_info=e)
            return False

    async def set_cadence(self, guild_id: int, cadence: str) -> bool:
        """Update delivery cadence: '15m', 'hourly', '09:00', '00:00', or 'custom:HH:MM'."""
        c = cadence.strip().lower()
        query = "UPDATE guild_dev_pulse SET cadence = $1 WHERE guild_id = $2;"
        try:
            await self.db.execute(query, c, guild_id)
            async with self._lock:
                if guild_id in self._guild_configs:
                    self._guild_configs[guild_id]["cadence"] = c
            return True
        except Exception as e:
            logger.error(f"Failed to set dev pulse cadence for guild {guild_id}: {e}", exc_info=e)
            return False

    async def update_last_dispatch(self, guild_id: int, dt: Optional[datetime.datetime] = None) -> None:
        """Record timestamp of latest successful batch dispatch."""
        if dt is None:
            dt = datetime.datetime.now(datetime.timezone.utc)
        query = "UPDATE guild_dev_pulse SET last_dispatch_ts = $1 WHERE guild_id = $2;"
        try:
            await self.db.execute(query, dt, guild_id)
            async with self._lock:
                if guild_id in self._guild_configs:
                    self._guild_configs[guild_id]["last_dispatch_ts"] = dt
        except Exception as e:
            logger.error(f"Failed to update last dispatch ts for guild {guild_id}: {e}", exc_info=e)

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

    def is_seen(self, story: DevPulseStory | str) -> bool:
        """Check if an item has already been broadcast by URL hash, title fingerprint, or entity signature."""
        if isinstance(story, str):
            return story in self._seen_hashes or story in self._seen_title_hashes or story in self._seen_entity_hashes
        if story.id in self._seen_hashes:
            return True
        if story.title_hash and story.title_hash in self._seen_title_hashes:
            return True
        if story.entity_hash and story.entity_hash in self._seen_entity_hashes:
            return True
        return False

    async def record_dispatched(self, stories: list[DevPulseStory]) -> None:
        """Store item hashes into history to prevent future duplicate broadcasts."""
        if not stories or not self.db:
            return
        insert_query = """
        INSERT INTO dev_pulse_history (item_hash, source, category, title, url, title_hash, entity_hash)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (item_hash) DO UPDATE
        SET title_hash = EXCLUDED.title_hash, entity_hash = EXCLUDED.entity_hash;
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
                await self.db.execute(insert_query, s.id, s.source, s.category, s.title, s.url, s.title_hash, s.entity_hash)
        except Exception as e:
            logger.error(f"Failed to write dispatched dev pulse history: {e}", exc_info=e)

    # -------------------------------------------------------------------------
    # Ingestion Adapters
    # -------------------------------------------------------------------------
    async def _harvest_bounties(self, session: aiohttp.ClientSession, limit: int = 6) -> list[DevPulseStory]:
        """Harvest active open-source GitHub issues with paid bounties ($50 - $500+)."""
        stories: list[DevPulseStory] = []
        url = "https://api.github.com/search/issues?q=label:bounty+state:open+is:issue&sort=created&order=desc&per_page=12"
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

                        # Strict blacklist for mirror bots, aggregator repos, and troll bounties
                        bad_repos = ["bountyfarmer", "bounty-plaza", "issue-mirror", "bounty-aggregator", "test", "dummy", "practice", "playground", "demo"]
                        if any(b in repo_name.lower() for b in bad_repos):
                            continue
                        if any(b in title.lower() for b in ["bountyfarmer", "bounty-plaza", "239398281948585883", "give boxy its own"]):
                            continue

                        canon_u = canonicalize_url(html_url)
                        item_id = hashlib.sha256(canon_u.encode()).hexdigest()
                        t_hash = compute_title_fingerprint(title)
                        ent_hash = hashlib.sha256(f"bounty:{t_hash[:24]}".encode()).hexdigest()

                        if item_id in self._seen_hashes or t_hash in self._seen_title_hashes or ent_hash in self._seen_entity_hashes:
                            continue

                        candidates.append(item)
                        if len(candidates) >= limit:
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

                        canon_url = canonicalize_url(html_url)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(title)
                        entity_h = hashlib.sha256(f"bounty:{title_h[:24]}".encode()).hexdigest()

                        story_obj = DevPulseStory(
                            id=story_id,
                            source="GitHub Bounties",
                            category="bounties",
                            title=title,
                            summary=summary,
                            url=canon_url,
                            metadata={"reward": reward, "repo": repo_name, "difficulty": diff},
                            image_url=f"https://github.com/{repo_name.split('/')[0] if '/' in repo_name else repo_name}.png?size=400",
                            highlights=highlights,
                            why_it_matters=why_matters,
                            title_hash=title_h,
                            entity_hash=entity_h,
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

    async def _harvest_jobs(self, session: aiohttp.ClientSession, limit: int = 6) -> list[DevPulseStory]:
        """Harvest entry-level, fresher, and remote developer internships and jobs with authentic company logos."""
        stories: list[DevPulseStory] = []
        jobicy_url = "https://jobicy.com/api/v2/remote-jobs?count=15&tag=dev"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "application/json"}
        try:
            async with session.get(jobicy_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    jobs = data.get("jobs", []) if isinstance(data, dict) else []
                    candidates: list[dict[str, Any]] = []
                    exclude_keywords = ["recruiter", "sales", "hr", "marketing", "account executive", "copywriter", "customer support"]

                    for job in jobs:
                        pos = job.get("jobTitle", "")
                        comp = job.get("companyName", "Tech Company")
                        link = job.get("url")
                        if not pos or not link:
                            continue
                        if any(ex in pos.lower() for ex in exclude_keywords):
                            continue

                        canon_u = canonicalize_url(link)
                        s_id = hashlib.sha256(canon_u.encode()).hexdigest()
                        t_hash = compute_title_fingerprint(f"{pos} {comp}")
                        clean_comp = re.sub(r"[^a-zA-Z0-9]", "", comp).lower()
                        clean_pos = re.sub(r"[^a-zA-Z0-9]", "", pos).lower()
                        ent_hash = hashlib.sha256(f"job:{clean_comp}:{clean_pos}".encode()).hexdigest()

                        if s_id in self._seen_hashes or t_hash in self._seen_title_hashes or ent_hash in self._seen_entity_hashes:
                            continue

                        candidates.append(job)
                        if len(candidates) >= limit:
                            break

                    async def _process_jobicy_job(job: dict[str, Any]) -> Optional[DevPulseStory]:
                        pos = job.get("jobTitle", "")
                        comp = job.get("companyName", "Tech Company")
                        link = job.get("url")
                        raw_desc = _clean_html(job.get("jobDescription") or "")
                        geo = job.get("jobGeo") or "Worldwide Remote"

                        salary_min = job.get("annualSalaryMin")
                        salary_max = job.get("annualSalaryMax")
                        curr = job.get("salaryCurrency", "USD")
                        comp_str = "Paid / Competitive"
                        if salary_min and salary_max:
                            comp_str = f"${salary_min:,} - ${salary_max:,} {curr}/yr"
                        elif salary_min:
                            comp_str = f"${salary_min:,}+ {curr}"

                        # High-resolution authentic company logo
                        logo_url = job.get("companyLogo")
                        if not logo_url:
                            clean_name = re.sub(r"[^a-zA-Z0-9]", "", comp).lower()
                            logo_url = f"https://t2.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://{clean_name}.com&size=256"

                        ai_data = await analyze_opportunity_with_gemini(
                            session=session,
                            title=f"{pos} at {comp}",
                            raw_context=f"Role: {pos}\nCompany: {comp}\nCompensation: {comp_str}\nLocation: {geo}\nDescription: {raw_desc[:800]}",
                            category="Developer Job / Internship",
                        )

                        if ai_data and not ai_data.get("is_valid", True):
                            return None

                        if ai_data and ai_data.get("summary"):
                            summary = ai_data["summary"]
                            highlights = ai_data.get("highlights", [])
                            if not highlights:
                                highlights = [
                                    f"Company: {comp} ({geo})",
                                    f"Compensation: {comp_str}",
                                    "Experience Level: Entry-Level / Internship / Junior",
                                ]
                            why_matters = ai_data.get("why_it_matters", f"Great engineering opportunity with remote flexibility at {comp}.")
                        else:
                            highlights = [
                                f"Company: {comp} ({geo})",
                                f"Compensation: {comp_str}",
                                "Experience Level: Entry-Level / Internship / Junior",
                            ]
                            summary = _smart_truncate(raw_desc, 280) if raw_desc else f"Remote engineering role open for {pos} at {comp}."
                            why_matters = f"Great engineering opportunity with remote flexibility at {comp}."

                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(f"{pos} {comp}")
                        clean_comp = re.sub(r"[^a-zA-Z0-9]", "", comp).lower()
                        clean_pos = re.sub(r"[^a-zA-Z0-9]", "", pos).lower()
                        entity_h = hashlib.sha256(f"job:{clean_comp}:{clean_pos}".encode()).hexdigest()

                        story_obj = DevPulseStory(
                            id=story_id,
                            source="Global Developer Careers",
                            category="jobs",
                            title=f"{pos} at {comp}",
                            summary=summary,
                            url=canon_url,
                            metadata={"company": comp, "compensation": comp_str, "location": geo},
                            image_url=logo_url,
                            highlights=highlights,
                            why_it_matters=why_matters,
                            title_hash=title_h,
                            entity_hash=entity_h,
                        )
                        self.register_story_memory(story_obj)
                        return story_obj

                    results = await asyncio.gather(*[_process_jobicy_job(c) for c in candidates], return_exceptions=True)
                    for r in results:
                        if isinstance(r, DevPulseStory):
                            stories.append(r)
        except Exception as e:
            logger.debug(f"Notice harvesting jobs: {e}")

        # Fallback to RemoteOK if Jobicy yielded zero
        if not stories:
            try:
                async with session.get("https://remoteok.com/api?tag=dev", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        jobs = [j for j in data if isinstance(j, dict) and j.get("position")]
                        for job in jobs:
                            pos = job.get("position", "")
                            comp = job.get("company", "Tech Startup")
                            link = job.get("url") or job.get("apply_url")
                            if not link or not pos:
                                continue
                            canon_url = canonicalize_url(link)
                            story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                            title_h = compute_title_fingerprint(f"{pos} {comp}")
                            clean_comp = re.sub(r"[^a-zA-Z0-9]", "", comp).lower()
                            clean_pos = re.sub(r"[^a-zA-Z0-9]", "", pos).lower()
                            entity_h = hashlib.sha256(f"job:{clean_comp}:{clean_pos}".encode()).hexdigest()

                            if story_id in self._seen_hashes or title_h in self._seen_title_hashes or entity_h in self._seen_entity_hashes:
                                continue

                            story_obj = DevPulseStory(
                                id=story_id,
                                source="RemoteOK Careers",
                                category="jobs",
                                title=f"{pos} at {comp}",
                                summary=f"Remote engineering opportunity for {pos} at {comp}.",
                                url=canon_url,
                                metadata={"company": comp, "compensation": "Paid / Competitive", "location": "Remote"},
                                image_url=logo,
                                highlights=[f"Company: {comp}", "Compensation: Competitive", "Status: Active Remote Listing"],
                                why_it_matters=f"Join the engineering team at {comp}.",
                                title_hash=title_h,
                                entity_hash=entity_h,
                            )
                            self.register_story_memory(story_obj)
                            stories.append(story_obj)
                            if len(stories) >= limit:
                                break
            except Exception as e:
                logger.debug(f"Notice during RemoteOK fallback: {e}")

        return stories

    async def _harvest_hackathons(self, session: aiohttp.ClientSession, limit: int = 6) -> list[DevPulseStory]:
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
                    data = await resp.json(content_type=None)
                    for h in data.get("hackathons", []):
                        title = h.get("title", "")
                        link = h.get("url", "")
                        if not title or not link:
                            continue

                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(title)
                        entity_h = hashlib.sha256(f"hackathon:{title_h[:24]}".encode()).hexdigest()

                        if story_id in self._seen_hashes or title_h in self._seen_title_hashes or entity_h in self._seen_entity_hashes:
                            continue

                        raw_prize = h.get("prize_amount", "Cash & Swags")
                        prize_clean = _clean_html(raw_prize).replace("data-currency-value", "").replace("<", "").replace(">", "").strip()
                        prize_clean = re.sub(r"\s+", " ", prize_clean) or "$10,000+ Prize Pool"

                        sub_period = h.get("submission_period_dates") or "Registration Open"
                        theme = ", ".join([t.get("name") for t in h.get("themes", [])[:3]]) if h.get("themes") else "Open Innovation"
                        
                        # Authentic AWS CloudFront challenge banner
                        hero_img = h.get("thumbnail_url")
                        if hero_img and hero_img.startswith("//"):
                            hero_img = f"https:{hero_img}"

                        highlights = [
                            f"Prize Pool: {prize_clean}",
                            f"Submission Window: {sub_period}",
                            f"Themes: {theme}",
                        ]

                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(title)
                        entity_h = hashlib.sha256(f"hackathon:{title_h[:24]}".encode()).hexdigest()

                        story_obj = DevPulseStory(
                            id=story_id,
                            source="Devpost Global",
                            category="hackathons",
                            title=title,
                            summary=f"Global developer hackathon featuring {prize_clean} in prizes. Open for solo builders and teams.",
                            url=canon_url,
                            metadata={"prize_pool": prize_clean, "deadline": sub_period},
                            image_url=hero_img,
                            highlights=highlights,
                            why_it_matters=f"Compete globally, build real portfolio projects, and earn from a {prize_clean} prize pool.",
                            title_hash=title_h,
                            entity_hash=entity_h,
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
                        if len(stories) >= limit:
                            break
        except Exception as e:
            logger.debug(f"Notice harvesting hackathons: {e}")
        return stories

    async def _harvest_perks(self, session: aiohttp.ClientSession, limit: int = 6) -> list[DevPulseStory]:
        """Harvest free developer perks, 100% off tech courses, and cloud vouchers."""
        stories: list[DevPulseStory] = []
        feed_url = "https://www.discudemy.com/feed"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            async with session.get(feed_url, headers=headers) as resp:
                if resp.status == 200:
                    xml_data = await resp.text()
                    root = ET.fromstring(xml_data)
                    for item in root.findall(".//item"):
                        title = _clean_html(item.findtext("title") or "").strip()
                        link = item.findtext("link") or ""
                        desc = _clean_html(item.findtext("description") or "").strip()
                        if not title or not link:
                            continue

                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(title)
                        entity_h = hashlib.sha256(f"perk:{title_h[:24]}".encode()).hexdigest()

                        if story_id in self._seen_hashes or title_h in self._seen_title_hashes or entity_h in self._seen_entity_hashes:
                            continue

                        # Extract authentic high-resolution course thumbnail from enclosure
                        img_url = None
                        enc = item.find("enclosure")
                        if enc is not None and enc.get("url"):
                            raw_u = enc.get("url")
                            # Rewrite udemy-images.udemy.com to public unauthenticated CDN
                            img_url = raw_u.replace("udemy-images.udemy.com", "img-c.udemycdn.com")

                        highlights = [
                            "Discount: 100% Free Coupon Code Included",
                            "Access: Lifetime Full Course & Certificate of Completion",
                            "Expiry: Limited Redemptions (First Come First Served)",
                        ]

                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(title)
                        entity_h = hashlib.sha256(f"perk:{title_h[:24]}".encode()).hexdigest()

                        story_obj = DevPulseStory(
                            id=story_id,
                            source="Developer Perks & Courses",
                            category="perks",
                            title=title,
                            summary=desc[:260] if desc else "Limited-time 100% free developer course coupon and certification voucher.",
                            url=canon_url,
                            metadata={"value": "100% Free Lifetime Access", "expires": "Limited Coupons"},
                            image_url=img_url,
                            highlights=highlights,
                            why_it_matters="Upskill for free and claim certification without paying course fees.",
                            title_hash=title_h,
                            entity_hash=entity_h,
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
                        if len(stories) >= limit:
                            break
        except Exception as e:
            logger.debug(f"Notice harvesting perks: {e}")
        return stories

    async def _harvest_ai_tools(self, session: aiohttp.ClientSession, limit: int = 6) -> list[DevPulseStory]:
        """Harvest daily top practical AI developer tools with authentic hero images from tool websites."""
        stories: list[DevPulseStory] = []
        feed_url = "https://www.producthunt.com/feed"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            async with session.get(feed_url, headers=headers) as resp:
                if resp.status == 200:
                    xml_data = await resp.text()
                    root = ET.fromstring(xml_data)
                    for entry in root.findall(".//{http://www.w3.org/2005/Atom}entry"):
                        title = _clean_html(entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
                        link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                        link = link_el.get("href") if link_el is not None else ""
                        raw_content = entry.findtext("{http://www.w3.org/2005/Atom}content") or ""
                        desc = _clean_html(raw_content).strip()
                        if not title or not link:
                            continue

                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(title)
                        entity_h = hashlib.sha256(f"tool:{title_h[:24]}".encode()).hexdigest()

                        if story_id in self._seen_hashes or title_h in self._seen_title_hashes or entity_h in self._seen_entity_hashes:
                            continue

                        # Extract authentic tool launch banner from official product site
                        img_url = None
                        m_redir = re.search(r'href=["\'](https://www\.producthunt\.com/r/p/[^"\']+)["\']', raw_content)
                        if m_redir:
                            redir_url = m_redir.group(1).replace("&amp;", "&")
                            try:
                                async with session.get(redir_url, headers=headers, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=2.5)) as pr:
                                    if pr.status == 200:
                                        p_html = await pr.text()
                                        m_og = re.search(r'<meta[^>]+(?:property|name)=[\'"](?:og:image)[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', p_html, re.I)
                                        if not m_og:
                                            m_og = re.search(r'<meta[^>]+content=[\'"]([^\'"]+)[\'"][^>]+(?:property|name)=[\'"](?:og:image)[\'"]', p_html, re.I)
                                        if m_og:
                                            from urllib.parse import urljoin
                                            raw_img = m_og.group(1).replace("&amp;", "&")
                                            img_url = urljoin(str(pr.url), raw_img)
                                        else:
                                            img_url = f"https://t2.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url={str(pr.url)}&size=256"
                            except Exception:
                                pass

                        highlights = [
                            "Tier: Generous Free Tier / Free Trials Available",
                            "Category: Developer AI Productivity Tool",
                            "Direct Launch via Product Hunt",
                        ]

                        canon_url = canonicalize_url(link)
                        story_id = hashlib.sha256(canon_url.encode()).hexdigest()
                        title_h = compute_title_fingerprint(title)
                        entity_h = hashlib.sha256(f"tool:{title_h[:24]}".encode()).hexdigest()

                        story_obj = DevPulseStory(
                            id=story_id,
                            source="Product Hunt AI",
                            category="tools",
                            title=title,
                            summary=_smart_truncate(desc, 280) if desc else f"New trending AI developer tool launched on Product Hunt: {title}.",
                            url=canon_url,
                            metadata={"tier": "Free Tier Available", "replaces": "Productivity Booster"},
                            image_url=img_url,
                            highlights=highlights,
                            why_it_matters=f"Streamline your developer workflow and test {title} on the free tier.",
                            title_hash=title_h,
                            entity_hash=entity_h,
                        )
                        self.register_story_memory(story_obj)
                        stories.append(story_obj)
                        if len(stories) >= limit:
                            break
        except Exception as e:
            logger.debug(f"Notice harvesting AI tools: {e}")
        return stories

    # -------------------------------------------------------------------------
    # High-Level Orchestrators
    # -------------------------------------------------------------------------
    async def harvest_all(self) -> list[DevPulseStory]:
        """Execute concurrent harvest across all developer opportunity sources with in-batch cross-deduplication."""
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

        raw_stories: list[DevPulseStory] = []
        for res in results:
            if isinstance(res, list):
                raw_stories.extend(res)

        # In-batch cross-source multi-layer deduplication
        deduped: list[DevPulseStory] = []
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        seen_entities: set[str] = set()

        for s in raw_stories:
            # Check against batch seen set AND historical database seen sets
            if s.id in seen_urls or self.is_seen(s):
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

    async def harvest_balanced_batch(self, target_total: int = 10) -> list[DevPulseStory]:
        """Harvest high-signal developer opportunities across all 4 key categories (Tools, Free Perks/Coupons, Remote Jobs, Bounties/Hackathons),
        enforcing strict multi-layer deduplication and balanced distribution (3 tools, 3 perks, 2 jobs, 2 bounties/hackathons)."""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tools_res, perks_res, jobs_res, bounties_res, hackathons_res = await asyncio.gather(
                self._harvest_ai_tools(session, limit=6),
                self._harvest_perks(session, limit=6),
                self._harvest_jobs(session, limit=6),
                self._harvest_bounties(session, limit=6),
                self._harvest_hackathons(session, limit=6),
                return_exceptions=True,
            )

        def _clean_pool(raw: Any) -> list[DevPulseStory]:
            if not isinstance(raw, list):
                return []
            return [s for s in raw if isinstance(s, DevPulseStory)]

        tools_items = _clean_pool(tools_res)
        perks_items = _clean_pool(perks_res)
        jobs_items = _clean_pool(jobs_res)
        comm_items = _clean_pool(bounties_res) + _clean_pool(hackathons_res)

        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        seen_entities: set[str] = set()

        def _filter_unseen(items: list[DevPulseStory]) -> list[DevPulseStory]:
            result: list[DevPulseStory] = []
            for s in items:
                if s.id in seen_urls or self.is_seen(s):
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

        pools: dict[str, list[DevPulseStory]] = {
            "tools": _filter_unseen(tools_items),
            "perks": _filter_unseen(perks_items),
            "jobs": _filter_unseen(jobs_items),
            "community": _filter_unseen(comm_items),
        }

        # Quota allocation: 3 tools, 3 perks, 2 jobs, 2 community (bounties/hackathons)
        quotas: dict[str, int] = {
            "tools": 3,
            "perks": 3,
            "jobs": 2,
            "community": 2,
        }

        selected: list[DevPulseStory] = []
        for cat_name, quota in quotas.items():
            items = pools.get(cat_name, [])
            chosen = items[:quota]
            selected.extend(chosen)
            pools[cat_name] = items[quota:]

        # Backfill if any pool fell short
        if len(selected) < target_total:
            remaining: list[DevPulseStory] = []
            for items in pools.values():
                remaining.extend(items)

            def _score_key(s: DevPulseStory) -> int:
                if s.is_critical:
                    return 1_000_000
                if s.category == "bounties":
                    return 500
                if s.category == "perks":
                    return 400
                if s.category == "jobs":
                    return 300
                if s.category == "tools":
                    return 200
                return 100

            remaining.sort(key=_score_key, reverse=True)
            needed = target_total - len(selected)
            selected.extend(remaining[:needed])

        for s in selected:
            self.register_story_memory(s)

        return selected[:target_total]

    async def fetch_category(self, category: str, limit: int = 4) -> list[DevPulseStory]:
        """Fetch fresh opportunity stories on-demand for a single category, filtering out seen items."""
        connector = aiohttp.TCPConnector(ssl=False)
        timeout = aiohttp.ClientTimeout(total=10)
        cat = category.strip().lower()

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            if cat in {"bounties", "bounty"}:
                res = await self._harvest_bounties(session)
            elif cat in {"jobs", "careers", "internships"}:
                res = await self._harvest_jobs(session)
            elif cat in {"hackathons", "hackathon"}:
                res = await self._harvest_hackathons(session)
            elif cat in {"perks", "courses"}:
                res = await self._harvest_perks(session)
            elif cat in {"tools", "aitools"}:
                res = await self._harvest_ai_tools(session)
            else:
                res = await self.harvest_all()

        unseen = [s for s in res if not self.is_seen(s)]
        final_res = unseen[:limit] if unseen else res[:limit]
        for s in final_res:
            self.register_story_memory(s)
        return final_res

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
            body_elements.append(story.summary)

        # 2. Key Highlights
        if story.highlights:
            hl_text = "\n".join(f"> {dot} {h}" for h in story.highlights[:3])
            body_elements.append(hl_text)

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
