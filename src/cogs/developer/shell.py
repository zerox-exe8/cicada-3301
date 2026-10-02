from __future__ import annotations

import asyncio
import io
import time
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_owner
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class ShellCog(commands.Cog, name="Developer-Shell"):
    """Host terminal shell command execution."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="shell", aliases=["sh", "bash", "cmd", "exec"])
    @is_owner()
    async def run_shell(self, ctx: CustomContext, *, command: str) -> None:
        """
        Execute command on host terminal shell.
        Usage:
          ?sh <command>
        """
        # clean markdown codeblocks if provided
        cmd_clean = command.strip()
        if cmd_clean.startswith("```") and cmd_clean.endswith("```"):
            lines = cmd_clean.split("\n")
            cmd_clean = "\n".join(lines[1:-1]).strip()

        t_start = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd_clean,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            except asyncio.TimeoutError:
                proc.kill()
                await ctx.send_error("Shell execution timed out after 30 seconds.")
                return

            t_dur = (time.perf_counter() - t_start) * 1000
            out_str = stdout_bytes.decode("utf-8", errors="replace").strip()
            err_str = stderr_bytes.decode("utf-8", errors="replace").strip()

            combined = ""
            if out_str:
                combined += out_str
            if err_str:
                if combined:
                    combined += "\n\n[STDERR]\n"
                combined += err_str

            if not combined:
                combined = "(Command executed with no output)"

            exit_code = proc.returncode

            container = KyroContainer(accent_color=None)
            if len(combined) <= 1800:
                container.add_section(content=f"```bash\n{combined}\n```")
                container.add_separator(divider=True)
                container.add_text(f"-# {t_dur:.2f}ms • exit code {exit_code}")
                await send_container_response(ctx, container)
            else:
                snippet = combined[:1500] + "\n... (truncated)"
                container.add_section(content=f"```bash\n{snippet}\n```")
                container.add_separator(divider=True)
                container.add_text(f"-# {t_dur:.2f}ms • exit code {exit_code} • full log attached")
                
                file = discord.File(
                    io.BytesIO(combined.encode("utf-8")),
                    filename="shell_output.log"
                )
                await ctx.reply(file=file)
                await send_container_response(ctx, container)

        except Exception as e:
            await ctx.send_error(f"Failed to execute shell process: {e}")


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ShellCog(bot))
