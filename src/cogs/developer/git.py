from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class GitCog(commands.Cog, name="Developer-Git"):
    """Git repository version and deployment telemetry."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.root_dir = Path(__file__).resolve().parent.parent.parent.parent

    async def _run_git(self, *args: str) -> str:
        cmd = ["git", "-C", str(self.root_dir), *args]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return stdout.decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    @commands.command(name="git", aliases=["repo", "commit", "version"])
    @is_developer()
    async def view_git(self, ctx: CustomContext) -> None:
        """
        Inspect live Git repository branch, commit, and sync status.
        Usage:
          ?git
        """
        branch = await self._run_git("rev-parse", "--abbrev-ref", "HEAD") or "main"
        commit_hash = await self._run_git("rev-parse", "--short", "HEAD") or "Unknown"
        author = await self._run_git("log", "-1", "--format=%an") or "Unknown"
        date_str = await self._run_git("log", "-1", "--format=%cd", "--date=relative") or "Recently"
        subject = await self._run_git("log", "-1", "--format=%s") or "No commit message"
        status_raw = await self._run_git("status", "--porcelain")
        is_dirty = bool(status_raw)
        dirty_flag = "dirty" if is_dirty else "clean"
        info_lines = [
            f"branch:  {branch}",
            f"commit:  {commit_hash} ({date_str})",
            f"author:  {author}",
            f"message: {subject}",
            f"tree:    {dirty_flag}",
        ]
        text_block = "\n".join(info_lines)

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"```yaml\n{text_block}\n```")
        container.add_separator(divider=True)
        container.add_text(f"-# git • {self.root_dir.name}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(GitCog(bot))
