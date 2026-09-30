"""
Kyro Discord Bot - Administrators & Admin Roles Audit Module
Discovers and lists all roles and members holding full Administrator permissions without unwanted pings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.Admins")


class Admins(commands.Cog, name="Moderation-Admins"):
    """Server administrator audit module."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="admins",
        aliases=["adminroles", "listadmins"],
        description="Audit and list all roles and members holding Administrator permissions.",
    )
    @commands.guild_only()
    async def admins(self, ctx: CustomContext) -> None:
        """List all administrator roles and authorized members."""
        guild = ctx.guild
        if not guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        admin_roles = [r for r in guild.roles if r.permissions.administrator and not r.is_default()]
        admin_roles.sort(key=lambda r: r.position, reverse=True)
        admin_roles_tags = [f"`@{r.name}`" for r in admin_roles]
        admin_roles_str = ", ".join(admin_roles_tags) if admin_roles_tags else "None"

        admin_members = [m for m in guild.members if m.guild_permissions.administrator]
        admin_members.sort(key=lambda m: (m.id != guild.owner_id, m.top_role.position), reverse=True)

        human_admins = [m for m in admin_members if not m.bot]
        bot_admins = [m for m in admin_members if m.bot]

        owner = guild.owner or await self.bot.fetch_user(guild.owner_id) if guild.owner_id else None
        owner_str = f"{owner.name} (ID: `{guild.owner_id}`)" if owner else f"ID: `{guild.owner_id}`"

        human_lines = [f"{m.name} (ID: `{m.id}`)" for m in human_admins[:15]]
        if len(human_admins) > 15:
            human_lines.append(f"-# ...and {len(human_admins) - 15} more human admins")

        bot_lines = [f"{m.name} (ID: `{m.id}`)" for m in bot_admins[:10]]
        if len(bot_admins) > 10:
            bot_lines.append(f"-# ...and {len(bot_admins) - 10} more bot admins")

        container = KyroContainer(accent_color=discord.Color.red().value)
        container.add_section(
            content=(
                f"### {guild.name} — Administrators\n"
                f"Server Owner: `{owner_str}`\n"
                f"Admin Roles: {admin_roles_str}\n"
                f"Total Admins: `{len(admin_members)}` ({len(human_admins)} humans, {len(bot_admins)} bots)"
            )
        )
        container.add_separator(divider=True)

        if human_lines:
            container.add_section(
                content="**Human Administrators**\n" + "\n".join(human_lines)
            )
            container.add_separator(divider=True)

        if bot_lines:
            container.add_section(
                content="**Bot Administrators**\n" + "\n".join(bot_lines)
            )
            container.add_separator(divider=True)

        container.add_text(f"-# Audited by {ctx.author.name}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Admins(bot))
