"""
Hertz Discord Bot - Components V2 Container Embed Utility
Standardized builder for creating Discord Components V2 Container cards
with consistent headers, native dark themes, and user footers.
"""

from __future__ import annotations

from typing import Any
import discord
from src.core.config import Config
from src.utils.containers import HertzContainer, send_container_response


class HertzCard(HertzContainer):
    """
    Standardized Discord Components V2 Container Card builder for Hertz.
    Provides easy factory methods for creating consistent cards across all modules.
    """

    def __init__(
        self,
        *,
        title: str | None = None,
        description: str | None = None,
        accent_color: int | None = None,
        author: discord.User | discord.Member | None = None,
    ) -> None:
        super().__init__(accent_color=accent_color)

        if title or description:
            body = []
            if title:
                body.append(f"## {title}" if not title.startswith("#") else title)
            if description:
                body.append(description)
            self.add_text("\n".join(body))

        if author:
            self.add_separator(divider=True)
            self.add_footer(
                f"Requested by {author.display_name}",
                icon_url=str(author.display_avatar.url),
            )

    @classmethod
    def standard(
        cls,
        *,
        title: str | None = None,
        description: str | None = None,
        author: discord.User | discord.Member | None = None,
    ) -> HertzCard:
        """Create a default native dark container card."""
        return cls(title=title, description=description, accent_color=None, author=author)

    @classmethod
    def success(
        cls,
        message: str,
        title: str = "Success",
        author: discord.User | discord.Member | None = None,
    ) -> HertzCard:
        """Create a success container card."""
        return cls(
            title=f"✅ {title}",
            description=f"> {message}" if not message.startswith(">") else message,
            accent_color=None,
            author=author,
        )

    @classmethod
    def error(
        cls,
        message: str,
        title: str = "Error Occurred",
        author: discord.User | discord.Member | None = None,
    ) -> HertzCard:
        """Create an error container card."""
        return cls(
            title=f"❌ {title}",
            description=f"> {message}" if not message.startswith(">") else message,
            accent_color=None,
            author=author,
        )

    @classmethod
    def warning(
        cls,
        message: str,
        title: str = "Warning",
        author: discord.User | discord.Member | None = None,
    ) -> HertzCard:
        """Create a warning container card."""
        return cls(
            title=f"⚠️ {title}",
            description=f"> {message}" if not message.startswith(">") else message,
            accent_color=None,
            author=author,
        )

    @classmethod
    def info(
        cls,
        message: str,
        title: str = "Information",
        author: discord.User | discord.Member | None = None,
    ) -> HertzCard:
        """Create an informational container card."""
        return cls(
            title=f"ℹ️ {title}",
            description=f"> {message}" if not message.startswith(">") else message,
            accent_color=None,
            author=author,
        )
