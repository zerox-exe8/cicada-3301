from __future__ import annotations

import logging
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.RoleInfo")


class RoleInfo(commands.Cog, name="Moderation-RoleInfo"):
    """Single role dossier and permissions inspector."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="roleinfo",
        aliases=["ri"],
        description="Inspect a role's color, hierarchy position, member count, and permissions.",
    )
    @app_commands.describe(role="Role to inspect")
    @commands.guild_only()
    async def roleinfo(self, ctx: CustomContext, *, role: discord.Role) -> None:
        """Display deep inspection dossier for a role."""
        guild = ctx.guild
        if not guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        created_ts = int(role.created_at.timestamp())
        hex_color = f"#{role.color.value:06X}" if role.color.value else "Default (No Color)"
        total_roles = len(guild.roles)
        hierarchy_pos = f"#{role.position} of {total_roles}"

        hoist_str = "Yes" if role.hoist else "No"
        mention_str = "Yes" if role.mentionable else "No"
        managed_str = "Yes (Integration / Bot)" if role.managed else "No (Standard)"

        perms = role.permissions
        key_perms: list[str] = []
        if perms.administrator:
            key_perms.append("Administrator")
        else:
            if perms.manage_guild:
                key_perms.append("Manage Server")
            if perms.manage_roles:
                key_perms.append("Manage Roles")
            if perms.manage_channels:
                key_perms.append("Manage Channels")
            if perms.ban_members:
                key_perms.append("Ban Members")
            if perms.kick_members:
                key_perms.append("Kick Members")
            if perms.moderate_members:
                key_perms.append("Timeout Members")
            if perms.manage_messages:
                key_perms.append("Manage Messages")

        perms_str = ", ".join(f"`{p}`" for p in key_perms) if key_perms else "Standard / None"

        icon_link = f" | [Icon]({role.display_icon.url})" if role.display_icon else ""

        container = KyroContainer(accent_color=role.color.value if role.color.value else None)
        container.add_section(
            content=(
                f"### @{role.name}\n"
                f"Role ID: `{role.id}`{icon_link}\n"
                f"Created: <t:{created_ts}:F> (<t:{created_ts}:R>)\n\n"
                f"**Properties**\n"
                f"Color: `{hex_color}`\n"
                f"Hierarchy Position: `{hierarchy_pos}`\n"
                f"Members: `{len(role.members):,}`\n"
                f"Hoisted: `{hoist_str}` | Mentionable: `{mention_str}` | Managed: `{managed_str}`\n\n"
                f"**Permissions**\n"
                f"{perms_str}"
            )
        )

        if role.display_icon:
            container.add_thumbnail(str(role.display_icon.url))

        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.name}")

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(RoleInfo(bot))
