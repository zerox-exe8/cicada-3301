"""
Kyro Discord Bot - Fake Nitro Gift Command
Creates a realistic Discord Nitro gift card with an interactive claim button that trolls members.
"""

from __future__ import annotations

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


class NitroCog(commands.Cog, name="Games-Nitro"):
    """Fake Nitro gift trolling suite."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

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
    await bot.add_cog(NitroCog(bot))
