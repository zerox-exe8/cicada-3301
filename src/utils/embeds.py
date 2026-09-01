"""
Kyro Discord Bot - Components V2 Container Embed Utility
Standardized builder for creating Discord Components V2 Container cards
with consistent headers, native dark themes, and user footers.
"""

from __future__ import annotations

from typing import Any
import discord
from src.core.config import Config
from src.utils.containers import KyroContainer, send_container_response


class KyroCard(KyroContainer):
    """
    Standardized Discord Components V2 Container Card builder for Kyro.
    Features cryptographic styling, glowing status glyphs, and unified matrix theme.
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
                formatted_title = title if title.startswith("#") else f"### {title.upper()}"
                body.append(formatted_title)
            if description:
                body.append(f"> {description}" if not description.startswith(">") else description)
            self.add_text("\n".join(body))

        if author:
            self.add_separator(divider=True)
            self.add_footer(
                f"Kyro Protocol • Initiated by {author.display_name}",
                icon_url=str(author.display_avatar.url),
            )

    @classmethod
    def standard(
        cls,
        *,
        title: str | None = None,
        description: str | None = None,
        author: discord.User | discord.Member | None = None,
    ) -> KyroCard:
        """Create a default native dark container card."""
        return cls(title=title, description=description, accent_color=None, author=author)

    @classmethod
    def success(
        cls,
        message: str,
        title: str = "OPERATION COMPLETED",
        author: discord.User | discord.Member | None = None,
    ) -> KyroCard:
        """Create a success container card."""
        return cls(
            title=title,
            description=message,
            accent_color=None,
            author=author,
        )

    @classmethod
    def error(
        cls,
        message: str,
        title: str = "SYSTEM EXCEPTION",
        author: discord.User | discord.Member | None = None,
    ) -> KyroCard:
        """Create an error container card."""
        return cls(
            title=title,
            description=message,
            accent_color=None,
            author=author,
        )

    @classmethod
    def warning(
        cls,
        message: str,
        title: str = "SYSTEM ADVISORY",
        author: discord.User | discord.Member | None = None,
    ) -> KyroCard:
        """Create a warning container card."""
        return cls(
            title=title,
            description=message,
            accent_color=None,
            author=author,
        )

    @classmethod
    def info(
        cls,
        message: str,
        title: str = "TELEMETRY DATA",
        author: discord.User | discord.Member | None = None,
    ) -> KyroCard:
        """Create an informational container card."""
        return cls(
            title=title,
            description=message,
            accent_color=None,
            author=author,
        )



# Backward Compatibility Alias
KyroCard = KyroCard
