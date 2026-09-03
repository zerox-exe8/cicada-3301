"""
Kyro Discord Bot - Asynchronous Code Evaluation Module
Owner-restricted Python execution sandbox for real-time debugging and inspections.
"""

from __future__ import annotations

import io
import time
import textwrap
import traceback
from contextlib import redirect_stdout
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_owner
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class EvalCog(commands.Cog, name="Developer-Eval"):
    """Interactive code execution sandbox."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="eval", aliases=["e", "py"])
    @is_owner()
    async def eval_code(self, ctx: CustomContext, *, code: str) -> None:
        """Execute asynchronous Python code snippet in safe sandbox."""
        # Clean markdown code blocks if provided
        if code.startswith("```") and code.endswith("```"):
            code = "\n".join(code.split("\n")[1:-1])
        code = code.strip("` \n")

        local_vars = {
            "bot": self.bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "discord": discord,
            "commands": commands,
        }

        stdout = io.StringIO()
        func_def = f"async def _eval_func():\n{textwrap.indent(code, '    ')}"

        try:
            exec(func_def, local_vars)
            func = local_vars["_eval_func"]
            t_start = time.perf_counter()
            with redirect_stdout(stdout):
                ret = await func()
            t_dur = (time.perf_counter() - t_start) * 1000

            res = stdout.getvalue()
            result_str = str(ret) if ret is not None else (res.strip() if res else "None")

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Evaluation Output**\n"
                    f"```py\n{result_str[:1500]}\n```"
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Execution Time: {t_dur:.2f}ms")
            await send_container_response(ctx, container)
        except Exception:
            err = traceback.format_exc()
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Evaluation Error**\n"
                    f"```py\n{err[:1500]}\n```"
                )
            )
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(EvalCog(bot))
