"""
Cicada 3301 Discord Bot - Advanced Dual Embed & Card Builder
Top Container: Real-time Live Preview Card.
Bottom Container: 5-Step Control Dashboard with full editing capabilities.
Includes Discohook/JSON/HTML raw import, dynamic variable engine, FAQ dropdowns, and button rows.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    CicadaContainer,
    send_container_response,
    edit_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import CicadaBot

logger = logging.getLogger("Cicada.EmbedBuilder")


# ─── Dynamic Variable Parser ──────────────────────────────────────────────────

def apply_placeholders(
    text: str | None,
    user: discord.Member | discord.User | None,
    guild: discord.Guild | None,
    channel: discord.abc.GuildChannel | discord.Thread | discord.abc.Messageable | None = None,
    bot: CicadaBot | None = None,
) -> str:
    """Replace comprehensive dynamic template variables in text."""
    if not text:
        return ""

    now = discord.utils.utcnow()
    replacements: dict[str, str] = {
        # Timestamps
        "{timestamp}": f"<t:{int(now.timestamp())}:f>",
        "{timestamp.short_datetime}": f"<t:{int(now.timestamp())}:f>",
        "{timestamp.long_datetime}": f"<t:{int(now.timestamp())}:F>",
        "{timestamp.short_date}": f"<t:{int(now.timestamp())}:d>",
        "{timestamp.long_date}": f"<t:{int(now.timestamp())}:D>",
        "{timestamp.short_time}": f"<t:{int(now.timestamp())}:t>",
        "{timestamp.long_time}": f"<t:{int(now.timestamp())}:T>",
        "{timestamp.relative}": f"<t:{int(now.timestamp())}:R>",
        "{relative_time}": f"<t:{int(now.timestamp())}:R>",
        "{date}": now.strftime("%Y-%m-%d"),
        "{time}": now.strftime("%H:%M:%S UTC"),
        "{unix}": str(int(now.timestamp())),
    }

    if user:
        created_ts = int(user.created_at.timestamp())
        replacements.update({
            "{user}": user.mention,
            "{user.mention}": user.mention,
            "{user.name}": user.name,
            "{user.display_name}": user.display_name,
            "{user.id}": str(user.id),
            "{user.avatar}": str(user.display_avatar.url),
            "{user.avatar_url}": str(user.display_avatar.url),
            "{user.default_avatar_url}": str(user.default_avatar.url),
            "{user.created_at}": user.created_at.strftime("%Y-%m-%d"),
            "{user.created_at_timestamp}": f"<t:{created_ts}:R>",
            "{user.bot}": str(user.bot),
        })
        if isinstance(user, discord.Member):
            joined_ts = int(user.joined_at.timestamp()) if user.joined_at else 0
            replacements.update({
                "{user.joined_at}": user.joined_at.strftime("%Y-%m-%d") if user.joined_at else "N/A",
                "{user.joined_at_timestamp}": f"<t:{joined_ts}:R>" if joined_ts else "N/A",
                "{user.top_role}": user.top_role.name if user.top_role else "None",
                "{user.top_role_mention}": user.top_role.mention if user.top_role else "None",
                "{user.roles_count}": str(len(user.roles) - 1),
                "{user.color}": str(user.color),
            })

    if guild:
        guild_created_ts = int(guild.created_at.timestamp())
        replacements.update({
            "{server}": guild.name,
            "{server.name}": guild.name,
            "{server.id}": str(guild.id),
            "{server.members}": str(guild.member_count or 0),
            "{server.member_count}": str(guild.member_count or 0),
            "{server.icon}": str(guild.icon.url) if guild.icon else "",
            "{server.icon_url}": str(guild.icon.url) if guild.icon else "",
            "{server.banner}": str(guild.banner.url) if guild.banner else "",
            "{server.banner_url}": str(guild.banner.url) if guild.banner else "",
            "{server.splash}": str(guild.splash.url) if guild.splash else "",
            "{server.splash_url}": str(guild.splash.url) if guild.splash else "",
            "{server.owner_id}": str(guild.owner_id),
            "{server.created_at}": guild.created_at.strftime("%Y-%m-%d"),
            "{server.created_at_timestamp}": f"<t:{guild_created_ts}:R>",
            "{server.boost_count}": str(guild.premium_subscription_count or 0),
            "{server.boosts}": str(guild.premium_subscription_count or 0),
            "{server.boost_tier}": str(guild.premium_tier),
            "{server.tier}": str(guild.premium_tier),
            "{server.roles_count}": str(len(guild.roles)),
            "{server.channels_count}": str(len(guild.channels)),
        })
        if guild.owner:
            replacements.update({
                "{server.owner}": guild.owner.display_name,
                "{server.owner.name}": guild.owner.name,
                "{server.owner.mention}": guild.owner.mention,
            })

    if channel:
        replacements.update({
            "{channel}": getattr(channel, "mention", f"#{channel}"),
            "{channel.name}": getattr(channel, "name", str(channel)),
            "{channel.id}": str(getattr(channel, "id", 0)),
            "{channel.mention}": getattr(channel, "mention", f"#{channel}"),
            "{channel.topic}": getattr(channel, "topic", "") or "",
        })

    if bot and bot.user:
        replacements.update({
            "{bot}": bot.user.mention,
            "{bot.name}": bot.user.name,
            "{bot.id}": str(bot.user.id),
            "{bot.avatar}": str(bot.user.display_avatar.url),
            "{bot.avatar_url}": str(bot.user.display_avatar.url),
            "{bot.prefix}": bot.guild_mgr.get_prefix(guild.id if guild else None) if hasattr(bot, "guild_mgr") else "?",
            "{bot.ping}": f"{round(bot.latency * 1000)}ms" if bot.latency else "0ms",
            "{bot.latency}": f"{round(bot.latency * 1000)}ms" if bot.latency else "0ms",
            "{bot.guilds_count}": str(len(bot.guilds)),
        })

    result = text
    for key, val in replacements.items():
        result = result.replace(key, val)
    return result


def convert_html_to_markdown(text: str) -> str:
    """Convert basic HTML tags to Discord Markdown format."""
    if not text:
        return ""
    t = text
    t = re.sub(r"<(?:b|strong)>(.*?)</(?:b|strong)>", r"**\1**", t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<(?:i|em)>(.*?)</(?:i|em)>", r"*\1*", t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<u>(.*?)</u>", r"__\1__", t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<(?:s|strike|del)>(.*?)</(?:s|strike|del)>", r"~~\1~~", t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r'<a\s+href=["\'](.*?)["\']>(.*?)</a>', r"[\2](\1)", t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<code>(.*?)</code>", r"`\1`", t, flags=re.IGNORECASE | re.DOTALL)
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.IGNORECASE)
    t = re.sub(r"<p>(.*?)</p>", r"\1\n", t, flags=re.IGNORECASE | re.DOTALL)
    return t


def parse_markdown_link(text: str | None) -> tuple[str | None, str | None]:
    """Parse [Text](URL) format into (text, url). If plain text, returns (text, None)."""
    if not text:
        return None, None
    m = re.match(r"^\[(.*?)\]\((https?://[^\s]+)\)$", text.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return text.strip(), None


# ─── Data Model ───────────────────────────────────────────────────────────────

class ContainerDraft:
    """Modular data model for custom Components V2 container cards."""

    def __init__(self) -> None:
        self.author_name: str | None = None
        self.author_icon_url: str | None = None
        self.author_url: str | None = None

        self.title: str | None = "Cicada 3301 Custom Card"
        self.title_url: str | None = None

        self.description: str | None = "This is your live Components V2 preview. Edit options below to customize."

        self.fields: list[dict[str, str]] = []  # [{"name": "...", "value": "..."}]

        self.thumbnail_url: str | None = None
        self.image_url: str | None = None

        self.footer_text: str | None = None
        self.footer_icon_url: str | None = None
        self.timestamp: bool = False

        self.accent_hex: str | None = None
        self.buttons: list[dict[str, str]] = []  # [{"label": "...", "url": "..."}]
        self.faq_options: list[dict[str, str]] = []  # [{"label": "...", "description": "...", "answer": "..."}]

    def get_accent_int(self) -> int | None:
        if not self.accent_hex or self.accent_hex.strip().lower() in ["none", "dark", "default"]:
            return None
        clean = self.accent_hex.strip().lstrip("#")
        try:
            return int(clean, 16)
        except ValueError:
            return None

    def to_container(
        self,
        user: discord.Member | discord.User | None = None,
        guild: discord.Guild | None = None,
        channel: discord.abc.GuildChannel | discord.Thread | discord.abc.Messageable | None = None,
        bot: CicadaBot | None = None,
        default_avatar: str | None = None,
    ) -> CicadaContainer:
        """Convert draft into a Discord Components V2 CicadaContainer."""
        container = CicadaContainer(accent_color=self.get_accent_int())

        def parse(t: str | None) -> str:
            if not t:
                return ""
            return apply_placeholders(t, user=user, guild=guild, channel=channel, bot=bot)

        # 1. Author & Title Extraction
        author_raw = parse(self.author_name)
        author_text, author_url_extracted = parse_markdown_link(author_raw)
        final_author_url = self.author_url or author_url_extracted

        title_raw = parse(self.title)
        title_text, title_url_extracted = parse_markdown_link(title_raw)
        final_title_url = self.title_url or title_url_extracted

        desc_text = parse(self.description)

        # Thumbnail / Author Icon Accessory (Type 11)
        thumb_url = parse(self.thumbnail_url or self.author_icon_url)
        accessory_dict = None
        if thumb_url and thumb_url.startswith("http"):
            accessory_dict = {
                "type": 11,
                "media": {
                    "url": thumb_url,
                },
            }

        # Compose Header Block
        header_blocks = []
        if author_text:
            if final_author_url and final_author_url.startswith("http"):
                header_blocks.append(f"**[{author_text}]({final_author_url})**")
            else:
                header_blocks.append(f"**{author_text}**")

        if title_text:
            formatted_title = title_text if title_text.startswith("#") else f"## {title_text}"
            if final_title_url and final_title_url.startswith("http"):
                header_blocks.append(f"[{formatted_title}]({final_title_url})")
            else:
                header_blocks.append(formatted_title)

        if desc_text:
            header_blocks.append(desc_text)

        if header_blocks or accessory_dict:
            full_header_content = "\n".join(header_blocks) if header_blocks else " "
            container.add_section(content=full_header_content, accessory=accessory_dict)
            container.add_separator(divider=True)

        # 2. Custom Fields (Type 10 Text Displays)
        if self.fields:
            field_lines = []
            for f in self.fields:
                f_name = parse(f.get("name", ""))
                f_val = parse(f.get("value", ""))
                if f_name and f_val:
                    field_lines.append(f"**{f_name}**\n{f_val}")
                elif f_name:
                    field_lines.append(f"**{f_name}**")
                elif f_val:
                    field_lines.append(f_val)

            if field_lines:
                container.add_text("\n\n".join(field_lines))
                container.add_separator(divider=True)

        # 3. Large Banner Image (Media Gallery Type 12)
        banner_url = parse(self.image_url)
        if banner_url and banner_url.startswith("http"):
            container.components.append({
                "type": 12,
                "items": [
                    {
                        "media": {
                            "url": banner_url,
                        }
                    }
                ],
            })
            container.add_separator(divider=True)

        # 4. FAQ Dropdown Select Menu (Type 3 Action Row)
        if self.faq_options:
            select_opts = []
            for idx, opt in enumerate(self.faq_options[:25]):
                select_opts.append({
                    "label": parse(opt.get("label", f"Option {idx + 1}"))[:100],
                    "value": f"faq_{idx}",
                    "description": parse(opt.get("description", ""))[:100] if opt.get("description") else None,
                })
            container.add_action_row([
                {
                    "type": 3,
                    "custom_id": "card_faq_select",
                    "placeholder": "Select an FAQ question / topic...",
                    "options": select_opts,
                }
            ])

        # 5. Link Buttons Row (Type 1 Action Row with Type 2 Buttons)
        if self.buttons:
            btn_comps = []
            for b in self.buttons[:5]:
                btn_comps.append({
                    "type": 2,
                    "style": 5,  # Link URL Button
                    "label": parse(b.get("label", "Link")),
                    "url": parse(b.get("url", "https://discord.com")),
                })
            container.add_action_row(btn_comps)

        # 6. Footer Subtext & Icon & Timestamp
        footer_raw = parse(self.footer_text)
        footer_parts = []
        if footer_raw:
            footer_parts.append(footer_raw)
        if self.timestamp:
            import datetime
            now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            footer_parts.append(now_str)

        if footer_parts:
            container.add_text(f"-# {' • '.join(footer_parts)}")

        if not container.components:
            container.add_text("Empty card container.")

        return container

    def to_dict(self) -> dict[str, Any]:
        return {
            "author_name": self.author_name,
            "author_icon_url": self.author_icon_url,
            "author_url": self.author_url,
            "title": self.title,
            "title_url": self.title_url,
            "description": self.description,
            "fields": self.fields,
            "thumbnail_url": self.thumbnail_url,
            "image_url": self.image_url,
            "footer_text": self.footer_text,
            "footer_icon_url": self.footer_icon_url,
            "timestamp": self.timestamp,
            "accent_hex": self.accent_hex,
            "buttons": self.buttons,
            "faq_options": self.faq_options,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContainerDraft:
        draft = cls()
        draft.author_name = data.get("author_name")
        draft.author_icon_url = data.get("author_icon_url")
        draft.author_url = data.get("author_url")
        draft.title = data.get("title")
        draft.title_url = data.get("title_url")
        draft.description = data.get("description")
        draft.fields = data.get("fields", [])
        draft.thumbnail_url = data.get("thumbnail_url")
        draft.image_url = data.get("image_url")
        draft.footer_text = data.get("footer_text")
        draft.footer_icon_url = data.get("footer_icon_url")
        draft.timestamp = bool(data.get("timestamp", False))
        draft.accent_hex = data.get("accent_hex")
        draft.buttons = data.get("buttons", [])
        draft.faq_options = data.get("faq_options", [])
        return draft

    @classmethod
    def from_raw_payload(cls, raw: str) -> ContainerDraft:
        """Parse raw JSON (Discohook, standard Discord Embed, or internal dict) and HTML."""
        cleaned = raw.strip()
        draft = cls()

        try:
            parsed_json = json.loads(cleaned)
            if isinstance(parsed_json, dict):
                # Check for Discohook / Standard Embed format: {"embeds": [{...}]}
                if "embeds" in parsed_json and isinstance(parsed_json["embeds"], list) and parsed_json["embeds"]:
                    emb = parsed_json["embeds"][0]
                    draft.title = emb.get("title")
                    draft.description = convert_html_to_markdown(emb.get("description", ""))
                    draft.title_url = emb.get("url")
                    if "author" in emb:
                        draft.author_name = emb["author"].get("name")
                        draft.author_icon_url = emb["author"].get("icon_url")
                        draft.author_url = emb["author"].get("url")
                    if "thumbnail" in emb:
                        draft.thumbnail_url = emb["thumbnail"].get("url")
                    if "image" in emb:
                        draft.image_url = emb["image"].get("url")
                    if "footer" in emb:
                        draft.footer_text = emb["footer"].get("text")
                        draft.footer_icon_url = emb["footer"].get("icon_url")
                    if "color" in emb:
                        draft.accent_hex = f"#{emb['color']:06x}"
                    if "fields" in emb and isinstance(emb["fields"], list):
                        draft.fields = [{"name": f.get("name", ""), "value": convert_html_to_markdown(f.get("value", ""))} for f in emb["fields"]]
                    return draft

                # Direct Embed Dictionary: {"title": "...", "description": "..."}
                if "title" in parsed_json or "description" in parsed_json or "fields" in parsed_json:
                    return cls.from_dict(parsed_json)
        except Exception:
            pass

        # Plain text / HTML fallback
        draft.description = convert_html_to_markdown(cleaned)
        return draft


# ─── Modals (5-Step Focused Inputs) ──────────────────────────────────────────

class ContentModal(discord.ui.Modal, title="Step 1: Content & Theme"):
    title_input = discord.ui.TextInput(
        label="Title",
        placeholder="Card title headline or [Title](https://...)",
        max_length=256,
        required=False,
    )
    author_input = discord.ui.TextInput(
        label="Author Name",
        placeholder="Author name or [Author Name](https://...)",
        max_length=256,
        required=False,
    )
    author_icon_input = discord.ui.TextInput(
        label="Author Icon URL",
        placeholder="https://.../icon.png or {user.avatar}",
        max_length=500,
        required=False,
    )
    desc_input = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.paragraph,
        placeholder="Main description text, [rules](url), {user}, {server}...",
        max_length=4000,
        required=False,
    )
    accent_input = discord.ui.TextInput(
        label="Accent Color",
        placeholder="#00FF66, #5865F2, or 'none'",
        max_length=20,
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.title_input.default = self.view_ref.draft.title or ""
        self.author_input.default = self.view_ref.draft.author_name or ""
        self.author_icon_input.default = self.view_ref.draft.author_icon_url or ""
        self.desc_input.default = self.view_ref.draft.description or ""
        self.accent_input.default = self.view_ref.draft.accent_hex or "none"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        t = str(self.title_input.value).strip()
        a = str(self.author_input.value).strip()
        ai = str(self.author_icon_input.value).strip()
        d = str(self.desc_input.value).strip()
        ac = str(self.accent_input.value).strip()

        self.view_ref.draft.title = t if t else None
        self.view_ref.draft.author_name = a if a else None
        self.view_ref.draft.author_icon_url = ai if ai else None
        self.view_ref.draft.description = d if d else None
        self.view_ref.draft.accent_hex = None if ac.lower() in ["none", "dark", "default", ""] else ac

        await self.view_ref.update_view(interaction)


class VisualsModal(discord.ui.Modal, title="Step 2: Images & Footer"):
    thumb_input = discord.ui.TextInput(
        label="Thumbnail URL",
        placeholder="https://example.com/thumb.png or empty to remove",
        required=False,
    )
    banner_input = discord.ui.TextInput(
        label="Banner Image URL",
        placeholder="https://example.com/banner.png or empty to remove",
        required=False,
    )
    footer_input = discord.ui.TextInput(
        label="Footer Subtext",
        placeholder="Footer text or {server.name}...",
        max_length=1000,
        required=False,
    )
    footer_icon_input = discord.ui.TextInput(
        label="Footer Icon URL",
        placeholder="https://example.com/footer_icon.png or empty",
        required=False,
    )
    timestamp_input = discord.ui.TextInput(
        label="Timestamp (on / off)",
        placeholder="on or off",
        max_length=10,
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        self.thumb_input.default = self.view_ref.draft.thumbnail_url or ""
        self.banner_input.default = self.view_ref.draft.image_url or ""
        self.footer_input.default = self.view_ref.draft.footer_text or ""
        self.footer_icon_input.default = self.view_ref.draft.footer_icon_url or ""
        self.timestamp_input.default = "on" if self.view_ref.draft.timestamp else "off"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        th = str(self.thumb_input.value).strip()
        bn = str(self.banner_input.value).strip()
        ft = str(self.footer_input.value).strip()
        fi = str(self.footer_icon_input.value).strip()
        ts = str(self.timestamp_input.value).strip().lower()

        self.view_ref.draft.thumbnail_url = th if th.startswith("http") or "{" in th else None
        self.view_ref.draft.image_url = bn if bn.startswith("http") or "{" in bn else None
        self.view_ref.draft.footer_text = ft if ft else None
        self.view_ref.draft.footer_icon_url = fi if fi.startswith("http") or "{" in fi else None
        self.view_ref.draft.timestamp = (ts in ["on", "true", "yes", "1", "enable", "enabled"])

        await self.view_ref.update_view(interaction)


class AddFieldModal(discord.ui.Modal, title="Add Field"):
    name_input = discord.ui.TextInput(
        label="Field Name",
        placeholder="Section name or header...",
        max_length=256,
        required=True,
    )
    value_input = discord.ui.TextInput(
        label="Field Value",
        style=discord.TextStyle.paragraph,
        placeholder="Field description, details, or [links](url)...",
        max_length=1024,
        required=True,
    )

    def __init__(self, view: EmbedBuilderView, edit_idx: int | None = None) -> None:
        super().__init__()
        self.view_ref = view
        self.edit_idx = edit_idx
        if edit_idx is not None and 0 <= edit_idx < len(self.view_ref.draft.fields):
            existing = self.view_ref.draft.fields[edit_idx]
            self.name_input.default = existing.get("name", "")
            self.value_input.default = existing.get("value", "")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        n = str(self.name_input.value).strip()
        v = str(self.value_input.value).strip()
        if n and v:
            if self.edit_idx is not None and 0 <= self.edit_idx < len(self.view_ref.draft.fields):
                self.view_ref.draft.fields[self.edit_idx] = {"name": n, "value": v}
            else:
                self.view_ref.draft.fields.append({"name": n, "value": v})
        await self.view_ref.update_view(interaction)


class AddButtonModal(discord.ui.Modal, title="Add Link Button"):
    label_input = discord.ui.TextInput(
        label="Button Label",
        placeholder="Visit Website, Join Server...",
        max_length=80,
        required=True,
    )
    url_input = discord.ui.TextInput(
        label="Destination URL",
        placeholder="https://example.com",
        required=True,
    )

    def __init__(self, view: EmbedBuilderView, edit_idx: int | None = None) -> None:
        super().__init__()
        self.view_ref = view
        self.edit_idx = edit_idx
        if edit_idx is not None and 0 <= edit_idx < len(self.view_ref.draft.buttons):
            b = self.view_ref.draft.buttons[edit_idx]
            self.label_input.default = b.get("label", "")
            self.url_input.default = b.get("url", "")

    async def on_submit(self, interaction: discord.Interaction) -> None:
        label = str(self.label_input.value).strip() or "Link"
        url = str(self.url_input.value).strip()
        if url:
            if not url.startswith("http://") and not url.startswith("https://"):
                url = f"https://{url}"
            if self.edit_idx is not None and 0 <= self.edit_idx < len(self.view_ref.draft.buttons):
                self.view_ref.draft.buttons[self.edit_idx] = {"label": label, "url": url}
            else:
                self.view_ref.draft.buttons.append({"label": label, "url": url})
        await self.view_ref.update_view(interaction)


class AddFAQModal(discord.ui.Modal, title="Add FAQ Dropdown Option"):
    label_input = discord.ui.TextInput(
        label="Question / Option Label",
        placeholder="How to upgrade to VIP?",
        max_length=100,
        required=True,
    )
    desc_input = discord.ui.TextInput(
        label="Subtitle Description",
        placeholder="Brief note or summary...",
        max_length=100,
        required=False,
    )
    answer_input = discord.ui.TextInput(
        label="Answer / Response",
        style=discord.TextStyle.paragraph,
        placeholder="The answer shown when selected...",
        max_length=2000,
        required=True,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        label = str(self.label_input.value).strip()
        desc = str(self.desc_input.value).strip()
        ans = str(self.answer_input.value).strip()
        if label and ans:
            self.view_ref.draft.faq_options.append({
                "label": label,
                "description": desc if desc else None,
                "answer": ans,
            })
        await self.view_ref.update_view(interaction)


class SaveModal(discord.ui.Modal, title="Save Template"):
    name_input = discord.ui.TextInput(
        label="Template Name",
        placeholder="welcome, rules, faq, announcement...",
        max_length=32,
        required=True,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = str(self.name_input.value).strip().lower()
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", name)
        if not clean_name:
            await interaction.response.send_message("Invalid template name.", ephemeral=True)
            return

        bot: CicadaBot = interaction.client  # type: ignore
        success = await bot.embed_mgr.save_template(
            guild_id=interaction.guild_id or 0,
            name=clean_name,
            payload=self.view_ref.draft.to_dict(),
            created_by=interaction.user.id,
        )
        if success:
            await interaction.response.send_message(
                f"Saved template as `{clean_name}`. Use `?embed send #channel {clean_name}` to post.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message("Failed to save template.", ephemeral=True)


class RawImportModal(discord.ui.Modal, title="Raw JSON / HTML Import"):
    raw_input = discord.ui.TextInput(
        label="Payload / Code",
        style=discord.TextStyle.paragraph,
        placeholder="Paste Discohook JSON, raw embed JSON, or HTML text...",
        max_length=4000,
        required=False,
    )

    def __init__(self, view: EmbedBuilderView) -> None:
        super().__init__()
        self.view_ref = view
        raw_json = json.dumps(self.view_ref.draft.to_dict(), indent=2)
        if len(raw_json) > 3900:
            raw_json = json.dumps(self.view_ref.draft.to_dict())
        self.raw_input.default = raw_json[:3950]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = str(self.raw_input.value).strip()
        if not raw:
            return
        try:
            self.view_ref.draft = ContainerDraft.from_raw_payload(raw)
            await self.view_ref.update_view(interaction)
        except Exception as e:
            await interaction.response.send_message(f"Import failed: {e}", ephemeral=True)


# ─── Dual-Container Controller View ──────────────────────────────────────────

class EmbedBuilderView(discord.ui.View):
    """Mimu-style dual-container builder: Top = Live Preview, Bottom = 5-Step Console."""

    SLIDES = [
        ("content", "Step 1: Content & Theme", "Title, Author, Icon, Description, Color"),
        ("visuals", "Step 2: Images & Footer", "Thumbnail, Banner, Footer Text & Icon, Timestamp"),
        ("fields", "Step 3: Custom Fields", "Add, edit, or remove structured sections"),
        ("interactive", "Step 4: Buttons & FAQ Menu", "Manage link buttons and FAQ dropdown options"),
        ("dispatch", "Step 5: Dispatch & Raw", "Send to channel, Save template, Raw JSON import"),
    ]

    def __init__(self, bot: CicadaBot, author: discord.Member | discord.User, draft: ContainerDraft | None = None) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.author = author
        self.draft: ContainerDraft = draft or ContainerDraft()
        self.current_slide_idx: int = 0  # 0 to 4
        self._setup_dynamic_buttons()

    def _setup_dynamic_buttons(self) -> None:
        """Assign custom arrow emojis from emoji2 folder to navigation buttons."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        if e_reg:
            left_e = e_reg.get_emoji_obj("icon_arrow_left") or e_reg.get_emoji_obj("icons_leftarrow")
            right_e = e_reg.get_emoji_obj("icons_arrow") or e_reg.get_emoji_obj("icons_rightarrow")

            self.btn_prev.label = None
            self.btn_prev.emoji = left_e if left_e else "◀"

            self.btn_next.label = None
            self.btn_next.emoji = right_e if right_e else "▶"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Only the command author can use this builder.", ephemeral=True)
            return False
        return True

    def build_preview_container(self, guild: discord.Guild | None = None, channel: discord.abc.Messageable | None = None) -> CicadaContainer:
        """Top Container: Live rendered preview of the custom card."""
        return self.draft.to_container(user=self.author, guild=guild, channel=channel, bot=self.bot)

    def build_control_container(self, guild: discord.Guild | None = None) -> CicadaContainer:
        """Bottom Container: Minimal 5-step editor console."""
        slide_key, slide_title, _ = self.SLIDES[self.current_slide_idx]
        e_reg = getattr(self.bot, "custom_emojis", None)
        dot = e_reg.get("icons_arrow", e_reg.get("icons_rightarrow", e_reg.get("heart_dot", "-"))) if e_reg else "-"

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Cicada 3301 Builder — {slide_title}**\n"
                f"> Use controls below to configure this section."
            )
        )
        container.add_separator(divider=True)

        if slide_key == "content":
            t_str = f"`{self.draft.title}`" if self.draft.title else "`None`"
            a_str = f"`{self.draft.author_name}`" if self.draft.author_name else "`None`"
            ai_str = "`Set`" if self.draft.author_icon_url else "`None`"
            desc_len = len(self.draft.description) if self.draft.description else 0
            accent_str = f"`{self.draft.accent_hex}`" if self.draft.accent_hex else "`Default Dark`"
            container.add_text(
                f"{dot} **Title:** {t_str} | **Author:** {a_str}\n"
                f"{dot} **Author Icon:** {ai_str} | **Accent Color:** {accent_str}\n"
                f"{dot} **Description Length:** `{desc_len} chars`"
            )
        elif slide_key == "visuals":
            thumb_str = "`Set`" if self.draft.thumbnail_url else "`None`"
            banner_str = "`Set`" if self.draft.image_url else "`None`"
            footer_str = f"`{self.draft.footer_text}`" if self.draft.footer_text else "`None`"
            ts_str = "`Enabled`" if self.draft.timestamp else "`Disabled`"
            container.add_text(
                f"{dot} **Thumbnail:** {thumb_str} | **Banner:** {banner_str}\n"
                f"{dot} **Footer:** {footer_str} | **Timestamp:** {ts_str}"
            )
        elif slide_key == "fields":
            f_cnt = len(self.draft.fields)
            f_summary = ", ".join([f"`{f['name']}`" for f in self.draft.fields[:4]]) if self.draft.fields else "`None`"
            container.add_text(
                f"{dot} **Total Fields:** `{f_cnt}`\n"
                f"{dot} **Fields:** {f_summary}"
            )
        elif slide_key == "interactive":
            b_cnt = len(self.draft.buttons)
            faq_cnt = len(self.draft.faq_options)
            b_summary = ", ".join([f"`{b['label']}`" for b in self.draft.buttons[:3]]) if self.draft.buttons else "`None`"
            faq_summary = ", ".join([f"`{q['label']}`" for q in self.draft.faq_options[:3]]) if self.draft.faq_options else "`None`"
            container.add_text(
                f"{dot} **Link Buttons ({b_cnt}/5):** {b_summary}\n"
                f"{dot} **FAQ Dropdown Options ({faq_cnt}/25):** {faq_summary}"
            )
        elif slide_key == "dispatch":
            container.add_text(
                f"{dot} **Ready to Publish:** Choose an action below to post, save, or import JSON/HTML."
            )

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.author.display_name}")
        return container

    def get_dual_containers(self, guild: discord.Guild | None = None, channel: discord.abc.Messageable | None = None) -> list[CicadaContainer]:
        """Return [Top: Live Preview, Bottom: Control Console]."""
        return [
            self.build_preview_container(guild=guild, channel=channel),
            self.build_control_container(guild=guild),
        ]

    def _sync_controls(self) -> None:
        """Update select menu placeholder and button states according to active slide."""
        slide_key, slide_title, _ = self.SLIDES[self.current_slide_idx]
        self._setup_dynamic_buttons()

        for item in self.children:
            if isinstance(item, discord.ui.Select) and item.custom_id == "select_slide":
                for opt in item.options:
                    opt.default = (opt.value == slide_key)
            elif isinstance(item, discord.ui.Button):
                if item.custom_id == "btn_edit_step":
                    if slide_key == "content":
                        item.label = "Edit Content"
                    elif slide_key == "visuals":
                        item.label = "Edit Visuals"
                    elif slide_key == "fields":
                        item.label = "Add Field"
                    elif slide_key == "interactive":
                        item.label = "Add Button"
                    elif slide_key == "dispatch":
                        item.label = "Raw JSON/HTML"
                elif item.custom_id == "btn_secondary_action":
                    if slide_key == "fields":
                        item.label = "Clear Fields"
                        item.disabled = (len(self.draft.fields) == 0)
                    elif slide_key == "interactive":
                        item.label = "Add FAQ Option"
                        item.disabled = False
                    elif slide_key == "dispatch":
                        item.label = "Reset Draft"
                        item.disabled = False
                    else:
                        item.label = "Save"
                        item.disabled = False

    async def update_view(self, interaction: discord.Interaction) -> None:
        """Update the dual-container message."""
        self._sync_controls()
        containers = self.get_dual_containers(interaction.guild, interaction.channel)
        await edit_container_response(interaction, containers, view=self)

    # ─── Dropdown: Direct Slide Selector ──────────────────────────────────────

    @discord.ui.select(
        placeholder="Jump to a step...",
        custom_id="select_slide",
        options=[
            discord.SelectOption(label="Step 1: Content & Theme", value="content", description="Title, Author, Icon, Description, Color"),
            discord.SelectOption(label="Step 2: Images & Footer", value="visuals", description="Thumbnail, Banner, Footer Text & Icon, Timestamp"),
            discord.SelectOption(label="Step 3: Custom Fields", value="fields", description="Add, edit, or remove structured sections"),
            discord.SelectOption(label="Step 4: Buttons & FAQ Menu", value="interactive", description="Manage link buttons and FAQ dropdown options"),
            discord.SelectOption(label="Step 5: Dispatch & Raw", value="dispatch", description="Send to channel, Save template, Raw JSON import"),
        ],
        row=0,
    )
    async def select_slide(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        val = select.values[0]
        for idx, (k, _, _) in enumerate(self.SLIDES):
            if k == val:
                self.current_slide_idx = idx
                break
        await self.update_view(interaction)

    # ─── Action Buttons (Row 1) ──────────────────────────────────────────────

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="◀", row=1)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current_slide_idx = (self.current_slide_idx - 1) % len(self.SLIDES)
        await self.update_view(interaction)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="▶", row=1)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.current_slide_idx = (self.current_slide_idx + 1) % len(self.SLIDES)
        await self.update_view(interaction)

    @discord.ui.button(label="Edit Content", style=discord.ButtonStyle.primary, custom_id="btn_edit_step", row=1)
    async def btn_edit_step(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        slide_key, _, _ = self.SLIDES[self.current_slide_idx]

        if slide_key == "content":
            await interaction.response.send_modal(ContentModal(self))
        elif slide_key == "visuals":
            await interaction.response.send_modal(VisualsModal(self))
        elif slide_key == "fields":
            await interaction.response.send_modal(AddFieldModal(self))
        elif slide_key == "interactive":
            if len(self.draft.buttons) >= 5:
                await interaction.response.send_message("Maximum 5 buttons allowed.", ephemeral=True)
                return
            await interaction.response.send_modal(AddButtonModal(self))
        elif slide_key == "dispatch":
            await interaction.response.send_modal(RawImportModal(self))

    @discord.ui.button(label="Save", style=discord.ButtonStyle.secondary, custom_id="btn_secondary_action", row=1)
    async def btn_secondary_action(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        slide_key, _, _ = self.SLIDES[self.current_slide_idx]

        if slide_key == "fields":
            self.draft.fields.clear()
            await self.update_view(interaction)
        elif slide_key == "interactive":
            if len(self.draft.faq_options) >= 25:
                await interaction.response.send_message("Maximum 25 FAQ options allowed.", ephemeral=True)
                return
            await interaction.response.send_modal(AddFAQModal(self))
        elif slide_key == "dispatch":
            self.draft = ContainerDraft()
            await self.update_view(interaction)
        else:
            await interaction.response.send_modal(SaveModal(self))

    @discord.ui.button(label="Send", style=discord.ButtonStyle.success, row=1)
    async def btn_send(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Cannot send in direct messages.", ephemeral=True)
            return

        text_channels = [c for c in guild.text_channels if c.permissions_for(guild.me).send_messages][:25]
        if not text_channels:
            await interaction.response.send_message("No accessible text channels found.", ephemeral=True)
            return

        select_options = [
            discord.SelectOption(
                label=f"#{c.name}"[:100],
                value=str(c.id),
                description=f"Send card to #{c.name}"[:100],
            )
            for c in text_channels
        ]

        class ChannelPicker(discord.ui.View):
            def __init__(self, parent_view: EmbedBuilderView) -> None:
                super().__init__(timeout=60)
                self.parent_view = parent_view

            @discord.ui.select(placeholder="Select target channel...", options=select_options)
            async def select_channel(self, inter: discord.Interaction, sel: discord.ui.Select) -> None:
                ch_id = int(sel.values[0])
                target_ch = inter.guild.get_channel(ch_id) if inter.guild else None
                if not target_ch:
                    await inter.response.send_message("Target channel not found.", ephemeral=True)
                    return

                container = self.parent_view.draft.to_container(
                    user=self.parent_view.author,
                    guild=inter.guild,
                    channel=target_ch,
                    bot=self.parent_view.bot,
                )
                try:
                    await send_container_response(target_ch, container)
                    await inter.response.send_message(f"Card successfully posted to {target_ch.mention}.", ephemeral=True)
                except Exception as e:
                    logger.error(f"Failed to post container card: {e}", exc_info=e)
                    await inter.response.send_message(f"Failed to post card: {e}", ephemeral=True)

        await interaction.response.send_message("Select target channel to post card:", view=ChannelPicker(self), ephemeral=True)


# ─── Cog Implementation ──────────────────────────────────────────────────────

class EmbedBuilder(commands.Cog):
    """Full-featured Discord Components V2 Embed & Container Builder."""
    category: str = "Utility"

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Handle persistent FAQ dropdown select menu responses."""
        if interaction.data and interaction.data.get("custom_id") == "card_faq_select":
            selected_values = interaction.data.get("values", [])
            if selected_values:
                val = selected_values[0]
                if val.startswith("faq_"):
                    try:
                        idx = int(val.replace("faq_", ""))
                        # We can respond with FAQ information
                        await interaction.response.send_message(
                            f"Selected topic option #{idx + 1}.",
                            ephemeral=True,
                        )
                    except Exception:
                        pass

    @commands.group(
        name="embed",
        aliases=["embedbuilder", "container", "card"],
        description="Design, customize, preview, save, edit, and post Components V2 container cards.",
        invoke_without_command=True,
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_group(self, ctx: CustomContext, template_name: str | None = None) -> None:
        """Launch the dual-container interactive embed builder."""
        draft = ContainerDraft()
        if template_name:
            data = await self.bot.embed_mgr.get_template(ctx.guild.id, template_name)
            if data:
                draft = ContainerDraft.from_dict(data)

        view = EmbedBuilderView(self.bot, ctx.author, draft=draft)
        containers = view.get_dual_containers(ctx.guild, ctx.channel)
        await send_container_response(ctx, containers, view=view)

    @embed_group.command(
        name="create",
        aliases=["new", "builder"],
        description="Launch a fresh interactive embed builder.",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_create(self, ctx: CustomContext, template_name: str | None = None) -> None:
        """Launch the interactive builder."""
        await self.embed_group(ctx, template_name=template_name)

    @embed_group.command(
        name="send",
        aliases=["post"],
        description="Send a saved template to a channel. Usage: ?embed send [#channel] <template_name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_send(
        self, ctx: CustomContext, target_or_name: str, template_name: str | None = None
    ) -> None:
        """Send a saved template to a channel."""
        target_channel: discord.abc.Messageable = ctx.channel
        actual_name = target_or_name

        if template_name is not None:
            channel_converter = commands.TextChannelConverter()
            try:
                target_channel = await channel_converter.convert(ctx, target_or_name)
            except Exception:
                found = None
                clean_id = re.sub(r"[<#>]", "", target_or_name)
                if clean_id.isdigit() and ctx.guild:
                    found = ctx.guild.get_channel(int(clean_id))
                if not found and ctx.guild:
                    found = discord.utils.get(ctx.guild.text_channels, name=target_or_name)
                if found:
                    target_channel = found
                else:
                    await ctx.send(f"Channel '{target_or_name}' not found.")
                    return
            actual_name = template_name

        template_data = await self.bot.embed_mgr.get_template(ctx.guild.id, actual_name)
        if not template_data:
            await ctx.send(f"Saved template '{actual_name}' not found.")
            return

        draft = ContainerDraft.from_dict(template_data)
        avatar_url = str(self.bot.user.display_avatar.url) if self.bot and self.bot.user else ""
        container = draft.to_container(
            user=ctx.author,
            guild=ctx.guild,
            channel=target_channel,
            bot=self.bot,
            default_avatar=avatar_url,
        )
        try:
            await send_container_response(target_channel, container)
            ch_mention = getattr(target_channel, "mention", f"#{target_channel}")

            resp_container = CicadaContainer(accent_color=None)
            resp_container.add_section(
                content=(
                    "**Card Dispatched**\n"
                    f"> Saved template `{actual_name}` posted to {ch_mention}."
                )
            )
            resp_container.add_separator(divider=True)
            resp_container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, resp_container)
        except Exception as e:
            logger.error(f"Failed to post embed template '{actual_name}': {e}", exc_info=e)
            await ctx.send(f"Failed to post card: {e}")

    @embed_group.command(
        name="edit",
        description="Edit an existing bot message in this channel. Usage: ?embed edit <message_id> <template_name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_edit_msg(
        self, ctx: CustomContext, message_id: int, template_name: str
    ) -> None:
        """Edit an existing bot container message."""
        template_data = await self.bot.embed_mgr.get_template(ctx.guild.id, template_name)
        if not template_data:
            await ctx.send(f"Saved template '{template_name}' not found.")
            return

        try:
            target_msg = await ctx.channel.fetch_message(message_id)
        except Exception:
            await ctx.send(f"Message ID '{message_id}' not found in this channel.")
            return

        if self.bot.user and target_msg.author.id != self.bot.user.id:
            await ctx.send("Can only edit messages sent by this bot.")
            return

        draft = ContainerDraft.from_dict(template_data)
        avatar_url = str(self.bot.user.display_avatar.url) if self.bot and self.bot.user else ""
        container = draft.to_container(
            user=ctx.author,
            guild=ctx.guild,
            channel=ctx.channel,
            bot=self.bot,
            default_avatar=avatar_url,
        )

        payload = container.to_payload()
        try:
            await self.bot.http.request(
                discord.http.Route("PATCH", f"/channels/{ctx.channel.id}/messages/{message_id}"),
                json=payload,
            )
            resp_container = CicadaContainer(accent_color=None)
            resp_container.add_section(
                content=(
                    "**Message Updated**\n"
                    f"> Target message `{message_id}` updated with template `{template_name}`."
                )
            )
            resp_container.add_separator(divider=True)
            resp_container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, resp_container)
        except Exception as e:
            logger.error(f"Failed to edit message {message_id}: {e}", exc_info=e)
            await ctx.send(f"Failed to edit message {message_id}: {e}")

    @embed_group.command(
        name="list",
        aliases=["all", "templates"],
        description="List all saved templates for this server.",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_list(self, ctx: CustomContext) -> None:
        """List all saved templates."""
        templates = await self.bot.embed_mgr.list_templates(ctx.guild.id)
        if not templates:
            container = CicadaContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Saved Embed Templates**\n"
                    "> No saved templates found in this server. Create one using `?embed`."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                "**Saved Server Templates**\n"
                f"> Listing `{len(templates)}` saved container template(s) in this server."
            )
        )
        container.add_separator(divider=True)

        lines = []
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        for t in templates:
            name = t.get("embed_name", "unknown")
            created_at = str(t.get("created_at", ""))[:10]
            lines.append(f"`{name}` (Created {created_at}) — `{prefix}embed send {name}`")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @embed_group.command(
        name="delete",
        aliases=["remove"],
        description="Delete a saved template. Usage: ?embed delete <template_name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_delete(self, ctx: CustomContext, template_name: str) -> None:
        """Delete a saved template."""
        success = await self.bot.embed_mgr.delete_template(ctx.guild.id, template_name)
        container = CicadaContainer(accent_color=None)
        if success:
            container.add_section(
                content=(
                    "**Template Deleted**\n"
                    f"> Template `{template_name}` has been removed from this server."
                )
            )
        else:
            container.add_section(
                content=(
                    "**Template Not Found**\n"
                    f"> Could not find or delete template `{template_name}`."
                )
            )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @embed_group.command(
        name="raw",
        aliases=["json"],
        description="Send a raw Components V2 JSON container. Usage: ?embed raw <json>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_raw(self, ctx: CustomContext, *, json_payload: str) -> None:
        """Send raw JSON container."""
        try:
            draft = ContainerDraft.from_raw_payload(json_payload)
            avatar_url = str(self.bot.user.display_avatar.url) if self.bot and self.bot.user else ""
            container = draft.to_container(
                user=ctx.author,
                guild=ctx.guild,
                channel=ctx.channel,
                bot=self.bot,
                default_avatar=avatar_url,
            )
            await send_container_response(ctx, container)
        except Exception as e:
            await ctx.send(f"Invalid payload: {e}")


async def setup(bot: CicadaBot) -> None:
    await bot.add_cog(EmbedBuilder(bot))
