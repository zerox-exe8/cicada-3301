from __future__ import annotations

import asyncio
import datetime
import logging
import re
import time
from urllib.parse import urlparse
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

from src.cogs.antinuke._helpers import execute_punishment, dispatch_antinuke_log

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.ChatDefense")

# Trusted developer, programming, documentation and media domains (Always Allowed in Anti-Link)
TRUSTED_TECH_DOMAINS = {
    # Repositories & Version Control
    "github.com",
    "www.github.com",
    "gist.github.com",
    "raw.githubusercontent.com",
    "gitlab.com",
    "bitbucket.org",
    # Documentation & Developer Reference
    "docs.python.org",
    "developer.mozilla.org",
    "w3schools.com",
    "stackoverflow.com",
    "stackexchange.com",
    "devdocs.io",
    "readthedocs.io",
    # Package Registries & Indexes
    "pypi.org",
    "npmjs.com",
    "crates.io",
    "pkg.go.dev",
    "nuget.org",
    # Tech Knowledge Hubs & Engineering Articles
    "medium.com",
    "dev.to",
    "hashnode.dev",
    "geeksforgeeks.org",
    "wikipedia.org",
    "en.wikipedia.org",
    # Safe Search & Media Hosting
    "google.com",
    "www.google.com",
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "tenor.com",
    "giphy.com",
    "imgur.com",
}

# Regex for detecting Discord server invite codes
INVITE_REGEX = re.compile(
    r"(?:https?:\/\/)?(?:www\.)?(?:discord(?:\.gg|(?:app)?\.com\/invite)\/([a-zA-Z0-9\-]+))",
    re.IGNORECASE,
)

# Regex for generic web URLs
URL_REGEX = re.compile(
    r"(?:https?:\/\/|www\.)[^\s]+",
    re.IGNORECASE,
)

# Regex for typosquatting / phishing domains targeting Discord / Steam / Crypto
SCAM_DOMAIN_REGEX = re.compile(
    r"(?:d[il1]sc[o0]r[cd]l?[\.\-]|dlscord|discorcl|discort|discrod|steamcomm[u|y]n[i|l]t[y|i]|robl[o0]x-)"
    r".*?(?:\.gift|\.top|\.xyz|\.app|\.click|\.site|\.online|\.info|\.ru|\.su|\.club)",
    re.IGNORECASE,
)

# Suspicious high-risk token grabbing lures
SCAM_LURE_REGEX = re.compile(
    r"(?:free\s*nitro|nitro\s*claim|steam\s*gift|airdrop\s*claim|free\s*boost|discord\s*nitro\s*free)",
    re.IGNORECASE,
)


class ChatDefenseCog(commands.Cog):
    """
    Silent & Intelligent Chat Defense Engine:
    Anti-Scam, Anti-Invites, Anti-Link, Anti-Spam & Anti-Mass-Mention.
    Enforces server safety silently without public warning spam or clutter.
    """

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # (guild_id, user_id) -> list of recent message timestamps
        self._flood_timestamps: dict[tuple[int, int], list[float]] = {}
        # (guild_id, user_id) -> (last_content, count, last_time)
        self._duplicate_cache: dict[tuple[int, int], tuple[str, int, float]] = {}

    async def _send_silent_toast(
        self, channel: discord.TextChannel | discord.Thread, text: str, delete_after: float = 3.5
    ) -> None:
        """Send a fleeting non-intrusive toast notice that disappears silently in 3.5 seconds."""
        try:
            toast = await channel.send(text)
            await asyncio.sleep(delete_after)
            await toast.delete()
        except Exception:
            pass

    async def _process_chat_defense(self, message: discord.Message) -> bool:
        """
        Evaluate message against active chat defense protections.
        Intercepts both unauthorized bots and rogue human perpetrators.
        Returns True if message was deleted/mitigated, False otherwise.
        """
        if not message.guild:
            return False

        # Ignore messages sent by Kyro itself
        if self.bot.user and message.author.id == self.bot.user.id:
            return False

        guild = message.guild
        author = message.author

        # Master Antinuke Switch must be active for this guild
        if not self.bot.antinuke_mgr.is_enabled(guild.id):
            return False

        # Immunity Guard: Server Owner, Extra Owners, Whitelisted Admins & Roles (and whitelisted bots) are immune
        if self.bot.antinuke_mgr.is_immune(guild, author.id):
            return False

        content = message.content or ""
        clean_content = content.strip()

        # ── 1. Anti-Scam / Token Grabber Phishing Defense ──
        if self.bot.antinuke_mgr.is_module_enabled(guild.id, "anti_scam"):
            has_scam_domain = bool(SCAM_DOMAIN_REGEX.search(content))
            has_scam_lure = bool(SCAM_LURE_REGEX.search(content))

            if has_scam_domain or (has_scam_lure and URL_REGEX.search(content)):
                try:
                    await message.delete()
                except Exception:
                    pass

                punish_result = await execute_punishment(
                    self.bot,
                    guild,
                    author,
                    "Anti-Scam Phishing Defense",
                    "Phishing / token-grabber link detected",
                )

                # Silent DM advisory to user if human
                if not author.bot:
                    try:
                        await author.send(
                            f"⚠️ Your message in **{guild.name}** was automatically removed because it contained a suspected "
                            f"phishing/scam URL. If your account was compromised, please change your Discord password immediately."
                        )
                    except Exception:
                        pass

                await dispatch_antinuke_log(
                    self.bot,
                    guild,
                    "Anti-Scam Phishing Defense",
                    author,
                    punish_result,
                    "Malicious Link Neutralized",
                    extra=f"Channel: {message.channel.mention}\nSnippet: `{clean_content[:120]}`",
                )
                return True

        # ── 2. Anti-Invites (Server Advertising Filter) ──
        if self.bot.antinuke_mgr.is_module_enabled(guild.id, "anti_invites"):
            invite_match = INVITE_REGEX.search(content)
            if invite_match:
                code = invite_match.group(1).lower()
                current_vanity = (guild.vanity_url_code or "").lower()
                is_self_invite = False
                if current_vanity and code == current_vanity:
                    is_self_invite = True

                if not is_self_invite:
                    try:
                        await message.delete()
                    except Exception:
                        pass

                    # If author is an unwhitelisted bot, eliminate it immediately
                    if author.bot:
                        punish_result = await execute_punishment(
                            self.bot,
                            guild,
                            author,
                            "Anti-Invite Protection",
                            f"Unauthorized bot advertising external invite code: {code}",
                        )
                    else:
                        punish_result = "Message Deleted"
                        asyncio.create_task(
                            self._send_silent_toast(
                                message.channel,
                                "-# ⚠️ External Discord invites are not allowed in this server.",
                                delete_after=3.5,
                            )
                        )

                    await dispatch_antinuke_log(
                        self.bot,
                        guild,
                        "Anti-Invite Protection",
                        author,
                        punish_result,
                        "External Invite Neutralized",
                        extra=f"Channel: {message.channel.mention}\nCode: `{code}`",
                    )
                    return True

        # ── 3. Anti-Link (Developer & Tech Safe Filter) ──
        if self.bot.antinuke_mgr.is_module_enabled(guild.id, "anti_link"):
            url_match = URL_REGEX.search(content)
            if url_match:
                raw_url = url_match.group(0)
                if not raw_url.startswith(("http://", "https://")):
                    raw_url = "https://" + raw_url

                try:
                    parsed = urlparse(raw_url)
                    domain = (parsed.netloc or "").lower().split(":")[0]
                    if domain.startswith("www."):
                        clean_domain = domain[4:]
                    else:
                        clean_domain = domain

                    is_trusted = (
                        clean_domain in TRUSTED_TECH_DOMAINS
                        or any(clean_domain.endswith("." + d) for d in TRUSTED_TECH_DOMAINS)
                    )

                    if not is_trusted:
                        try:
                            await message.delete()
                        except Exception:
                            pass

                        if author.bot:
                            punish_result = await execute_punishment(
                                self.bot,
                                guild,
                                author,
                                "Anti-Link Protection",
                                f"Unauthorized bot posting unverified link: {domain}",
                            )
                        else:
                            punish_result = "Message Deleted"
                            asyncio.create_task(
                                self._send_silent_toast(
                                    message.channel,
                                    "-# ⚠️ Links from unverified domains are restricted in this server.",
                                    delete_after=3.5,
                                )
                            )

                        await dispatch_antinuke_log(
                            self.bot,
                            guild,
                            "Anti-Link Protection",
                            author,
                            punish_result,
                            "Unverified URL Neutralized",
                            extra=f"Channel: {message.channel.mention}\nDomain: `{domain}`",
                        )
                        return True
                except Exception as e:
                    logger.debug(f"Notice parsing URL in chat defense: {e}")

        # ── 4. Anti-Mass-Mention (Ping Raid Guard & Unauthorized @everyone/@here Killer) ──
        if self.bot.antinuke_mgr.is_module_enabled(guild.id, "anti_mass_mention"):
            total_mentions = len(message.mentions) + len(message.role_mentions)
            has_raw_everyone = bool(
                message.mention_everyone
                or "@everyone" in content
                or "@here" in content
            )

            # Trigger on unauthorized @everyone/@here or 3+ mentions
            if has_raw_everyone or total_mentions >= 3:
                try:
                    await message.delete()
                except Exception:
                    pass

                breach_reason = (
                    "Unauthorized @everyone/@here ping abuse"
                    if has_raw_everyone
                    else f"Mass mention ping flood ({total_mentions} mentions)"
                )

                punish_result = await execute_punishment(
                    self.bot,
                    guild,
                    author,
                    "Anti-Mass Mention",
                    breach_reason,
                )

                await dispatch_antinuke_log(
                    self.bot,
                    guild,
                    "Anti-Mass Mention",
                    author,
                    punish_result,
                    "Ping Raid Neutralized",
                    extra=f"Channel: {message.channel.mention}\n> • **Breach:** {breach_reason}\n> • **Mentions Count:** `{total_mentions}`",
                )
                return True

        # ── 5. Anti-Spam (Rapid Flooding & Duplicate Spammer) ──
        if self.bot.antinuke_mgr.is_module_enabled(guild.id, "anti_spam"):
            now = time.time()
            tracker_key = (guild.id, author.id)

            # Rapid message flood: 5 messages in < 3.5 seconds
            times = self._flood_timestamps.setdefault(tracker_key, [])
            times.append(now)
            self._flood_timestamps[tracker_key] = [t for t in times if now - t <= 3.5]

            if len(self._flood_timestamps[tracker_key]) >= 5:
                try:
                    await message.delete()
                except Exception:
                    pass

                self._flood_timestamps[tracker_key].clear()

                punish_result = await execute_punishment(
                    self.bot,
                    guild,
                    author,
                    "Anti-Spam Flooding",
                    "Rapid message flood attack (5+ msgs / 3.5s)",
                )

                await dispatch_antinuke_log(
                    self.bot,
                    guild,
                    "Anti-Spam Flooding",
                    author,
                    punish_result,
                    "Flood Attack Neutralized",
                    extra=f"Channel: {message.channel.mention}\nRate: 5+ msgs / 3.5s",
                )
                return True

            # Cross-channel / Rapid duplicate spam: 3 identical messages > 10 chars in 6s
            if len(clean_content) >= 10:
                last_txt, dup_count, last_t = self._duplicate_cache.get(tracker_key, ("", 0, 0))
                if last_txt == clean_content and (now - last_t) <= 6.0:
                    dup_count += 1
                else:
                    dup_count = 1

                self._duplicate_cache[tracker_key] = (clean_content, dup_count, now)

                if dup_count >= 3:
                    try:
                        await message.delete()
                    except Exception:
                        pass

                    self._duplicate_cache.pop(tracker_key, None)

                    punish_result = await execute_punishment(
                        self.bot,
                        guild,
                        author,
                        "Anti-Spam Duplicate",
                        "Repeated duplicate copy-paste spam",
                    )

                    await dispatch_antinuke_log(
                        self.bot,
                        guild,
                        "Anti-Spam Duplicate",
                        author,
                        punish_result,
                        "Duplicate Spam Suppressed",
                        extra=f"Channel: {message.channel.mention}\nRepeats: `{dup_count}`",
                    )
                    return True

        return False

    @commands.Cog.listener("on_message")
    async def on_message_handler(self, message: discord.Message) -> None:
        """Listen to incoming messages and evaluate chat defense rules."""
        await self._process_chat_defense(message)

    @commands.Cog.listener("on_message_edit")
    async def on_message_edit_handler(self, before: discord.Message, after: discord.Message) -> None:
        """Prevent bypassing chat defense via sneaky message edits."""
        if before.content == after.content:
            return
        await self._process_chat_defense(after)


async def setup(bot: KyroBot) -> None:
    """Register the ChatDefenseCog into KyroBot."""
    await bot.add_cog(ChatDefenseCog(bot))
