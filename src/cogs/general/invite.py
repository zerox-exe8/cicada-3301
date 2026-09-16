"""
Kyro Discord Bot - Official Invite & Community Links Command (Components V2)
Presents a sleek, aesthetic Discord Components V2 card with instant authorization links.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class InviteView(discord.ui.View):
    """Clean, single-row link buttons for bot authorization and support server."""

    def __init__(self, invite_url: str, support_url: str | None = None) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label=f"Invite {Config.BOT_NAME}",
                style=discord.ButtonStyle.link,
                url=invite_url,
            )
        )
        if support_url:
            self.add_item(
                discord.ui.Button(
                    label="Support Server",
                    style=discord.ButtonStyle.link,
                    url=support_url,
                )
            )


class Invite(commands.Cog):
    """Bot invitation, official links, and community support."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="invite",
        aliases=["inv", "addbot", "links", "support"],
        description="Get official authorization links to invite Kyro to your server.",
    )
    async def invite(self, ctx: CustomContext) -> None:
        """Display Kyro's sleek official invite card and support server access."""
        client_id = self.bot.user.id if self.bot.user else 1544289369907658853

        invite_url = (
            Config.INVITE_URL
            if Config.INVITE_URL
            else f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions=8&integration_type=0&scope=bot+applications.commands"
        )

        support_url = Config.SUPPORT_URL or "https://discord.gg/kBKnvBVCj7"

        bot_avatar = self.bot.user.display_avatar.url if self.bot.user else None
        guilds_count = len(self.bot.guilds)
        users_count = len(self.bot.users)

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Invite {Config.BOT_NAME}**\n"
                "> Next-generation Discord ecosystem built for studio-grade lossless music, high-speed moderation, and server automation.\n\n"
                f"> Serving **{guilds_count:,} servers** and **{users_count:,} members**."
            ),
            accessory={"type": 11, "media": {"url": bot_avatar}} if bot_avatar else None,
        )
        container.add_separator(divider=True)
        container.add_text("-# Click an authorization link below to add Kyro to your server.")

        view = InviteView(invite_url=invite_url, support_url=support_url)
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    """Load the Invite cog into KyroBot."""
    await bot.add_cog(Invite(bot))
