"""
Kyro Discord Bot - Clean Channel Snipe Utility
Clean, focused deleted message inspector with direct highlighted content and zero clutter.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


@dataclass
class SnipeEntry:
    """Structure storing captured deleted or edited message data."""
    id: int
    author_id: int
    author_name: str
    author_avatar: str
    content: str
    attachments: list[str]
    created_at: datetime
    action_at: datetime
    type: str  # 'delete' or 'edit'
    before: Optional[str] = None
    after: Optional[str] = None
    guild_id: int = 0
    channel_id: int = 0
    channel_name: str = ""


class SnipeCog(commands.Cog, name="Utility-Snipe"):
    """Channel message retention inspector for deleted messages."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        if not hasattr(self.bot, "snipe_cache"):
            self.bot.snipe_cache = {}
        if not hasattr(self.bot, "guild_snipe_cache"):
            self.bot.guild_snipe_cache = {}

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Capture deleted messages in memory buffer."""
        if not message.guild or message.author.bot:
            return

        content = message.content or ""
        media_urls: list[str] = []

        # 1. Attachments
        for a in message.attachments:
            if a.url:
                media_urls.append(a.url)
            elif a.proxy_url:
                media_urls.append(a.proxy_url)

        # 2. Stickers
        for s in message.stickers:
            if s.url:
                media_urls.append(s.url)

        # 3. Embeds (Tenor GIFs, Giphy, image embeds)
        for emb in message.embeds:
            if emb.image and emb.image.url:
                media_urls.append(emb.image.url)
            elif emb.thumbnail and emb.thumbnail.url:
                media_urls.append(emb.thumbnail.url)

        # 4. Check for direct image or gif link in content if no media detected
        if not media_urls and content:
            import re
            url_match = re.search(r"https?://\S+", content)
            if url_match:
                found_url = url_match.group(0)
                clean_url = found_url.lower().split("?")[0]
                if clean_url.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    media_urls.append(found_url)

        if not content and not media_urls:
            return

        channel_id = message.channel.id
        guild_id = message.guild.id

        if channel_id not in self.bot.snipe_cache:
            self.bot.snipe_cache[channel_id] = deque(maxlen=25)
        if guild_id not in self.bot.guild_snipe_cache:
            self.bot.guild_snipe_cache[guild_id] = deque(maxlen=100)

        entry = SnipeEntry(
            id=message.id,
            author_id=message.author.id,
            author_name=message.author.display_name,
            author_avatar=message.author.display_avatar.url if message.author.display_avatar else "",
            content=content,
            attachments=media_urls,
            created_at=message.created_at,
            action_at=discord.utils.utcnow(),
            type="delete",
            guild_id=guild_id,
            channel_id=channel_id,
            channel_name=message.channel.name,
        )

        self.bot.snipe_cache[channel_id].appendleft(entry)
        self.bot.guild_snipe_cache[guild_id].appendleft(entry)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        """Capture edited messages in memory buffer."""
        if not before.guild or before.author.bot:
            return

        if before.content == after.content:
            return

        channel_id = before.channel.id
        guild_id = before.guild.id

        if channel_id not in self.bot.snipe_cache:
            self.bot.snipe_cache[channel_id] = deque(maxlen=25)
        if guild_id not in self.bot.guild_snipe_cache:
            self.bot.guild_snipe_cache[guild_id] = deque(maxlen=100)

        media = [a.url or a.proxy_url for a in before.attachments if a.url or a.proxy_url]

        entry = SnipeEntry(
            id=before.id,
            author_id=before.author.id,
            author_name=before.author.display_name,
            author_avatar=before.author.display_avatar.url if before.author.display_avatar else "",
            content=before.content,
            attachments=media,
            created_at=before.created_at,
            action_at=discord.utils.utcnow(),
            type="edit",
            before=before.content,
            after=after.content,
            guild_id=guild_id,
            channel_id=channel_id,
            channel_name=before.channel.name,
        )

        self.bot.snipe_cache[channel_id].appendleft(entry)
        self.bot.guild_snipe_cache[guild_id].appendleft(entry)

    @commands.hybrid_command(
        name="snipe",
        aliases=["sn"],
        description="View recently deleted messages in this channel.",
    )
    @commands.guild_only()
    async def snipe(self, ctx: CustomContext) -> None:
        """View recently deleted messages in this channel."""
        channel_id = ctx.channel.id
        all_entries: deque[SnipeEntry] = self.bot.snipe_cache.get(channel_id, deque())
        deleted_entries = [e for e in all_entries if e.type == "delete"]

        dot = getattr(self.bot, "custom_emojis", {}).get("heart_dot", "•")
        img_emoji = getattr(self.bot, "custom_emojis", {}).get("icons_image", "")
        file_emoji = getattr(self.bot, "custom_emojis", {}).get("icons_file", "")
        img_prefix = f"{img_emoji} " if img_emoji else ""
        file_prefix = f"{file_emoji} " if file_emoji else ""

        if not deleted_entries:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Sniped Messages • #{ctx.channel.name}**")
            container.add_separator(divider=True)
            container.add_text(f"> No recently deleted messages found in this channel.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        # Fetch recent deleted messages (all deleted within 3 minutes of latest, or up to top 5)
        latest_ts = deleted_entries[0].action_at.timestamp()
        recent_threshold = latest_ts - 180  # 3 minutes window
        entries_to_show = [
            e for e in deleted_entries
            if e.action_at.timestamp() >= recent_threshold
        ][:5]

        if not entries_to_show:
            entries_to_show = deleted_entries[:3]

        # Group messages by author in chronological order (oldest to newest)
        chrono_entries = list(reversed(entries_to_show))

        groups: list[dict[str, Any]] = []
        user_map: dict[int, dict[str, Any]] = {}

        for entry in chrono_entries:
            if entry.author_id not in user_map:
                group = {
                    "author_id": entry.author_id,
                    "author_name": entry.author_name,
                    "entries": [],
                }
                user_map[entry.author_id] = group
                groups.append(group)
            user_map[entry.author_id]["entries"].append(entry)

        container = KyroContainer(accent_color=None)
        container.add_text(f"**Sniped Messages • #{ctx.channel.name}**")
        container.add_separator(divider=True)

        media_to_render: list[str] = []
        body_sections: list[str] = []

        for group in groups:
            user_lines = [f"{dot} **{group['author_name']}**"]

            for entry in group["entries"]:
                has_media = bool(entry.attachments)
                raw_text = entry.content.strip() if entry.content else ""
                is_gif_link = (
                    "tenor.com" in raw_text
                    or "giphy.com" in raw_text
                    or raw_text.lower().split("?")[0].endswith(".gif")
                )

                # Format text content if present and not just a raw gif link that has media
                if raw_text and not (is_gif_link and has_media):
                    if "\n" in raw_text:
                        for line in raw_text.splitlines():
                            if line.strip():
                                user_lines.append(f"> `{line.strip()[:1000]}`")
                    else:
                        user_lines.append(f"> `{raw_text[:1000]}`")

                # Handle media (images / gifs / attachments)
                if has_media:
                    for att_url in entry.attachments:
                        clean_url = att_url.lower().split("?")[0]
                        if clean_url.endswith(".gif") or "tenor" in clean_url or "giphy" in clean_url:
                            if not raw_text or is_gif_link:
                                user_lines.append(f"> {img_prefix}`[GIF Attachment]`")
                        elif clean_url.endswith((".png", ".jpg", ".jpeg", ".webp")):
                            if not raw_text:
                                user_lines.append(f"> {img_prefix}`[Image Attachment]`")
                        else:
                            user_lines.append(f"> {file_prefix}[Attachment]({att_url})")

                        # Collect valid images/GIFs for media gallery
                        if clean_url.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                            if att_url not in media_to_render:
                                media_to_render.append(att_url)
                elif is_gif_link:
                    user_lines.append(f"> {img_prefix}`[GIF Attachment]`")
                    clean_u = raw_text.lower().split("?")[0]
                    if clean_u.endswith((".gif", ".png", ".jpg", ".jpeg", ".webp")):
                        if raw_text not in media_to_render:
                            media_to_render.append(raw_text)

            body_sections.append("\n".join(user_lines))

        container.add_text("\n\n".join(body_sections))

        # Render images/GIFs directly inside container (up to 2)
        for media_url in media_to_render[:2]:
            container.add_media(media_url)

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="clearsnipe",
        aliases=["csnipe"],
        description="Purge the deleted message snipe cache for this channel.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def clearsnipe(self, ctx: CustomContext) -> None:
        """Purge the deleted message snipe cache for this channel."""
        channel_id = ctx.channel.id
        count = len(self.bot.snipe_cache.get(channel_id, []))
        if channel_id in self.bot.snipe_cache:
            self.bot.snipe_cache[channel_id].clear()

        container = KyroContainer(accent_color=None)
        container.add_text(f"**Snipe Cache Cleared • #{ctx.channel.name}**")
        container.add_separator(divider=True)
        container.add_text(f"> Successfully purged `{count}` cached message(s).")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load SnipeCog into KyroBot."""
    await bot.add_cog(SnipeCog(bot))
