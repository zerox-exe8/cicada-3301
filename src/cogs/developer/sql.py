from __future__ import annotations

import io
import time
from typing import TYPE_CHECKING
import discord
from discord.ext import commands
from tabulate import tabulate

from src.core.context import CustomContext
from src.managers.permission_manager import is_owner
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class SqlCog(commands.Cog, name="Developer-SQL"):
    """Direct PostgreSQL database query execution."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="sql", aliases=["db", "query"])
    @is_owner()
    async def run_sql(self, ctx: CustomContext, *, query: str) -> None:
        """
        Execute raw SQL query on the connected database.
        Usage:
          ?sql SELECT * FROM guilds LIMIT 5;
        """
        # clean markdown codeblocks if provided
        q_clean = query.strip()
        if q_clean.startswith("```") and q_clean.endswith("```"):
            lines = q_clean.split("\n")
            q_clean = "\n".join(lines[1:-1]).strip()

        t_start = time.perf_counter()
        try:
            is_select = q_clean.strip().upper().startswith(("SELECT", "WITH", "EXPLAIN", "SHOW"))

            if is_select:
                rows = await self.bot.db.fetch_all(q_clean)
                t_dur = (time.perf_counter() - t_start) * 1000

                if not rows:
                    container = KyroContainer(accent_color=None)
                    container.add_section(content="```sql\n(0 rows returned)\n```")
                    container.add_separator(divider=True)
                    container.add_text(f"-# 0 rows • {t_dur:.2f}ms")
                    await send_container_response(ctx, container)
                    return

                # convert Record objects to dict
                dict_rows = [dict(r) for r in rows]
                headers = list(dict_rows[0].keys())
                values = [list(r.values()) for r in dict_rows]

                table_str = tabulate(values, headers=headers, tablefmt="psql")

                container = KyroContainer(accent_color=None)
                if len(table_str) <= 1800:
                    container.add_section(content=f"```sql\n{table_str}\n```")
                    container.add_separator(divider=True)
                    container.add_text(f"-# {len(rows):,} rows • {t_dur:.2f}ms")
                    await send_container_response(ctx, container)
                else:
                    snippet = table_str[:1500] + "\n... (truncated)"
                    container.add_section(content=f"```sql\n{snippet}\n```")
                    container.add_separator(divider=True)
                    container.add_text(f"-# {len(rows):,} rows • {t_dur:.2f}ms • full table attached")
                    
                    file = discord.File(
                        io.BytesIO(table_str.encode("utf-8")),
                        filename="query_result.txt"
                    )
                    await ctx.reply(file=file)
                    await send_container_response(ctx, container)

            else:
                status = await self.bot.db.execute(q_clean)
                t_dur = (time.perf_counter() - t_start) * 1000

                container = KyroContainer(accent_color=None)
                container.add_section(content=f"```sql\n{status or 'OK'}\n```")
                container.add_separator(divider=True)
                container.add_text(f"-# {t_dur:.2f}ms")
                await send_container_response(ctx, container)

        except Exception as e:
            await ctx.send_error(f"SQL Execution Error: `{e}`")


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(SqlCog(bot))
