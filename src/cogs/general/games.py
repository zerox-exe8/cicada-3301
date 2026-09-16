"""
Kyro Discord Bot - Games & Fun Module
Provides community entertainment commands (Mimic webhook impersonation, Fake Hack terminal, Fake Nitro gift).
"""

from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class FakeNitroView(discord.ui.View):
    """Interactive Fake Nitro Gift view that trolls the claimer."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim Nitro (1 Year Free)",
        style=discord.ButtonStyle.success,
        custom_id="fake_nitro:claim_btn",
    )
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Troll response when any member tries to claim fake nitro."""
        troll_container = KyroContainer(accent_color=None)
        troll_container.add_section(
            content=(
                "**Nice Try! Free Nitro Denied**\n"
                "> You really thought you were getting free Discord Nitro?\n"
                "> Stay safe from phishing links and don't click random gifts!"
            )
        )
        troll_container.add_separator(divider=True)
        troll_container.add_text("-# Trolled by Kyro Studio")
        await interaction.response.send_message(
            embed=troll_container.to_embed(),
            ephemeral=True,
        )


class Games(commands.Cog, name="Games"):
    """Community entertainment and interactive fun suite."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="mimic",
        aliases=["clone", "impersonate"],
        description="Send a message as another user using dynamic server webhooks.",
    )
    @commands.guild_only()
    async def mimic(self, ctx: CustomContext, member: discord.Member, *, message: str) -> None:
        """Send a message disguised as another server member."""
        if not ctx.guild or not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send_error("This command can only be executed in server text channels.")
            return

        # Check bot permissions for managing webhooks
        me = ctx.guild.me
        if not ctx.channel.permissions_for(me).manage_webhooks:
            await ctx.send_error("I need `Manage Webhooks` permission in this channel to mimic members.")
            return

        # Delete user invocation message to maintain stealth illusion
        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        # Sanitize message to prevent ghost mentions or mass @everyone abuse
        clean_content = message.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
        if not clean_content.strip():
            return

        try:
            # Find existing or create temporary webhook
            webhooks = await ctx.channel.webhooks()
            webhook = next((w for w in webhooks if w.user == self.bot.user), None)
            if not webhook:
                webhook = await ctx.channel.create_webhook(name="Kyro-Mimic")

            # Execute webhook impersonation with member identity
            await webhook.send(
                content=clean_content,
                username=member.display_name,
                avatar_url=member.display_avatar.url,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as err:
            await ctx.send_error(f"Failed to execute mimic: {err}")

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

        # Fake details generation
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

    @commands.hybrid_command(
        name="nitro",
        aliases=["fakenitro"],
        description="Generate a realistic Discord Nitro gift card that trolls anyone who claims it.",
    )
    @commands.guild_only()
    async def fake_nitro(self, ctx: CustomContext) -> None:
        """Drop a fake Discord Nitro gift card in chat."""
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**A Wild Discord Nitro Gift Appeared!**\n"
                "> Someone dropped a **Discord Nitro 1-Year Subscription** in this channel.\n"
                "> Click the button below to claim it before someone else does!"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            "- **Tier:** Nitro All-Access (Boosts + HD Streaming)\n"
            "- **Expires:** In 48 hours\n"
            "- **Status:** Ready to Claim"
        )
        container.add_separator(divider=True)
        container.add_text("-# Discord Official Partner Gift")

        view = FakeNitroView()
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    """Load Games cog into KyroBot."""
    await bot.add_cog(Games(bot))
