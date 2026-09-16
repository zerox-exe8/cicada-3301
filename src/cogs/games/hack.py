"""
Kyro Discord Bot - Fake Hack Terminal Command
Simulates an interactive hacker terminal sequence trolling a target member.
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class HackCog(commands.Cog, name="Games-Hack"):
    """Fake hacker simulation suite."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="hack",
        aliases=["fakehack", "trollhack"],
        description="Simulate an interactive fake terminal hack sequence on a target member.",
    )
    @commands.guild_only()
    async def fake_hack(self, ctx: CustomContext, member: discord.Member) -> None:
        """Run a simulated real-time terminal hacking sequence on a friend."""
        e_reg = getattr(self.bot, "custom_emojis", {})
        dot = e_reg.get("heart_dot", "-")

        fake_passwords = ["iloveanime123", "password2024", "secretcat99", "admin1234", "qwertyuiop"]
        fake_password = random.choice(fake_passwords)
        fake_ip = f"192.168.{random.randint(1, 254)}.{random.randint(1, 254)}"
        fake_token = f"mfa.{random.randint(10000000, 99999999)}...[ENCRYPTED]"
        fake_searches = [
            "how to get free discord nitro 2026",
            "why do my friends ignore me",
            "how to look cool on discord",
            "is 1+1 really 2",
        ]
        fake_search = random.choice(fake_searches)

        stages = [
            f"{dot} **Phase 1:** Injecting backdoor payload into `{member.name}`'s client...",
            f"{dot} **Phase 2:** Bypassing Discord 2FA & cracking master password (`{fake_password}`)...",
            f"{dot} **Phase 3:** Extracting private browser search history (`\"{fake_search}\"`)...",
            f"{dot} **Phase 4:** Scraping Discord authorization token (`{fake_token}`)...",
            f"{dot} **Phase 5:** Uploading all saved photos & DMs to darkweb database...",
        ]

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Terminal Breach: Infiltrating `{member.display_name}`**\n"
                f"> Target ID: `{member.id}` • Gateway: `ESTABLISHED`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(stages[0])
        container.add_separator(divider=True)
        container.add_text("-# Initializing zero-day exploit...")

        msg = await ctx.send(embed=container.to_embed())

        for idx, stage in enumerate(stages[1:], start=2):
            await asyncio.sleep(1.4)
            current_log = "\n".join(stages[:idx])
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Terminal Breach: Infiltrating `{member.display_name}`**\n"
                    f"> Target ID: `{member.id}` • Status: `Infiltrating ({idx}/5)`"
                )
            )
            container.add_separator(divider=True)
            container.add_text(current_log)
            container.add_separator(divider=True)
            container.add_text(f"-# Executing payload stage {idx}...")
            try:
                await msg.edit(embed=container.to_embed())
            except discord.HTTPException:
                break

        await asyncio.sleep(1.4)
        final_container = KyroContainer(accent_color=None)
        final_container.add_section(
            content=(
                f"**Terminal Breach Complete: `{member.display_name}` Owned**\n"
                f"> All sensitive account data successfully gathered."
            )
        )
        final_container.add_separator(divider=True)
        final_summary = (
            f"{dot} **Target:** {member.mention} (`{member.id}`)\n"
            f"{dot} **Password:** `{fake_password}`\n"
            f"{dot} **IP Address:** `{fake_ip}`\n"
            f"{dot} **Recent Search:** `{fake_search}`\n"
            f"{dot} **Discord Token:** `{fake_token}`"
        )
        final_container.add_text(final_summary)
        final_container.add_separator(divider=True)
        final_container.add_text("-# 100% Fake Simulation • Powered by Kyro Studio")
        try:
            await msg.edit(embed=final_container.to_embed())
        except discord.HTTPException:
            pass


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(HackCog(bot))
