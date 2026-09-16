"""
Kyro Discord Bot - Custom Command Context
Extends commands.Context to add Components V2 container responses and interactive helpers.
"""

from __future__ import annotations

from typing import Any
import discord
from discord.ext import commands

from src.utils.containers import KyroContainer, send_container_response
from src.utils.views import ConfirmView


class CustomContext(commands.Context):
    """Custom context providing streamlined Components V2 container dispatchers and UI helpers."""

    async def send_container(
        self,
        container: KyroContainer | list[KyroContainer],
        view: discord.ui.View | None = None,
        ephemeral: bool = False,
        content: str | None = None,
        file: discord.File | None = None,
        files: list[discord.File] | None = None,
    ) -> Any:
        """Send a Components V2 Container card with full parameter support."""
        return await send_container_response(
            self,
            container,
            view=view,
            ephemeral=ephemeral,
            content=content,
            file=file,
            files=files,
        )

    async def send_success(
        self,
        message: str,
        title: str = "Success",
        ephemeral: bool = False,
    ) -> Any:
        """Send a formatted success container card."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        icon = e_reg.get("icons_correct", "") if e_reg else ""
        icon_str = f"{icon} " if icon else ""

        container = KyroContainer(accent_color=None)
        container.add_text(
            f"{icon_str}**{title}**\n"
            f"> {message}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.author.display_name}")
        return await self.send_container(container, ephemeral=ephemeral)

    async def send_error(
        self,
        message: str,
        title: str = "Error",
        ephemeral: bool = True,
    ) -> Any:
        """Send a formatted error container card."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        icon = e_reg.get("icons_wrong", e_reg.get("icon_x", "")) if e_reg else ""
        icon_str = f"{icon} " if icon else ""

        container = KyroContainer(accent_color=None)
        container.add_text(
            f"{icon_str}**{title}**\n"
            f"> {message}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.author.display_name}")
        return await self.send_container(container, ephemeral=ephemeral)

    async def send_warning(
        self,
        message: str,
        title: str = "Warning",
        ephemeral: bool = False,
    ) -> Any:
        """Send a formatted warning container card."""
        e_reg = getattr(self.bot, "custom_emojis", None)
        icon = e_reg.get("icons_warning", e_reg.get("icon_warning", "")) if e_reg else ""
        icon_str = f"{icon} " if icon else ""

        container = KyroContainer(accent_color=None)
        container.add_text(
            f"{icon_str}**{title}**\n"
            f"> {message}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.author.display_name}")
        return await self.send_container(container, ephemeral=ephemeral)
