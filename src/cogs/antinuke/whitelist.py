from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response
from src.managers.antinuke_manager import PROTECTION_MODULES

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class AntinukeWhitelistCog(commands.Cog):
    """Whitelist management for Kyro Antinuke."""
    category: str = "Security"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    def _build_usage_card(self, ctx: CustomContext) -> KyroContainer:
        """Construct the Components V2 usage guide for whitelist commands (same style as role)."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Whitelist Commands**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} `{prefix}whitelist add <@user or bot>`\n"
            f"{dot} `{prefix}whitelist remove <@user or bot>`\n"
            f"{dot} `{prefix}whitelist list/show`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    @commands.hybrid_group(
        name="whitelist",
        aliases=["wl"],
        description="Manage users or bots immune to antinuke triggers.",
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def whitelist(self, ctx: CustomContext) -> None:
        """Show Whitelist usage guide (same style as role command)."""
        if ctx.invoked_subcommand is not None:
            return

        container = self._build_usage_card(ctx)
        await send_container_response(ctx, container)

    @whitelist.command(name="add", description="Add a user or bot to the antinuke whitelist.")
    @app_commands.describe(
        target="User or bot to whitelist",
        scope="Optional comma-separated modules (e.g. 'channels,roles'). Leave empty for Full Whitelist.",
    )
    async def whitelist_add(
        self,
        ctx: CustomContext,
        target: Union[discord.Member, discord.User],
        scope: Optional[str] = None,
    ) -> None:
        """Add user/bot to whitelist."""
        is_owner = ctx.author.id == ctx.guild.owner_id
        is_eo = self.bot.antinuke_mgr.is_extra_owner(ctx.guild.id, ctx.author.id)
        if not (is_owner or is_eo):
            await ctx.send_error("Only the **Server Owner** or **Extra Owners** can manage the whitelist.")
            return

        is_full = True
        clean_scope = ""
        if scope and scope.strip():
            parts = [p.strip().lower() for p in scope.split(",") if p.strip()]
            invalid = [p for p in parts if p not in PROTECTION_MODULES]
            if invalid:
                allowed_str = ", ".join([f"`{m}`" for m in PROTECTION_MODULES])
                await ctx.send_error(f"Invalid module(s): `{', '.join(invalid)}`.\n> Valid options: {allowed_str}")
                return
            is_full = False
            clean_scope = ",".join(parts)

        await self.bot.antinuke_mgr.add_whitelist(
            ctx.guild.id, target.id, ctx.author.id, is_full=is_full, scope=clean_scope
        )

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Whitelist**")
        container.add_separator(divider=True)
        container.add_text(f"{dot} **Target:** **{target.name}** `「{target.id}」`")
        await send_container_response(ctx, container)

    @whitelist.command(name="remove", description="Remove a user or bot from the antinuke whitelist.")
    @app_commands.describe(target="User or bot to remove from whitelist")
    async def whitelist_remove(self, ctx: CustomContext, target: Union[discord.Member, discord.User]) -> None:
        """Remove user/bot from whitelist."""
        is_owner = ctx.author.id == ctx.guild.owner_id
        is_eo = self.bot.antinuke_mgr.is_extra_owner(ctx.guild.id, ctx.author.id)
        if not (is_owner or is_eo):
            await ctx.send_error("Only the **Server Owner** or **Extra Owners** can manage the whitelist.")
            return

        curr_wl = self.bot.antinuke_mgr.get_whitelist(ctx.guild.id)
        if target.id not in curr_wl:
            await ctx.send_error(f"**{target.name}** is not in the whitelist.")
            return

        await self.bot.antinuke_mgr.remove_whitelist(ctx.guild.id, target.id)

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Whitelist Removed**")
        container.add_separator(divider=True)
        container.add_text(f"• **Target:** **{target.name}** `「{target.id}」` has been removed.")
        await send_container_response(ctx, container)

    @whitelist.command(name="list", aliases=["show"], description="List all whitelisted users and bots.")
    async def whitelist_list(self, ctx: CustomContext) -> None:
        """Display all whitelisted members and bots."""
        wl_dict = self.bot.antinuke_mgr.get_whitelist(ctx.guild.id)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Whitelist**")
        container.add_separator(divider=True)

        if not wl_dict:
            container.add_text(f"{dot} No entities currently whitelisted.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        lines = []
        for uid, data in wl_dict.items():
            u = self.bot.get_user(uid)
            u_name = f"**{u.name}**" if u else f"<@{uid}>"

            if data.get("is_extra_owner"):
                lines.append(f"{dot} {u_name} `「{uid}」` **—** `[Extra Owner]`")
            elif data.get("is_full"):
                lines.append(f"{dot} {u_name} `「{uid}」` **—** `[Full Whitelist]`")
            else:
                scopes = ", ".join(data.get("scope", set()))
                lines.append(f"{dot} {u_name} `「{uid}」` **—** `[Scoped: {scopes}]`")

        container.add_text("\n".join(lines[:25]))
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load AntinukeWhitelistCog."""
    await bot.add_cog(AntinukeWhitelistCog(bot))
