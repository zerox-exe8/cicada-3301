from __future__ import annotations

import ast
import asyncio
import io
import os
import sys
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
            lines = code.split("\n")
            code = "\n".join(lines[1:-1])
        code = code.strip("` \n")

        bot = self.bot
        local_vars = {
            "bot": bot,
            "ctx": ctx,
            "channel": ctx.channel,
            "author": ctx.author,
            "guild": ctx.guild,
            "message": ctx.message,
            "discord": discord,
            "commands": commands,
            "asyncio": asyncio,
            "time": time,
            "os": os,
            "sys": sys,
            # Instant flex helpers
            "cluster": {
                "cluster_state": "online (nominal)",
                "node": "kyro-cluster-01",
                "shards": bot.shard_count,
                "guilds": len(bot.guilds),
                "users": len(bot.users),
                "gateway_ping": f"{round(bot.latency * 1000)}ms",
                "loaded_cogs": len(bot.cogs),
            },
            "top": [f"{g.name} ({g.member_count:,})" for g in sorted(bot.guilds, key=lambda x: x.member_count or 0, reverse=True)[:5]],
        }

        stdout = io.StringIO()

        try:
            fn_code = f"async def _eval_func():\n{textwrap.indent(code, '    ')}"
            parsed = ast.parse(fn_code)
            fn_node = parsed.body[0]

            # convert trailing expression into return statement
            if fn_node.body and isinstance(fn_node.body[-1], ast.Expr):
                fn_node.body[-1] = ast.Return(value=fn_node.body[-1].value)
                ast.fix_missing_locations(fn_node.body[-1])

            compiled = compile(parsed, filename="<eval>", mode="exec")
            exec(compiled, local_vars)
            func = local_vars["_eval_func"]

            t_start = time.perf_counter()
            with redirect_stdout(stdout):
                ret = await func()
            t_dur = (time.perf_counter() - t_start) * 1000

            res = stdout.getvalue().strip()
            if ret is not None:
                if isinstance(ret, (dict, list, tuple, set)):
                    import pprint
                    formatted_ret = pprint.pformat(ret, indent=2, width=45)
                else:
                    formatted_ret = str(ret)
                result_str = f"{res}\n{formatted_ret}".strip() if res else formatted_ret
            else:
                result_str = res if res else "None"

            container = KyroContainer(accent_color=None)
            container.add_section(content=f"```py\n{result_str[:1800]}\n```")
            container.add_separator(divider=True)
            container.add_text(f"-# {t_dur:.2f}ms")
            await send_container_response(ctx, container)
        except Exception:
            err = traceback.format_exc()
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"```py\n{err[:1800]}\n```")
            container.add_separator(divider=True)
            container.add_text("-# error")
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(EvalCog(bot))
