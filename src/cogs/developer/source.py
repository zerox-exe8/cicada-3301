from __future__ import annotations

import inspect
import io
from pathlib import Path
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class SourceCog(commands.Cog, name="Developer-Source"):
    """Live Python code and command inspector."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="source", aliases=["src", "inspect"])
    @is_developer()
    async def view_source(self, ctx: CustomContext, *, target: str) -> None:
        """
        Inspect live source code of any command or cog.
        Usage:
          ?source ping
          ?source profile
        """
        query = target.strip().lower()
        cmd = self.bot.get_command(query)
        cog = self.bot.get_cog(target.strip())

        obj = None
        target_name = query
        if cmd:
            obj = cmd.callback
            target_name = f"Command: {cmd.qualified_name}"
        elif cog:
            obj = cog.__class__
            target_name = f"Cog: {cog.qualified_name}"

        if not obj:
            await ctx.send_error(f"Could not locate command or cog matching `{target}`.")
            return

        try:
            source_lines, start_line = inspect.getsourcelines(obj)
            source_code = "".join(source_lines)
            file_path = inspect.getsourcefile(obj) or "Unknown file"

            # make path relative if possible
            try:
                rel_path = Path(file_path).relative_to(Path(__file__).resolve().parent.parent.parent.parent)
            except Exception:
                rel_path = Path(file_path).name

            total_lines = len(source_lines)
            container = KyroContainer(accent_color=None)

            if len(source_code) <= 1700:
                container.add_section(
                    content=(
                        f"`{rel_path}:{start_line}`\n"
                        f"```py\n{source_code}\n```"
                    )
                )
                container.add_separator(divider=True)
                container.add_text(f"-# {total_lines} lines")
                await send_container_response(ctx, container)
            else:
                snippet = "".join(source_lines[:35]) + f"\n... ({total_lines - 35} more lines in file)"
                container.add_section(
                    content=(
                        f"`{rel_path}:{start_line}`\n"
                        f"```py\n{snippet}\n```"
                    )
                )
                container.add_separator(divider=True)
                container.add_text(f"-# {total_lines} lines • attached")

                file = discord.File(
                    io.BytesIO(source_code.encode("utf-8")),
                    filename=f"{query}_source.py"
                )
                await ctx.reply(file=file)
                await send_container_response(ctx, container)

        except Exception as e:
            await ctx.send_error(f"Failed to inspect source: `{e}`")


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(SourceCog(bot))
