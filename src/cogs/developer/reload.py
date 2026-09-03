"""
Kyro Discord Bot - Module Hot-Reloading Suite
Enables real-time code reloading without restarting the bot process.
Supports reloading all modules, category folders, or specific cogs.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Optional

from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class ReloadCog(commands.Cog, name="Developer-Reload"):
    """Live module reloading suite."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="reload", aliases=["r"])
    @is_developer()
    async def reload_module(self, ctx: CustomContext, *, module_name: Optional[str] = None) -> None:
        """
        Hot-reload cogs without restarting the bot.
        Usage:
          ?reload           -> Reloads all loaded extensions
          ?reload all       -> Reloads all loaded extensions
          ?reload music     -> Reloads the music module
          ?reload general   -> Reloads all general category cogs
        """
        start_time = time.perf_counter()
        target = (module_name or "").strip().lower()

        # Case 1: Reload ALL extensions if no argument or 'all'/'*' passed
        if not target or target in ("all", "*", "everything"):
            all_exts = list(self.bot.extensions.keys())
            reloaded: list[str] = []
            failed: list[str] = []

            for ext in all_exts:
                try:
                    await self.bot.reload_extension(ext)
                    short_name = ext.split(".")[-1]
                    reloaded.append(short_name)
                except Exception as e:
                    failed.append(f"{ext}: {e}")

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            container = KyroContainer(accent_color=None)

            if not failed:
                container.add_section(
                    content=(
                        f"### System Hot-Reload Complete\n"
                        f"> **Modules Reloaded:** `{len(reloaded)}` cogs\n"
                        f"> **Execution Time:** `{elapsed_ms:.1f}ms`\n"
                        f"> **Status:** `All Extensions Live & Fresh`"
                    )
                )
            else:
                container.add_section(
                    content=(
                        f"### System Hot-Reload Partial\n"
                        f"> **Reloaded:** `{len(reloaded)}` cogs\n"
                        f"> **Failed:** `{len(failed)}` cogs\n"
                        f"> **Errors:**\n" + "\n".join(f"> • `{err}`" for err in failed[:5])
                    )
                )

            container.add_separator(divider=True)
            container.add_text("-# Powered by Kyro Studio")
            await send_container_response(ctx, container)
            return

        # Case 2: Specific module or category requested
        # Search for exact matches or partial folder matches
        matching_exts: list[str] = []
        for ext in list(self.bot.extensions.keys()):
            # Exact suffix match (e.g. 'music', 'ping', 'identity')
            if ext.lower().endswith(f".{target}") or ext.lower().endswith(f"._{target}"):
                matching_exts.append(ext)
            # Category folder match (e.g. 'general', 'developer', 'music')
            elif f".{target}." in ext.lower():
                matching_exts.append(ext)
            elif ext.lower() == target:
                matching_exts.append(ext)

        if not matching_exts:
            container = KyroContainer(accent_color=None)
            available = [e.split(".")[-1] for e in self.bot.extensions.keys()]
            container.add_section(
                content=(
                    f"**Module Not Found: `{target}`**\n"
                    f"> Available cogs:\n"
                    f"> `{'`, `'.join(sorted(available))}`\n\n"
                    f"-# Tip: Use `?reload` to reload all extensions at once."
                )
            )
            container.add_separator(divider=True)
            container.add_text("-# Powered by Kyro Studio")
            await send_container_response(ctx, container)
            return

        reloaded = []
        failed = []
        for ext in matching_exts:
            try:
                await self.bot.reload_extension(ext)
                reloaded.append(ext.split(".")[-1])
            except Exception as e:
                failed.append(f"{ext.split('.')[-1]}: {e}")

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        container = KyroContainer(accent_color=None)

        if not failed:
            container.add_section(
                content=(
                    f"### Module Reloaded\n"
                    f"> **Modules:** `{'`, `'.join(reloaded)}`\n"
                    f"> **Execution Time:** `{elapsed_ms:.1f}ms`\n"
                    f"> **Status:** `Active & Fresh`"
                )
            )
        else:
            container.add_section(
                content=(
                    f"### Module Reload Issues\n"
                    f"> **Reloaded:** `{'`, `'.join(reloaded)}`\n"
                    f"> **Failed:** `{'`, `'.join(failed)}`"
                )
            )

        container.add_separator(divider=True)
        container.add_text("-# Powered by Kyro Studio")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ReloadCog(bot))

