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

        self.title: str | None = None
        self.title_url: str | None = None

        self.description: str | None = "> Welcome to your interactive container card preview.\n> Use the control panel below to customize and style your message."

        self.fields: list[dict[str, str]] = []  # [{"name": "...", "value": "..."}]

        self.thumbnail_url: str | None = None
        self.image_url: str | None = None

        self.footer_text: str | None = None
        self.footer_icon_url: str | None = None
        self.timestamp: bool = False

        self.accent_hex: str | None = None
        self.buttons: list[dict[str, str]] = []  # [{"label": "...", "url": "..."}]
        self.modules: list[dict[str, Any]] = []  # [{"id": "...", "label": "...", "description": "...", "page_title": "...", "content": "..."}]

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
        active_module_id: str | None = None,
        user: discord.Member | discord.User | None = None,
        guild: discord.Guild | None = None,
        channel: discord.abc.GuildChannel | discord.Thread | discord.abc.Messageable | None = None,
        bot: CicadaBot | None = None,
        default_avatar: str | None = None,
    ) -> CicadaContainer:
        """Convert draft into a Discord Components V2 CicadaContainer with dynamic module page support."""
        container = CicadaContainer(accent_color=self.get_accent_int())

        def parse(t: str | None) -> str:
            if not t:
                return ""
            return apply_placeholders(t, user=user, guild=guild, channel=channel, bot=bot)

        # Check for active module page
        active_mod: dict[str, Any] | None = None
        if active_module_id and active_module_id not in ["home", "mod_home"]:
            for idx, m in enumerate(self.modules):
                if m.get("id") == active_module_id or f"mod_{idx}" == active_module_id or m.get("label") == active_module_id:
                    active_mod = m
                    break

        # 1. Author & Title Extraction
        author_raw = parse(self.author_name)
        author_text, author_url_extracted = parse_markdown_link(author_raw)
        final_author_url = self.author_url or author_url_extracted

        # If active module has page_title, use it; otherwise use main title
        if active_mod and active_mod.get("page_title"):
            title_raw = parse(active_mod["page_title"])
        else:
            title_raw = parse(self.title)

        title_text, title_url_extracted = parse_markdown_link(title_raw)
        final_title_url = self.title_url or title_url_extracted

        # If active module has content, use it; otherwise use main description
        if active_mod and active_mod.get("content"):
            desc_text = parse(active_mod["content"])
        else:
            desc_text = parse(self.description)

        # Thumbnail Accessory (Type 11) - Only if thumbnail_url is set
        thumb_url = parse(self.thumbnail_url)
        accessory_dict = None
        if thumb_url and thumb_url.startswith("http"):
            accessory_dict = {
                "type": 11,
                "media": {
                    "url": thumb_url,
                },
            }

        # Compose Header Block with natural tight spacing
        header_blocks = []
        top_lines = []
        if author_text:
            if final_author_url and final_author_url.startswith("http"):
                top_lines.append(f"-# **[{author_text}]({final_author_url})**" if not author_text.startswith("-#") else f"**[{author_text}]({final_author_url})**")
            else:
                top_lines.append(f"-# **{author_text}**" if not author_text.startswith("-#") else f"**{author_text}**")

        if title_text:
            if title_text.startswith("#"):
                formatted_title = title_text
            else:
                formatted_title = f"**{title_text}**"
            if final_title_url and final_title_url.startswith("http"):
                top_lines.append(f"[{formatted_title}]({final_title_url})")
            else:
                top_lines.append(formatted_title)

        if top_lines:
            header_blocks.append("\n".join(top_lines))

        if desc_text:
            header_blocks.append(desc_text)

        if header_blocks or accessory_dict:
            full_header_content = "\n".join(header_blocks) if header_blocks else " "
            container.add_section(content=full_header_content, accessory=accessory_dict)
            container.add_separator(divider=True)

        # 2. Custom Fields (Show on main overview or if active module doesn't replace them)
        if not active_mod and self.fields:
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

        # 4. Interactive Dropdown Modules Select Menu (Type 3 Action Row)
        if self.modules:
            select_opts = [
                {
                    "label": "Main Overview",
                    "value": "mod_home",
                    "description": "Return to original card overview",
                    "default": (active_mod is None),
                }
            ]
            for idx, mod in enumerate(self.modules[:24]):
                mod_id = mod.get("id", f"mod_{idx}")
                is_selected = (active_mod is not None and active_mod.get("id") == mod_id)
                select_opts.append({
                    "label": parse(mod.get("label", f"Page {idx + 1}"))[:100],
                    "value": mod_id,
                    "description": parse(mod.get("description", ""))[:100] if mod.get("description") else None,
                    "default": is_selected,
                })
            container.add_action_row([
                {
                    "type": 3,
                    "custom_id": "card_module_select",
                    "placeholder": "Select an interactive module / page...",
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
            "modules": self.modules,
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
        draft.timestamp = data.get("timestamp", False)
        draft.accent_hex = data.get("accent_hex")
        draft.buttons = data.get("buttons", [])
        draft.modules = data.get("modules") or data.get("faq_options") or []
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
        self.desc_input.default = self.view_ref.draft.description or ""
        self.accent_input.default = self.view_ref.draft.accent_hex or "none"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        t = str(self.title_input.value).strip()
        a = str(self.author_input.value).strip()
        d = str(self.desc_input.value).strip()
        ac = str(self.accent_input.value).strip()

        self.view_ref.draft.title = t if t else None
        self.view_ref.draft.author_name = a if a else None
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


class AddModuleModal(discord.ui.Modal):
    def __init__(self, view: EmbedBuilderView, edit_idx: int | None = None) -> None:
        title = f"Edit Module #{edit_idx + 1}" if edit_idx is not None else "Add Dropdown Module"
        super().__init__(title=title)
        self.view_ref = view
        self.edit_idx = edit_idx

        existing: dict[str, Any] = {}
        if edit_idx is not None and 0 <= edit_idx < len(self.view_ref.draft.modules):
            existing = self.view_ref.draft.modules[edit_idx]

        self.label_input = discord.ui.TextInput(
            label="Module Name (Label)",
            placeholder="Server Rules, VIP Perks, Payment...",
            default=existing.get("label", ""),
            max_length=100,
            required=True,
        )
        self.desc_input = discord.ui.TextInput(
            label="Subtitle Description",
            placeholder="Brief note shown in dropdown list...",
            default=existing.get("description", "") or "",
            max_length=100,
            required=False,
        )
        self.page_title_input = discord.ui.TextInput(
            label="Page Card Title (Optional)",
            placeholder="Headline when this page is open...",
            default=existing.get("page_title", "") or "",
            max_length=100,
            required=False,
        )
        self.content_input = discord.ui.TextInput(
            label="Page Content (Description)",
            style=discord.TextStyle.paragraph,
            placeholder="Full markdown text to display on card when selected...",
            default=existing.get("content", ""),
            max_length=2000,
            required=True,
        )

        self.add_item(self.label_input)
        self.add_item(self.desc_input)
        self.add_item(self.page_title_input)
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        label = str(self.label_input.value).strip()
        desc = str(self.desc_input.value).strip()
        page_title = str(self.page_title_input.value).strip()
        content = str(self.content_input.value).strip()
        if label and content:
            mod_data = {
                "id": f"mod_{self.edit_idx}" if self.edit_idx is not None else f"mod_{len(self.view_ref.draft.modules)}",
                "label": label,
                "description": desc if desc else None,
                "page_title": page_title if page_title else None,
                "content": content,
            }
            if self.edit_idx is not None and 0 <= self.edit_idx < len(self.view_ref.draft.modules):
                self.view_ref.draft.modules[self.edit_idx] = mod_data
            else:
                self.view_ref.draft.modules.append(mod_data)
        self.view_ref.preview_module_id = None
        await self.view_ref.update_view(interaction)


class ModuleManagementPicker(discord.ui.View):
    """Ephemeral picker to Add, Edit, or Delete dropdown modules."""
    def __init__(self, parent_view: EmbedBuilderView) -> None:
        super().__init__(timeout=60)
        self.parent_view = parent_view

        options = []
        if len(self.parent_view.draft.modules) < 25:
            options.append(discord.SelectOption(
                label="Add New Module",
                value="action_add",
                description="Create a new dropdown page option",
            ))

        for i, mod in enumerate(self.parent_view.draft.modules):
            options.append(discord.SelectOption(
                label=f"Edit #{i+1}: {mod.get('label', 'Module')}"[:100],
                value=f"edit_{i}",
                description=f"Modify #{i+1} {mod.get('label', '')}"[:100],
            ))

        for i, mod in enumerate(self.parent_view.draft.modules):
            options.append(discord.SelectOption(
                label=f"Delete #{i+1}: {mod.get('label', 'Module')}"[:100],
                value=f"delete_{i}",
                description=f"Remove module #{i+1} permanently"[:100],
            ))

        if len(self.parent_view.draft.modules) > 1:
            options.append(discord.SelectOption(
                label="Clear All Modules",
                value="action_clear_all",
                description="Delete all dropdown modules",
            ))

        select = discord.ui.Select(
            placeholder="Select a module to edit or delete...",
            options=options[:25],
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction) -> None:
        select: discord.ui.Select = self.children[0]  # type: ignore
        val = select.values[0]

        if val == "action_add":
            await interaction.response.send_modal(AddModuleModal(self.parent_view))
        elif val.startswith("edit_"):
            idx = int(val.replace("edit_", ""))
            await interaction.response.send_modal(AddModuleModal(self.parent_view, edit_idx=idx))
        elif val.startswith("delete_"):
            idx = int(val.replace("delete_", ""))
            if 0 <= idx < len(self.parent_view.draft.modules):
                self.parent_view.draft.modules.pop(idx)
                for new_i, m in enumerate(self.parent_view.draft.modules):
                    m["id"] = f"mod_{new_i}"
                if self.parent_view.preview_module_id == f"mod_{idx}":
                    self.parent_view.preview_module_id = None
                await self.parent_view.update_view(interaction)
        elif val == "action_clear_all":
            self.parent_view.draft.modules.clear()
            self.parent_view.preview_module_id = None
            await self.parent_view.update_view(interaction)


class ButtonManagementPicker(discord.ui.View):
    """Ephemeral picker to Add, Edit, or Delete link buttons."""
    def __init__(self, parent_view: EmbedBuilderView) -> None:
        super().__init__(timeout=60)
        self.parent_view = parent_view

        options = []
        if len(self.parent_view.draft.buttons) < 5:
            options.append(discord.SelectOption(
                label="Add New Button",
                value="action_add",
                description="Create a new link button",
            ))

        for i, btn in enumerate(self.parent_view.draft.buttons):
            options.append(discord.SelectOption(
                label=f"Edit #{i+1}: {btn.get('label', 'Link')}"[:100],
                value=f"edit_{i}",
                description=f"Modify #{i+1} URL/Label"[:100],
            ))

        for i, btn in enumerate(self.parent_view.draft.buttons):
            options.append(discord.SelectOption(
                label=f"Delete #{i+1}: {btn.get('label', 'Link')}"[:100],
                value=f"delete_{i}",
                description=f"Remove button #{i+1}"[:100],
            ))

        if len(self.parent_view.draft.buttons) > 1:
            options.append(discord.SelectOption(
                label="Clear All Buttons",
                value="action_clear_all",
                description="Remove all buttons",
            ))

        select = discord.ui.Select(
            placeholder="Select a button to edit or delete...",
            options=options[:25],
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction) -> None:
        select: discord.ui.Select = self.children[0]  # type: ignore
        val = select.values[0]

        if val == "action_add":
            await interaction.response.send_modal(AddButtonModal(self.parent_view))
        elif val.startswith("edit_"):
            idx = int(val.replace("edit_", ""))
            await interaction.response.send_modal(AddButtonModal(self.parent_view, edit_idx=idx))
        elif val.startswith("delete_"):
            idx = int(val.replace("delete_", ""))
            if 0 <= idx < len(self.parent_view.draft.buttons):
                self.parent_view.draft.buttons.pop(idx)
                await self.parent_view.update_view(interaction)
        elif val == "action_clear_all":
            self.parent_view.draft.buttons.clear()
            await self.parent_view.update_view(interaction)


class FieldManagementPicker(discord.ui.View):
    """Ephemeral picker to Add, Edit, or Delete custom fields."""
    def __init__(self, parent_view: EmbedBuilderView) -> None:
        super().__init__(timeout=60)
        self.parent_view = parent_view

        options = []
        if len(self.parent_view.draft.fields) < 25:
            options.append(discord.SelectOption(
                label="Add New Field",
                value="action_add",
                description="Add another structured section",
            ))

        for i, fld in enumerate(self.parent_view.draft.fields):
            options.append(discord.SelectOption(
                label=f"Edit #{i+1}: {fld.get('name', 'Field')}"[:100],
                value=f"edit_{i}",
                description=f"Modify field #{i+1}"[:100],
            ))

        for i, fld in enumerate(self.parent_view.draft.fields):
            options.append(discord.SelectOption(
                label=f"Delete #{i+1}: {fld.get('name', 'Field')}"[:100],
                value=f"delete_{i}",
                description=f"Remove field #{i+1}"[:100],
            ))

        if len(self.parent_view.draft.fields) > 1:
            options.append(discord.SelectOption(
                label="Clear All Fields",
                value="action_clear_all",
                description="Delete all fields",
            ))

        select = discord.ui.Select(
            placeholder="Select a field to edit or delete...",
            options=options[:25],
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction) -> None:
        select: discord.ui.Select = self.children[0]  # type: ignore
        val = select.values[0]

        if val == "action_add":
            await interaction.response.send_modal(AddFieldModal(self.parent_view))
        elif val.startswith("edit_"):
            idx = int(val.replace("edit_", ""))
            await interaction.response.send_modal(AddFieldModal(self.parent_view, edit_idx=idx))
        elif val.startswith("delete_"):
            idx = int(val.replace("delete_", ""))
            if 0 <= idx < len(self.parent_view.draft.fields):
                self.parent_view.draft.fields.pop(idx)
                await self.parent_view.update_view(interaction)
        elif val == "action_clear_all":
            self.parent_view.draft.fields.clear()
            await self.parent_view.update_view(interaction)


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


class CreateEmbedModal(discord.ui.Modal, title="Create New Embed"):
    name_input = discord.ui.TextInput(
        label="Embed Name (Identifier)",
        placeholder="rules, welcome, faq, announcement, perks...",
        max_length=32,
        required=True,
    )

    def __init__(self, bot: CicadaBot, author: discord.Member | discord.User) -> None:
        super().__init__()
        self.bot = bot
        self.author = author

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = str(self.name_input.value).strip().lower()
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", name)
        if not clean_name:
            await interaction.response.send_message("Invalid embed name. Use letters, numbers, hyphens, and underscores.", ephemeral=True)
            return

        draft = ContainerDraft()
        await self.bot.embed_mgr.save_template(
            guild_id=interaction.guild_id or 0,
            name=clean_name,
            payload=draft.to_dict(),
            created_by=self.author.id,
        )

        view = EmbedBuilderView(self.bot, self.author, draft=draft, template_name=clean_name)
        containers = view.get_dual_containers(interaction.guild, interaction.channel)
        msg_data = await send_container_response(interaction, containers, view=view)
        msg_id = None
        if isinstance(msg_data, dict) and "id" in msg_data:
            msg_id = int(msg_data["id"])
        elif hasattr(msg_data, "id"):
            msg_id = int(msg_data.id)
        if msg_id:
            EmbedBuilderView.active_views[msg_id] = view


class EmbedHubView(discord.ui.View):
    """Server Embed Management Hub: Select an existing embed to edit."""
    def __init__(self, bot: CicadaBot, author: discord.Member | discord.User, templates: list[dict[str, Any]]) -> None:
        super().__init__(timeout=180)
        self.bot = bot
        self.author = author
        self.templates = templates

        if templates:
            options = [
                discord.SelectOption(
                    label=f"Edit: {t.get('embed_name', 'unknown')}"[:100],
                    value=t.get("embed_name", "unknown"),
                    description=f"Open builder for '{t.get('embed_name', '')}'"[:100],
                )
                for t in templates[:25]
            ]
            select = discord.ui.Select(
                placeholder="Select an existing embed to edit...",
                options=options,
                row=0,
            )
            select.callback = self.on_select_template
            self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Only the command author can use this menu.", ephemeral=True)
            return False
        return True

    async def on_select_template(self, interaction: discord.Interaction) -> None:
        select: discord.ui.Select = self.children[0]  # type: ignore
        template_name = select.values[0]
        data = await self.bot.embed_mgr.get_template(interaction.guild_id or 0, template_name)
        if not data:
            await interaction.response.send_message(f"Embed '{template_name}' not found.", ephemeral=True)
            return

        draft = ContainerDraft.from_dict(data)
        view = EmbedBuilderView(self.bot, self.author, draft=draft, template_name=template_name)
        containers = view.get_dual_containers(interaction.guild, interaction.channel)
        msg_data = await send_container_response(interaction, containers, view=view)
        msg_id = None
        if isinstance(msg_data, dict) and "id" in msg_data:
            msg_id = int(msg_data["id"])
        elif hasattr(msg_data, "id"):
            msg_id = int(msg_data.id)
        if msg_id:
            EmbedBuilderView.active_views[msg_id] = view


# ─── Dual-Container Controller View ──────────────────────────────────────────

class EmbedBuilderView(discord.ui.View):
    """Mimu-style dual-container builder: Top = Live Preview, Bottom = 5-Step Console."""

    active_views: dict[int, EmbedBuilderView] = {}

    SLIDES = [
        ("content", "Step 1: Content & Theme", "Title, Author, Description, Color"),
        ("visuals", "Step 2: Images & Footer", "Thumbnail, Banner, Footer Text & Icon, Timestamp"),
        ("fields", "Step 3: Custom Fields", "Add, edit, or remove structured sections"),
        ("interactive", "Step 4: Buttons & Modules", "Manage link buttons and interactive dropdown modules"),
        ("dispatch", "Step 5: Dispatch & Raw", "Send to channel, Save template, Raw JSON import"),
    ]

    def __init__(
        self,
        bot: CicadaBot,
        author: discord.Member | discord.User,
        draft: ContainerDraft | None = None,
        template_name: str = "default",
    ) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.author = author
        self.draft: ContainerDraft = draft or ContainerDraft()
        self.template_name: str = template_name
        self.current_slide_idx: int = 0  # 0 to 4
        self.preview_module_id: str | None = None
        self._setup_dynamic_buttons()

    def _setup_dynamic_buttons(self) -> None:
        """Assign custom edit and send emojis from emoji registry."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        if e_reg:
            edit_e = e_reg.get_emoji_obj("icons_edit") or e_reg.get_emoji_obj("icon_edit")
            send_e = e_reg.get_emoji_obj("icon_send") or e_reg.get_emoji_obj("icons_send")
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    if item.custom_id == "btn_action_1" and edit_e:
                        item.emoji = edit_e
                    elif item.custom_id == "btn_send" and send_e and item.label == "Send Embed":
                        item.emoji = send_e

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Only the command author can use this builder.", ephemeral=True)
            return False
        return True

    def build_preview_container(self, guild: discord.Guild | None = None, channel: discord.abc.Messageable | None = None) -> CicadaContainer:
        """Top Container: Live rendered preview of the custom card."""
        return self.draft.to_container(
            active_module_id=self.preview_module_id,
            user=self.author,
            guild=guild,
            channel=channel,
            bot=self.bot,
        )

    def build_control_container(self, guild: discord.Guild | None = None) -> CicadaContainer:
        """Bottom Container: Minimal 5-step editor console."""
        slide_key, slide_title, _ = self.SLIDES[self.current_slide_idx]

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                f"> **{slide_title}** | **Name:** `{self.template_name}`\n"
                f"> Use controls below to configure this section."
            )
        )
        container.add_separator(divider=True)

        if slide_key == "content":
            t_str = f"`{self.draft.title}`" if self.draft.title else "`None`"
            a_str = f"`{self.draft.author_name}`" if self.draft.author_name else "`None`"
            desc_len = len(self.draft.description) if self.draft.description else 0
            accent_str = f"`{self.draft.accent_hex}`" if self.draft.accent_hex else "`Default Dark`"
            container.add_text(
                f"**Title:** {t_str} | **Author:** {a_str}\n"
                f"**Accent Color:** {accent_str} | **Description:** `{desc_len} chars`"
            )
        elif slide_key == "visuals":
            thumb_str = "`Set`" if self.draft.thumbnail_url else "`None`"
            banner_str = "`Set`" if self.draft.image_url else "`None`"
            footer_str = f"`{self.draft.footer_text}`" if self.draft.footer_text else "`None`"
            ts_str = "`Enabled`" if self.draft.timestamp else "`Disabled`"
            container.add_text(
                f"**Thumbnail:** {thumb_str} | **Banner:** {banner_str}\n"
                f"**Footer:** {footer_str} | **Timestamp:** {ts_str}"
            )
        elif slide_key == "fields":
            f_cnt = len(self.draft.fields)
            f_summary = ", ".join([f"`{f['name']}`" for f in self.draft.fields[:4]]) if self.draft.fields else "`None`"
            container.add_text(
                f"**Total Fields:** `{f_cnt}`\n"
                f"**Fields:** {f_summary}"
            )
        elif slide_key == "interactive":
            b_cnt = len(self.draft.buttons)
            m_cnt = len(self.draft.modules)
            b_summary = ", ".join([f"`{b['label']}`" for b in self.draft.buttons[:3]]) if self.draft.buttons else "`None`"
            m_summary = ", ".join([f"`{m['label']}`" for m in self.draft.modules[:3]]) if self.draft.modules else "`None`"
            container.add_text(
                f"**Link Buttons ({b_cnt}/5):** {b_summary}\n"
                f"**Dropdown Modules ({m_cnt}/25):** {m_summary}"
            )
        elif slide_key == "dispatch":
            container.add_text(
                f"**Auto-Saved to `{self.template_name}`:** Post to channel or import raw JSON below."
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
                if item.custom_id == "btn_action_1":
                    if slide_key == "content":
                        item.label = "Edit Content"
                        item.style = discord.ButtonStyle.secondary
                        item.disabled = False
                    elif slide_key == "visuals":
                        item.label = "Edit Visuals"
                        item.style = discord.ButtonStyle.secondary
                        item.disabled = False
                    elif slide_key == "fields":
                        item.label = "Add Field"
                        item.style = discord.ButtonStyle.secondary
                        item.disabled = False
                    elif slide_key == "interactive":
                        if self.preview_module_id and self.preview_module_id.startswith("mod_"):
                            item.label = "Edit Module"
                            item.style = discord.ButtonStyle.secondary
                        else:
                            item.label = "Add Module"
                            item.style = discord.ButtonStyle.primary
                        item.disabled = False
                    elif slide_key == "dispatch":
                        item.label = "Send to Channel"
                        item.style = discord.ButtonStyle.success
                        item.disabled = False
                elif item.custom_id == "btn_action_2":
                    if slide_key == "content":
                        item.label = "Clear Content"
                        item.style = discord.ButtonStyle.danger
                        has_content = bool(self.draft.title or self.draft.author_name or self.draft.description or self.draft.accent_hex)
                        item.disabled = not has_content
                    elif slide_key == "visuals":
                        ts_state = "ON" if self.draft.timestamp else "OFF"
                        item.label = f"Timestamp: {ts_state}"
                        item.style = discord.ButtonStyle.primary if self.draft.timestamp else discord.ButtonStyle.secondary
                        item.disabled = False
                    elif slide_key == "fields":
                        item.label = "Clear Fields"
                        item.style = discord.ButtonStyle.danger
                        item.disabled = (len(self.draft.fields) == 0)
                    elif slide_key == "interactive":
                        if self.preview_module_id and self.preview_module_id.startswith("mod_"):
                            item.label = "Delete Module"
                            item.style = discord.ButtonStyle.danger
                            item.disabled = False
                        else:
                            item.label = "Add Button"
                            item.style = discord.ButtonStyle.secondary
                            item.disabled = False
                    elif slide_key == "dispatch":
                        item.label = "Test in DM"
                        item.style = discord.ButtonStyle.secondary
                        item.disabled = False
                elif item.custom_id == "btn_action_3":
                    if slide_key == "content":
                        item.label = "Reset Draft"
                        item.style = discord.ButtonStyle.danger
                        item.disabled = False
                    elif slide_key == "visuals":
                        item.label = "Clear Visuals"
                        item.style = discord.ButtonStyle.danger
                        has_vis = bool(self.draft.thumbnail_url or self.draft.image_url or self.draft.footer_text)
                        item.disabled = not has_vis
                    elif slide_key == "fields":
                        item.label = "Reset Draft"
                        item.style = discord.ButtonStyle.danger
                        item.disabled = False
                    elif slide_key == "interactive":
                        if self.preview_module_id and self.preview_module_id.startswith("mod_"):
                            item.label = "Add Module"
                            item.style = discord.ButtonStyle.primary
                            item.disabled = False
                        else:
                            item.label = "Clear Modules"
                            item.style = discord.ButtonStyle.danger
                            item.disabled = (len(self.draft.modules) == 0 and len(self.draft.buttons) == 0)
                    elif slide_key == "dispatch":
                        item.label = "Raw JSON"
                        item.style = discord.ButtonStyle.secondary
                        item.disabled = False
                elif item.custom_id == "btn_send":
                    if slide_key == "dispatch":
                        item.label = "Reset Draft"
                        item.style = discord.ButtonStyle.danger
                    else:
                        item.label = "Send Embed"
                        item.style = discord.ButtonStyle.success
                    item.disabled = False

    async def update_view(self, interaction: discord.Interaction) -> None:
        """Update the dual-container message and auto-save changes."""
        self._sync_controls()
        if interaction.message:
            EmbedBuilderView.active_views[interaction.message.id] = self

        if self.template_name and interaction.guild_id:
            try:
                await self.bot.embed_mgr.save_template(
                    guild_id=interaction.guild_id,
                    name=self.template_name,
                    payload=self.draft.to_dict(),
                    created_by=self.author.id,
                )
            except Exception as e:
                logger.error(f"Failed to auto-save template '{self.template_name}': {e}")

        containers = self.get_dual_containers(interaction.guild, interaction.channel)
        await edit_container_response(interaction, containers, view=self)

    # ─── Dropdown: Direct Slide Selector ──────────────────────────────────────

    @discord.ui.select(
        placeholder="Jump to a step...",
        custom_id="select_slide",
        options=[
            discord.SelectOption(label="Step 1: Content & Theme", value="content", description="Title, Author, Description, Color"),
            discord.SelectOption(label="Step 2: Images & Footer", value="visuals", description="Thumbnail, Banner, Footer Text & Icon, Timestamp"),
            discord.SelectOption(label="Step 3: Custom Fields", value="fields", description="Add, edit, or remove structured sections"),
            discord.SelectOption(label="Step 4: Buttons & Modules", value="interactive", description="Manage link buttons and interactive dropdown modules"),
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

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.secondary, custom_id="btn_action_1", row=1)
    async def btn_action_1(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        slide_key, _, _ = self.SLIDES[self.current_slide_idx]

        if slide_key == "content":
            await interaction.response.send_modal(ContentModal(self))
        elif slide_key == "visuals":
            await interaction.response.send_modal(VisualsModal(self))
        elif slide_key == "fields":
            if len(self.draft.fields) >= 25:
                await interaction.response.send_message("Maximum 25 fields allowed.", ephemeral=True)
                return
            await interaction.response.send_modal(AddFieldModal(self))
        elif slide_key == "interactive":
            if self.preview_module_id and self.preview_module_id.startswith("mod_"):
                try:
                    idx = int(self.preview_module_id.replace("mod_", ""))
                    await interaction.response.send_modal(AddModuleModal(self, edit_idx=idx))
                except Exception:
                    await interaction.response.send_modal(AddModuleModal(self))
            else:
                if len(self.draft.modules) >= 25:
                    await interaction.response.send_message("Maximum 25 dropdown modules allowed.", ephemeral=True)
                    return
                await interaction.response.send_modal(AddModuleModal(self))
        elif slide_key == "dispatch":
            await self._open_send_picker(interaction)

    @discord.ui.button(label="Action 2", style=discord.ButtonStyle.secondary, custom_id="btn_action_2", row=1)
    async def btn_action_2(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        slide_key, _, _ = self.SLIDES[self.current_slide_idx]

        if slide_key == "content":
            self.draft.title = None
            self.draft.author_name = None
            self.draft.description = None
            self.draft.accent_hex = None
            await self.update_view(interaction)
        elif slide_key == "visuals":
            self.draft.timestamp = not self.draft.timestamp
            await self.update_view(interaction)
        elif slide_key == "fields":
            self.draft.fields.clear()
            await self.update_view(interaction)
        elif slide_key == "interactive":
            if self.preview_module_id and self.preview_module_id.startswith("mod_"):
                try:
                    idx = int(self.preview_module_id.replace("mod_", ""))
                    if 0 <= idx < len(self.draft.modules):
                        self.draft.modules.pop(idx)
                        for new_i, m in enumerate(self.draft.modules):
                            m["id"] = f"mod_{new_i}"
                    self.preview_module_id = None
                    await self.update_view(interaction)
                except Exception:
                    self.preview_module_id = None
                    await self.update_view(interaction)
            else:
                if len(self.draft.buttons) >= 5:
                    await interaction.response.send_message("Maximum 5 buttons allowed.", ephemeral=True)
                    return
                await interaction.response.send_modal(AddButtonModal(self))
        elif slide_key == "dispatch":
            await self._send_test_dm(interaction)

    @discord.ui.button(label="Action 3", style=discord.ButtonStyle.secondary, custom_id="btn_action_3", row=1)
    async def btn_action_3(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        slide_key, _, _ = self.SLIDES[self.current_slide_idx]

        if slide_key in ["content", "fields"]:
            self.draft = ContainerDraft()
            await self.update_view(interaction)
        elif slide_key == "visuals":
            self.draft.thumbnail_url = None
            self.draft.image_url = None
            self.draft.footer_text = None
            await self.update_view(interaction)
        elif slide_key == "interactive":
            if self.preview_module_id and self.preview_module_id.startswith("mod_"):
                if len(self.draft.modules) >= 25:
                    await interaction.response.send_message("Maximum 25 dropdown modules allowed.", ephemeral=True)
                    return
                await interaction.response.send_modal(AddModuleModal(self))
            else:
                self.draft.modules.clear()
                self.draft.buttons.clear()
                self.preview_module_id = None
                await self.update_view(interaction)
        elif slide_key == "dispatch":
            await interaction.response.send_modal(RawImportModal(self))

    @discord.ui.button(label="Send Embed", style=discord.ButtonStyle.success, custom_id="btn_send", row=1)
    async def btn_send(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        slide_key, _, _ = self.SLIDES[self.current_slide_idx]
        if slide_key == "dispatch":
            self.draft = ContainerDraft()
            await self.update_view(interaction)
        else:
            await self._open_send_picker(interaction)

    async def _send_test_dm(self, interaction: discord.Interaction) -> None:
        """Dispatch a live test copy of the embed container directly to user DM."""
        container = self.draft.to_container(
            user=self.author,
            guild=interaction.guild,
            bot=self.bot,
        )
        try:
            dm_channel = self.author.dm_channel or await self.author.create_dm()
            await send_container_response(dm_channel, container)
            await interaction.response.send_message("Test embed dispatched to your DMs!", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Could not send DM. Please enable DMs from server members.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to send DM: {e}", ephemeral=True)

    async def _open_send_picker(self, interaction: discord.Interaction) -> None:
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
                description=f"Send embed to #{c.name}"[:100],
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
                if not target_ch or not isinstance(target_ch, discord.TextChannel):
                    await inter.response.send_message("Target channel not found.", ephemeral=True)
                    return

                container = self.parent_view.draft.to_container(
                    user=self.parent_view.author,
                    guild=inter.guild,
                    channel=target_ch,
                    bot=self.parent_view.bot,
                )
                try:
                    target_msg = await send_container_response(target_ch, container)
                    if hasattr(target_msg, "id") and target_msg:
                        await self.parent_view.bot.embed_mgr.record_interactive_card(
                            guild_id=inter.guild_id or 0,
                            message_id=target_msg.id,
                            template_name=self.parent_view.template_name,
                            payload=self.parent_view.draft.to_dict(),
                        )
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
        """Handle persistent interactive card dropdown module switching and hub template picker."""
        if not interaction.data:
            return
        custom_id = interaction.data.get("custom_id")
        if custom_id not in ("card_module_select", "hub_select_template"):
            return

        guild = interaction.guild
        message = interaction.message
        if not guild or not message:
            return

        selected_vals = interaction.data.get("values", [])
        if not selected_vals:
            return

        selected_id = selected_vals[0]

        # Handle Hub Template Selection Dropdown
        if custom_id == "hub_select_template":
            template_name = selected_id
            data = await self.bot.embed_mgr.get_template(interaction.guild_id or 0, template_name)
            if not data:
                await interaction.response.send_message(f"Embed '{template_name}' not found.", ephemeral=True)
                return

            draft = ContainerDraft.from_dict(data)
            view = EmbedBuilderView(self.bot, interaction.user, draft=draft, template_name=template_name)
            containers = view.get_dual_containers(interaction.guild, interaction.channel)
            msg_data = await send_container_response(interaction, containers, view=view)
            msg_id = None
            if isinstance(msg_data, dict) and "id" in msg_data:
                msg_id = int(msg_data["id"])
            elif hasattr(msg_data, "id"):
                msg_id = int(msg_data.id)
            if msg_id:
                EmbedBuilderView.active_views[msg_id] = view
            return

        # Case 1: Inside active EmbedBuilderView session
        if message.id in EmbedBuilderView.active_views:
            active_view = EmbedBuilderView.active_views[message.id]
            if interaction.user.id != active_view.author.id:
                await interaction.response.send_message("Only the builder author can test the preview.", ephemeral=True)
                return
            active_view.preview_module_id = selected_id
            await active_view.update_view(interaction)
            return

        # Case 2: On a posted channel card from database
        card_data = await self.bot.embed_mgr.get_interactive_card(guild.id, message.id)
        if card_data:
            draft = ContainerDraft.from_dict(card_data)
            avatar_url = str(self.bot.user.display_avatar.url) if self.bot and self.bot.user else ""
            new_container = draft.to_container(
                active_module_id=selected_id,
                user=interaction.user,
                guild=guild,
                channel=interaction.channel,
                bot=self.bot,
                default_avatar=avatar_url,
            )

            payload = new_container.to_payload()
            try:
                if not interaction.response.is_done():
                    await self.bot.http.request(
                        discord.http.Route(
                            "POST",
                            f"/interactions/{interaction.id}/{interaction.token}/callback",
                        ),
                        json={"type": 7, "data": payload},  # 7 = UPDATE_MESSAGE
                    )
                else:
                    await self.bot.http.request(
                        discord.http.Route("PATCH", f"/channels/{interaction.channel_id}/messages/{message.id}"),
                        json=payload,
                    )
            except Exception as e:
                logger.error(f"Failed to switch interactive module page: {e}", exc_info=e)
                if not interaction.response.is_done():
                    await interaction.response.defer()
        else:
            if not interaction.response.is_done():
                await interaction.response.defer()

    @commands.hybrid_group(
        name="embed",
        aliases=["embedbuilder", "container", "card"],
        description="Design, customize, preview, save, edit, and post Components V2 container cards.",
        fallback="hub",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_group(self, ctx: CustomContext, template_name: str | None = None) -> None:
        """Launch the embed manager dashboard or a specific named builder."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if template_name:
            clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", template_name.lower())
            data = await self.bot.embed_mgr.get_template(ctx.guild.id, clean_name)
            draft = ContainerDraft.from_dict(data) if data else ContainerDraft()
            view = EmbedBuilderView(self.bot, ctx.author, draft=draft, template_name=clean_name)
            containers = view.get_dual_containers(ctx.guild, ctx.channel)
            msg_data = await send_container_response(ctx, containers, view=view)
            msg_id = None
            if isinstance(msg_data, dict) and "id" in msg_data:
                msg_id = int(msg_data["id"])
            elif hasattr(msg_data, "id"):
                msg_id = int(msg_data.id)
            if msg_id:
                EmbedBuilderView.active_views[msg_id] = view
            return

        templates = await self.bot.embed_mgr.list_templates(ctx.guild.id)
        hub_container = CicadaContainer(accent_color=None)
        hub_container.add_section(
            content=(
                "**Server Embed Manager**\n"
                f"> Manage, design, and dispatch custom container cards for **{ctx.guild.name}**.\n"
                f"> All embeds are saved and managed by their unique **Name**."
            )
        )
        hub_container.add_separator(divider=True)

        if templates:
            t_lines = [f"`{t.get('embed_name')}`" for t in templates[:25]]
            hub_container.add_text(
                f"**Saved Embeds ({len(templates)}):** " + " , ".join(t_lines)
            )
        else:
            hub_container.add_text(
                "**Saved Embeds:** `None`"
            )

        hub_container.add_separator(divider=True)
        hub_container.add_text(
            f"`{prefix}embed create <name>` , `{prefix}embed edit <name>`\n"
            f"`{prefix}embed show <name>` , `{prefix}embed delete <name>`\n"
            f"`{prefix}embed send #channel <name>` , `{prefix}embed list`"
        )
        if templates:
            hub_container.add_separator(divider=True)
            options = [
                {
                    "label": f"Edit: {t.get('embed_name', 'unknown')}"[:100],
                    "value": t.get("embed_name", "unknown"),
                    "description": f"Open builder for '{t.get('embed_name', '')}'"[:100],
                }
                for t in templates[:25]
            ]
            hub_container.add_action_row([
                {
                    "type": 3,
                    "custom_id": "hub_select_template",
                    "placeholder": "Select an existing embed to edit...",
                    "options": options,
                }
            ])

        hub_container.add_separator(divider=True)
        hub_container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, hub_container)

    @embed_group.command(
        name="create",
        description="Create a new named embed. Usage: ?embed create <name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_create(self, ctx: CustomContext, name: str) -> None:
        """Create a new named embed."""
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", name.lower())
        if not clean_name:
            await ctx.send("Please provide a valid embed name (letters, numbers, hyphens). Example: `?embed create rules`")
            return

        existing = await self.bot.embed_mgr.get_template(ctx.guild.id, clean_name)
        draft = ContainerDraft.from_dict(existing) if existing else ContainerDraft()

        # Save initial template record
        await self.bot.embed_mgr.save_template(
            guild_id=ctx.guild.id,
            name=clean_name,
            payload=draft.to_dict(),
            created_by=ctx.author.id,
        )

        view = EmbedBuilderView(self.bot, ctx.author, draft=draft, template_name=clean_name)
        containers = view.get_dual_containers(ctx.guild, ctx.channel)
        msg_data = await send_container_response(ctx, containers, view=view)
        msg_id = None
        if isinstance(msg_data, dict) and "id" in msg_data:
            msg_id = int(msg_data["id"])
        elif hasattr(msg_data, "id"):
            msg_id = int(msg_data.id)
        if msg_id:
            EmbedBuilderView.active_views[msg_id] = view

    @embed_group.command(
        name="edit",
        description="Edit an existing named embed. Usage: ?embed edit <name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_edit_template(self, ctx: CustomContext, name: str) -> None:
        """Open the builder to edit a saved template."""
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", name.lower())
        template_data = await self.bot.embed_mgr.get_template(ctx.guild.id, clean_name)
        if not template_data:
            await ctx.send(f"Embed template `{clean_name}` not found. Create it using `?embed create {clean_name}`.")
            return

        draft = ContainerDraft.from_dict(template_data)
        view = EmbedBuilderView(self.bot, ctx.author, draft=draft, template_name=clean_name)
        containers = view.get_dual_containers(ctx.guild, ctx.channel)
        msg_data = await send_container_response(ctx, containers, view=view)
        msg_id = None
        if isinstance(msg_data, dict) and "id" in msg_data:
            msg_id = int(msg_data["id"])
        elif hasattr(msg_data, "id"):
            msg_id = int(msg_data.id)
        if msg_id:
            EmbedBuilderView.active_views[msg_id] = view

    @embed_group.command(
        name="show",
        aliases=["view", "preview"],
        description="Preview a saved embed card. Usage: ?embed show <name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_show(self, ctx: CustomContext, name: str) -> None:
        """View a live preview of a saved embed template."""
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", name.lower())
        template_data = await self.bot.embed_mgr.get_template(ctx.guild.id, clean_name)
        if not template_data:
            await ctx.send(f"Embed template `{clean_name}` not found.")
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
        msg_data = await send_container_response(ctx, container)
        if hasattr(msg_data, "id") and msg_data:
            await self.bot.embed_mgr.record_interactive_card(
                guild_id=ctx.guild.id,
                message_id=msg_data.id,
                template_name=clean_name,
                payload=draft.to_dict(),
            )
        elif isinstance(msg_data, dict) and "id" in msg_data:
            await self.bot.embed_mgr.record_interactive_card(
                guild_id=ctx.guild.id,
                message_id=int(msg_data["id"]),
                template_name=clean_name,
                payload=draft.to_dict(),
            )

    @embed_group.command(
        name="send",
        aliases=["post"],
        description="Send a saved template to a channel. Usage: ?embed send [#channel] <name>",
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

        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", actual_name.lower())
        template_data = await self.bot.embed_mgr.get_template(ctx.guild.id, clean_name)
        if not template_data:
            await ctx.send(f"Saved template '{clean_name}' not found.")
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
            target_msg = await send_container_response(target_channel, container)
            msg_id = None
            if hasattr(target_msg, "id"):
                msg_id = target_msg.id
            elif isinstance(target_msg, dict) and "id" in target_msg:
                msg_id = int(target_msg["id"])

            if msg_id:
                await self.bot.embed_mgr.record_interactive_card(
                    guild_id=ctx.guild.id,
                    message_id=msg_id,
                    template_name=clean_name,
                    payload=draft.to_dict(),
                )

            ch_mention = getattr(target_channel, "mention", f"#{target_channel}")
            resp_container = CicadaContainer(accent_color=None)
            resp_container.add_section(
                content=(
                    "**Card Dispatched**\n"
                    f"> Saved embed `{clean_name}` posted to {ch_mention}."
                )
            )
            resp_container.add_separator(divider=True)
            resp_container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, resp_container)
        except Exception as e:
            logger.error(f"Failed to post embed template '{clean_name}': {e}", exc_info=e)
            await ctx.send(f"Failed to post card: {e}")

    @embed_group.command(
        name="delete",
        aliases=["remove"],
        description="Delete a saved template. Usage: ?embed delete <name>",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_delete(self, ctx: CustomContext, name: str) -> None:
        """Delete a saved template."""
        clean_name = re.sub(r"[^a-zA-Z0-9_-]", "", name.lower())
        success = await self.bot.embed_mgr.delete_template(ctx.guild.id, clean_name)
        container = CicadaContainer(accent_color=None)
        if success:
            container.add_section(
                content=(
                    "**Embed Deleted**\n"
                    f"> Embed template `{clean_name}` has been removed from this server."
                )
            )
        else:
            container.add_section(
                content=(
                    "**Embed Not Found**\n"
                    f"> Could not find or delete template `{clean_name}`."
                )
            )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @embed_group.command(
        name="list",
        aliases=["all", "templates"],
        description="List all saved embeds in this server. Usage: ?embed list",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_list(self, ctx: CustomContext) -> None:
        """List all saved templates."""
        templates = await self.bot.embed_mgr.list_templates(ctx.guild.id)
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not templates:
            container = CicadaContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Saved Embed Templates**\n"
                    f"> No saved embeds found in this server. Create one using `{prefix}embed create <name>`."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        container = CicadaContainer(accent_color=None)
        container.add_section(
            content=(
                "**Saved Server Embeds**\n"
                f"> Listing `{len(templates)}` saved embed template(s) in this server."
            )
        )
        container.add_separator(divider=True)

        lines = []
        for t in templates:
            t_name = t.get("embed_name", "unknown")
            created_at = str(t.get("created_at", ""))[:10]
            lines.append(f"`{t_name}` (Created {created_at}) — `{prefix}embed edit {t_name}`")

        container.add_text("\n".join(lines))
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
