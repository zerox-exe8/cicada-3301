from __future__ import annotations

import asyncio
from pathlib import Path
import time
from typing import TYPE_CHECKING, Optional

from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class ReloadCog(commands.Cog, name="Developer-Reload"):
    """Live module hot-reloading and git sync."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.root_dir = Path(__file__).resolve().parent.parent.parent.parent
        self.cogs_dir = self.root_dir / "src" / "cogs"

    def _discover_all_cogs(self) -> list[str]:
        """Discover all valid cog module strings from disk."""
        modules = []
        for file in self.cogs_dir.rglob("*.py"):
            if any(part.startswith("_") for part in file.relative_to(self.cogs_dir).parts):
                continue
            rel = file.relative_to(self.root_dir)
            mod = ".".join(rel.with_suffix("").parts)
            modules.append(mod)
        return modules

    async def _reload_or_load(self, ext: str) -> None:
        """Reload extension if already loaded, otherwise load it."""
        if ext in self.bot.extensions:
            await self.bot.reload_extension(ext)
        else:
            await self.bot.load_extension(ext)

    @commands.command(name="pull", aliases=["update"])
    @is_developer()
    async def git_pull(self, ctx: CustomContext) -> None:
        """
        Pull latest code from git remote and hot-reload all cogs.
        Usage:
          ?pull
        """
        t_start = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "-C", str(self.root_dir), "pull",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            out_str = stdout.decode("utf-8", errors="replace").strip()
            err_str = stderr.decode("utf-8", errors="replace").strip()
            git_output = out_str or err_str or "No output from git"
        except Exception as e:
            await ctx.send_error(f"Git pull failed: `{e}`")
            return

        # now trigger full reload
        all_exts = self._discover_all_cogs()
        self_ext = "src.cogs.developer.reload"
        if self_ext in all_exts:
            all_exts.remove(self_ext)
            all_exts.append(self_ext)

        reloaded = []
        failed = []
        for ext in all_exts:
            try:
                await self._reload_or_load(ext)
                reloaded.append(ext.split(".")[-1])
            except Exception as e:
                failed.append(f"{ext.split('.')[-1]}: {e}")

        t_dur = (time.perf_counter() - t_start) * 1000

        info = [
            f"git:      {git_output.splitlines()[-1] if git_output.splitlines() else git_output}",
            f"reloaded: {len(reloaded)} cogs",
            f"failed:   {len(failed)}",
        ]
        if failed:
            info.append("errors:")
            for f in failed[:3]:
                info.append(f"  - {f}")

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"```yaml\n" + "\n".join(info) + "\n```")
        container.add_separator(divider=True)
        container.add_text(f"-# {t_dur:.1f}ms • pull & reload")
        await send_container_response(ctx, container)

    @commands.command(name="reload", aliases=["r"])
    @is_developer()
    async def reload_module(self, ctx: CustomContext, *, module_name: Optional[str] = None) -> None:
        """
        Hot-reload cogs without restarting the bot.
        Usage:
          ?reload           -> Reloads all cogs on disk
          ?reload music     -> Reloads the music module
          ?reload general   -> Reloads all general category cogs
        """
        t_start = time.perf_counter()
        try:
            target = (module_name or "").strip().lower()

            if target in ("pull", "git"):
                await self.git_pull(ctx)
                return

            if not target or target in ("all", "*", "everything"):
                all_exts = self._discover_all_cogs()
                self_ext = "src.cogs.developer.reload"
                if self_ext in all_exts:
                    all_exts.remove(self_ext)
                    all_exts.append(self_ext)

                reloaded = []
                failed = []

                for ext in all_exts:
                    try:
                        await self._reload_or_load(ext)
                        reloaded.append(ext.split(".")[-1])
                    except Exception as e:
                        failed.append(f"{ext.split('.')[-1]}: {e}")

                t_dur = (time.perf_counter() - t_start) * 1000

                info = [
                    f"reloaded: {len(reloaded)} cogs",
                    f"failed:   {len(failed)}",
                ]
                if failed:
                    info.append("errors:")
                    for f in failed[:5]:
                        info.append(f"  - {f}")

                container = KyroContainer(accent_color=None)
                container.add_section(content=f"```yaml\n" + "\n".join(info) + "\n```")
                container.add_separator(divider=True)
                container.add_text(f"-# {t_dur:.1f}ms")
                await send_container_response(ctx, container)
                return

            # specific cog or category target
            discovered = self._discover_all_cogs()
            matching_exts = []
            for ext in discovered:
                if ext.lower().endswith(f".{target}") or ext.lower().endswith(f"._{target}"):
                    matching_exts.append(ext)
                elif f".{target}." in ext.lower():
                    matching_exts.append(ext)
                elif ext.lower() == target:
                    matching_exts.append(ext)

            if not matching_exts:
                available = sorted({e.split(".")[-1] for e in discovered})
                container = KyroContainer(accent_color=None)
                container.add_section(content=f"```yaml\nerror: module '{target}' not found\navailable: [{', '.join(available[:15])}...]\n```")
                container.add_separator(divider=True)
                container.add_text("-# use ?reload to reload all cogs")
                await send_container_response(ctx, container)
                return

            reloaded = []
            failed = []
            for ext in matching_exts:
                try:
                    await self._reload_or_load(ext)
                    reloaded.append(ext.split(".")[-1])
                except Exception as e:
                    failed.append(f"{ext.split('.')[-1]}: {e}")

            t_dur = (time.perf_counter() - t_start) * 1000
            info = [
                f"reloaded: {', '.join(reloaded) if reloaded else 'none'}",
                f"failed:   {len(failed)}",
            ]
            if failed:
                info.append("errors:")
                for f in failed[:3]:
                    info.append(f"  - {f}")

            container = KyroContainer(accent_color=None)
            container.add_section(content=f"```yaml\n" + "\n".join(info) + "\n```")
            container.add_separator(divider=True)
            container.add_text(f"-# {t_dur:.1f}ms")
            await send_container_response(ctx, container)

        except Exception as e:
            await ctx.send_error(f"Reload error: `{e}`")


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ReloadCog(bot))


