"""
Kyro Discord Bot - Module Hot-Reloading Suite
Enables real-time code reloading without restarting the bot process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    async def reload_module(self, ctx: CustomContext, module_name: str) -> None:
        """Hot-reload a cog without restarting the bot."""
        mod = module_name.strip()
        if not mod.startswith("src.cogs."):
            # Try finding shortcut
            if "." not in mod:
                for ext in list(self.bot.extensions.keys()):
                    if ext.endswith(f".{mod}") or ext.endswith(f"._{mod}"):
                        mod = ext
                        break
            else:
                mod = f"src.cogs.{mod}"

        try:
            await self.bot.reload_extension(mod)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Module Reloaded**\n"
                    f"> **Path:** `{mod}`\n"
                    f"> **Status:** `Active & Fresh`"
                )
            )
            await send_container_response(ctx, container)
        except Exception as e:
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Failed to reload `{mod}`:**\n`{e}`")
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ReloadCog(bot))
