"""
Kyro Discord Bot - Official Invite & Community Links Command
Presents high-aesthetic Discord Components V2 card with instant authorization links.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class InviteView(discord.ui.View):
    """Link buttons for official bot invitation and community support server."""

    def __init__(self, admin_url: str, standard_url: str, support_url: str) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label="Invite Kyro (Recommended)",
                style=discord.ButtonStyle.link,
                url=admin_url,
            )
        )
        self.add_item(
            discord.ui.Button(
                label="Invite (Standard)",
                style=discord.ButtonStyle.link,
                url=standard_url,
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
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="invite",
        aliases=["inv", "addbot", "links", "support"],
        description="Get official authorization links to invite Kyro to your server.",
    )
    async def invite(self, ctx: CustomContext) -> None:
        """Display Kyro's official invite cards and support server access."""
        client_id = self.bot.user.id if self.bot.user else 1544289369907658853

        # 1. Administrator Permissions (Recommended for zero-friction setup)
        admin_invite = (
            Config.INVITE_URL
            if Config.INVITE_URL
            else f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions=8&integration_type=0&scope=bot+applications.commands"
        )

        # 2. Standard Permissions (Roles, Channels, Messages, Voice, Moderation)
        standard_invite = (
            f"https://discord.com/oauth2/authorize?client_id={client_id}&permissions=1099513077790&integration_type=0&scope=bot+applications.commands"
        )

        support_url = Config.SUPPORT_URL or "https://discord.gg/kBKnvBVCj7"

        e_reg = getattr(self.bot, "custom_emojis", {})
        dot = e_reg.get("heart_dot", "-")
        sparkle = e_reg.get("icons_correct", "")
        sparkle_str = f"{sparkle} " if sparkle else ""

        guilds_count = len(self.bot.guilds)
        users_count = len(self.bot.users)

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{sparkle_str}Invite {Config.BOT_NAME} to Your Server**\n"
                f"> All-in-one Discord ecosystem built for lossless audio, high-speed moderation, and server automation."
            )
        )
        container.add_separator(divider=True)

        features = (
            f"{dot} **Studio Lossless Audio:** 24/7 high-fidelity playback, playlists & filters.\n"
            f"{dot} **Intelligent Moderation:** Purge bot/human, channel lock, timeout & clean mod logs.\n"
            f"{dot} **Server Automation:** Dual auto-role (human & bot), welcomer & AFK status.\n"
            f"{dot} **Support Tickets:** Interactive Components V2 support panels."
        )
        container.add_text(features)
        container.add_separator(divider=True)

        info = (
            f"{dot} **Recommended:** Administrator (instant zero-friction setup)\n"
            f"{dot} **Standard:** Essential permissions (Voice, Messages, Roles, Channels)"
        )
        container.add_text(info)
        container.add_separator(divider=True)
        container.add_text(f"-# Serving {guilds_count:,} servers and {users_count:,} members • Powered by Kyro")

        # Add interactive action row buttons
        button_items = [
            {
                "type": 2,
                "style": 5,
                "label": "Invite Kyro (Recommended)",
                "url": admin_invite,
            },
            {
                "type": 2,
                "style": 5,
                "label": "Invite (Standard)",
                "url": standard_invite,
            },
        ]
        if support_url:
            button_items.append({
                "type": 2,
                "style": 5,
                "label": "Support Server",
                "url": support_url,
            })

        container.add_action_row(button_items)

        view = InviteView(admin_invite, standard_invite, support_url)
        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    """Load the Invite cog into KyroBot."""
    await bot.add_cog(Invite(bot))
