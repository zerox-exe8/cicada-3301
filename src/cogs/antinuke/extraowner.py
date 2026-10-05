from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class AntinukeExtraOwnerCog(commands.Cog):
    """Extra Owner management for Kyro Antinuke (Strictly Server Owner Only)."""
    category: str = "Security"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_group(
        name="extraowner",
        aliases=["eo"],
        description="Manage Extra Owners who can configure Antinuke and bypass triggers.",
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def extraowner(self, ctx: CustomContext) -> None:
        """View list of current Extra Owners."""
        await ctx.invoke(self.bot.get_command("extraowner list"))

    @extraowner.command(name="add", description="Promote a trusted user to Extra Owner (Server Owner only).")
    @app_commands.describe(user="User to promote to Extra Owner")
    async def extraowner_add(self, ctx: CustomContext, user: discord.User) -> None:
        """Add an Extra Owner."""
        if ctx.author.id != ctx.guild.owner_id:
            await ctx.send_error("Only the **Server Owner** can assign Extra Owners.")
            return

        if user.id == ctx.guild.owner_id:
            await ctx.send_error("The Server Owner already possesses master immunity.")
            return

        if user.bot:
            await ctx.send_error("Bots cannot be designated as Extra Owners. Use `,whitelist add <bot>` instead.")
            return

        await self.bot.antinuke_mgr.add_extra_owner(ctx.guild.id, user.id, ctx.author.id)

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Extra Owner Assigned**")
        container.add_separator(divider=True)
        container.add_text(
            f"• **User:** **{user.name}** `「{user.id}」`\n"
            f"• **Access:** Full Antinuke immunity and configuration access."
        )
        await send_container_response(ctx, container)

    @extraowner.command(name="remove", description="Revoke Extra Owner status from a user (Server Owner only).")
    @app_commands.describe(user="User to revoke Extra Owner from")
    async def extraowner_remove(self, ctx: CustomContext, user: discord.User) -> None:
        """Revoke Extra Owner status."""
        if ctx.author.id != ctx.guild.owner_id:
            await ctx.send_error("Only the **Server Owner** can revoke Extra Owners.")
            return

        if not self.bot.antinuke_mgr.is_extra_owner(ctx.guild.id, user.id):
            await ctx.send_error(f"**{user.name}** is not registered as an Extra Owner.")
            return

        await self.bot.antinuke_mgr.remove_extra_owner(ctx.guild.id, user.id)

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Extra Owner Revoked**")
        container.add_separator(divider=True)
        container.add_text(f"• **User:** **{user.name}** `「{user.id}」` has been demoted.")
        await send_container_response(ctx, container)

    @extraowner.command(name="list", description="List all registered Extra Owners.")
    async def extraowner_list(self, ctx: CustomContext) -> None:
        """Display list of all registered Extra Owners."""
        owner_ids = self.bot.antinuke_mgr.get_extra_owners(ctx.guild.id)

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Extra Owners Registry**")
        container.add_separator(divider=True)

        if not owner_ids:
            container.add_text("• No Extra Owners configured.")
        else:
            lines = []
            for uid in owner_ids:
                u = self.bot.get_user(uid)
                u_str = f"**{u.name}**" if u else f"<@{uid}>"
                lines.append(f"• {u_str} `「{uid}」`")
            container.add_text("\n".join(lines))

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load AntinukeExtraOwnerCog."""
    await bot.add_cog(AntinukeExtraOwnerCog(bot))
