"""
Kyro Discord Bot - Ultra-Realistic Fake Nitro Gift Command
Produces a pixel-perfect Discord Nitro gift card with a green 'Accept' button.
Trolls anyone who clicks it with an ephemeral Rickroll screen while leaving the card active.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext

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
        troll_embed = discord.Embed(
            title="You Got Rickrolled!",
            description=(
                "**Did you really think you were getting free Discord Nitro?**\n\n"
                "> Never gonna give you up,\n"
                "> Never gonna let you down,\n"
                "> Never gonna run around and desert you!\n\n"
                "-# Always verify gift sources before clicking random links."
            ),
            color=discord.Color.from_rgb(244, 127, 255),
        )
        troll_embed.set_image(url="https://media1.tenor.com/m/x8v1oNUOmg4AAAAd/rickroll-roll.gif")
        await interaction.response.send_message(embed=troll_embed, ephemeral=True)


class NitroCog(commands.Cog, name="Games-Nitro"):
    """Ultra-realistic Discord Nitro gift simulator."""
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
        """Deploy a deceptive native-styled Discord Nitro gift card."""
        # Instantly purge command invocation so members don't know it's a command
        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        # Native Discord Nitro Gift Card Embed
        embed = discord.Embed(
            title="You've been gifted a subscription!",
            description="**Discord Nitro**\nExpires in 48 hours",
            color=discord.Color.from_rgb(43, 45, 49),
        )
        embed.set_author(
            name="Discord Nitro",
            icon_url="https://assets-global.website-files.com/6257adef93867e50d84d30e2/636e0a6a49cf127bf92de1e2_icon_clyde_blurple_RGB.png",
        )
        embed.set_thumbnail(url="https://i.imgur.com/w9ai84b.png")

        view = FakeNitroView()

        # If channel permits webhooks, send as the author so it looks like they dropped it
        sent = False
        if isinstance(ctx.channel, discord.TextChannel) and ctx.guild:
            if ctx.channel.permissions_for(ctx.guild.me).manage_webhooks:
                try:
                    webhooks = await ctx.channel.webhooks()
                    webhook = next((w for w in webhooks if w.user == self.bot.user), None)
                    if not webhook:
                        webhook = await ctx.channel.create_webhook(name="Kyro-Nitro")

                    await webhook.send(
                        embed=embed,
                        view=view,
                        username=ctx.author.display_name,
                        avatar_url=ctx.author.display_avatar.url,
                    )
                    sent = True
                except discord.HTTPException:
                    pass

        if not sent:
            await ctx.channel.send(embed=embed, view=view)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(NitroCog(bot))
