"""
Kyro Discord Bot - Ultra-Realistic Fake Nitro Gift Command (Components V2)
Produces a Discord Components V2 Nitro gift card with a green 'Accept' button.
Trolls anyone who clicks it with an ephemeral Rickroll Components V2 screen.
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
    """Persistent view with realistic 'Accept' button that drops an ephemeral Rickroll."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Accept",
        style=discord.ButtonStyle.success,
        custom_id="fake_nitro:accept_btn",
    )
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Deliver secret ephemeral Rickroll to anyone who tries to accept."""
        troll_container = KyroContainer(accent_color=None)
        troll_container.add_section(
            content=(
                "**You Got Rickrolled!**\n"
                "> **Did you really think you were getting free Discord Nitro?**\n\n"
                "> Never gonna give you up,\n"
                "> Never gonna let you down,\n"
                "> Never gonna run around and desert you!"
            ),
            accessory={
                "type": 11,
                "media": {
                    "url": "https://media.tenor.com/x8v1oNUOmg4AAAAC/rickroll-roll.gif",
                },
            },
        )
        troll_container.add_separator(divider=True)
        troll_container.add_text("-# Always verify gift sources before clicking random links.")

        await send_container_response(interaction, troll_container, ephemeral=True)


class NitroCog(commands.Cog, name="Games-Nitro"):
    """Ultra-realistic Discord Nitro gift simulator using Components V2."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="nitro",
        aliases=["fakenitro"],
        description="Drop an authentic-looking Discord Nitro gift in the chat to troll members.",
    )
    @commands.guild_only()
    async def fake_nitro(self, ctx: CustomContext) -> None:
        """Deploy a deceptive native Components V2 Discord Nitro gift card."""
        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**You've been gifted a subscription!**\n"
                "> **Discord Nitro** (1 Month)\n"
                "> *Expires in 48 hours*"
            ),
            accessory={
                "type": 11,
                "media": {
                    "url": "https://raw.githubusercontent.com/zerox-exe8/cicada-3301/main/assets/emoji2/icons_colornitro.png",
                },
            },
        )
        container.add_separator(divider=True)
        container.add_text("-# Discord Official Partner Gift")

        view = FakeNitroView()
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(NitroCog(bot))
