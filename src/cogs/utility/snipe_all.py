"""
Kyro Discord Bot - Server-Wide Snipe All Suite
Clean, focused overview of recently deleted messages across all server channels.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response
from src.cogs.utility.snipe import SnipeEntry

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class SnipeAllCog(commands.Cog, name="Utility-SnipeAll"):
    """Server-wide message retention auditor across all channels."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        if not hasattr(self.bot, "snipe_cache"):
            self.bot.snipe_cache = {}
        if not hasattr(self.bot, "guild_snipe_cache"):
            self.bot.guild_snipe_cache = {}

    @commands.hybrid_command(
        name="snipeall",
        aliases=["sall", "globalsnipe", "serversnipe"],
        description="Show recent deleted messages across all channels in the server.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def snipeall(self, ctx: CustomContext) -> None:
        """
        Show recent deleted messages across all channels in the server.
        Requires Manage Messages permission.
        """
        guild_id = ctx.guild.id
        all_entries: deque[SnipeEntry] = getattr(self.bot, "guild_snipe_cache", {}).get(guild_id, deque())
        deleted_entries = [e for e in all_entries if e.type == "delete"]

        dot = getattr(self.bot, "custom_emojis", {}).get("heart_dot", "•")
        img_emoji = getattr(self.bot, "custom_emojis", {}).get("icons_image", "")
        file_emoji = getattr(self.bot, "custom_emojis", {}).get("icons_file", "")
        img_prefix = f"{img_emoji} " if img_emoji else ""
        file_prefix = f"{file_emoji} " if file_emoji else ""

        if not deleted_entries:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Server Sniped Messages**")
            container.add_separator(divider=True)
            container.add_text(f"> No recently deleted messages tracked in **{ctx.guild.name}**.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        latest_ts = deleted_entries[0].action_at.timestamp()
        recent_threshold = latest_ts - 180  # 3 minutes window
        recent_entries = [
            e for e in deleted_entries
            if e.action_at.timestamp() >= recent_threshold
        ][:6]

        if not recent_entries:
            recent_entries = deleted_entries[:4]

        # Group messages by (channel_id, author_id) in chronological order
        chrono_entries = list(reversed(recent_entries))

        groups: list[dict[str, Any]] = []
        group_map: dict[tuple[int, int], dict[str, Any]] = {}

        for entry in chrono_entries:
            key = (entry.channel_id, entry.author_id)
            if key not in group_map:
                group = {
                    "author_name": entry.author_name,
                    "channel_id": entry.channel_id,
                    "channel_name": entry.channel_name,
                    "entries": [],
                }
                group_map[key] = group
                groups.append(group)
            group_map[key]["entries"].append(entry)

        container = KyroContainer(accent_color=None)
        title_text = "**Server Sniped Messages**"
        container.add_text(title_text)
        container.add_separator(divider=True)

        media_to_render: list[str] = []
        body_sections: list[str] = []

        for group in groups:
            ch_ref = f"<#{group['channel_id']}>" if group["channel_id"] else f"#{group['channel_name']}"
            user_lines = [f"{dot} **{group['author_name']}** in {ch_ref}"]

            for entry in group["entries"]:
                has_media = bool(entry.attachments)
                raw_text = entry.content.strip() if entry.content else ""
                is_gif_link = (
                    "tenor.com" in raw_text
                    or "giphy.com" in raw_text
                    or raw_text.lower().split("?")[0].endswith(".gif")
                )

                if raw_text and not (is_gif_link and has_media):
                    if "\n" in raw_text:
                        for line in raw_text.splitlines():
                            if line.strip():
                                user_lines.append(f"> {line.strip()[:1000]}")
                    else:
                        user_lines.append(f"> {raw_text[:1000]}")

                if has_media:
                    for att_url in entry.attachments:
                        clean_url = att_url.lower().split("?")[0]
                        if clean_url.endswith(".gif") or "tenor" in clean_url or "giphy" in clean_url:
                            if not raw_text or is_gif_link:
                                user_lines.append(f"> {img_prefix}[GIF Attachment]")
                        elif clean_url.endswith((".png", ".jpg", ".jpeg", ".webp")):
                            if not raw_text:
                                user_lines.append(f"> {img_prefix}[Image Attachment]")
                        else:
                            user_lines.append(f"> {file_prefix}[Attachment]({att_url})")

                        if clean_url.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                            if att_url not in media_to_render:
                                media_to_render.append(att_url)
                elif is_gif_link:
                    user_lines.append(f"> {img_prefix}[GIF Attachment]")
                    clean_u = raw_text.lower().split("?")[0]
                    if clean_u.endswith((".gif", ".png", ".jpg", ".jpeg", ".webp")):
                        if raw_text not in media_to_render:
                            media_to_render.append(raw_text)

            body_sections.append("\n".join(user_lines))

        container.add_text("\n\n".join(body_sections))

        for media_url in media_to_render[:2]:
            container.add_media(media_url)

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="clearsnipeall",
        aliases=["csnipeall", "wipesnipeall"],
        description="Wipe the server-wide deleted message cache.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def clearsnipeall(self, ctx: CustomContext) -> None:
        """Wipe the server-wide deleted message cache."""
        guild_id = ctx.guild.id
        count = len(getattr(self.bot, "guild_snipe_cache", {}).get(guild_id, []))
        if guild_id in getattr(self.bot, "guild_snipe_cache", {}):
            self.bot.guild_snipe_cache[guild_id].clear()

        container = KyroContainer(accent_color=None)
        container.add_text(f"**Server Snipe Cache Cleared**")
        container.add_separator(divider=True)
        container.add_text(f"> Successfully wiped `{count}` tracked server message(s) in **{ctx.guild.name}**.")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load SnipeAllCog into KyroBot."""
    await bot.add_cog(SnipeAllCog(bot))
