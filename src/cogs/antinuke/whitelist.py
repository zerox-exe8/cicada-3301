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
    """Whitelist and Extra Owner management for Kyro Antinuke."""
    category: str = "Security"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    # ----------------- EXTRA OWNER COMMANDS (SERVER OWNER ONLY) -----------------

    @commands.hybrid_group(
        name="extraowner",
        aliases=["trustowner", "eo"],
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
        """Add an Extra Owner (Strictly Server Owner only)."""
        if ctx.author.id != ctx.guild.owner_id:
            await ctx.send_error("Only the **Server Owner** can assign Extra Owners.")
            return

        if user.id == ctx.guild.owner_id:
            await ctx.send_error("The Server Owner already possesses hardcoded master immunity.")
            return

        if user.bot:
            await ctx.send_error("Bots cannot be designated as Extra Owners. Use `,whitelist add <bot>` instead.")
            return

        await self.bot.antinuke_mgr.add_extra_owner(ctx.guild.id, user.id, ctx.author.id)

        dot = self.bot.custom_emojis.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Extra Owner Assigned**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **User:** **{user.name}** `「{user.id}」`\n"
            f"{dot} **Privilege:** Full Antinuke immunity and configuration access."
        )
        await send_container_response(ctx, container)

    @extraowner.command(name="remove", description="Revoke Extra Owner status from a user (Server Owner only).")
    @app_commands.describe(user="User to revoke Extra Owner from")
    async def extraowner_remove(self, ctx: CustomContext, user: discord.User) -> None:
        """Revoke Extra Owner status (Strictly Server Owner only)."""
        if ctx.author.id != ctx.guild.owner_id:
            await ctx.send_error("Only the **Server Owner** can revoke Extra Owners.")
            return

        if not self.bot.antinuke_mgr.is_extra_owner(ctx.guild.id, user.id):
            await ctx.send_error(f"**{user.name}** is not registered as an Extra Owner.")
            return

        await self.bot.antinuke_mgr.remove_extra_owner(ctx.guild.id, user.id)

        dot = self.bot.custom_emojis.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Extra Owner Revoked**")
        container.add_separator(divider=True)
        container.add_text(f"{dot} **User:** **{user.name}** `「{user.id}」` has been demoted.")
        await send_container_response(ctx, container)

    @extraowner.command(name="list", description="List all registered Extra Owners.")
    async def extraowner_list(self, ctx: CustomContext) -> None:
        """Display list of all registered Extra Owners."""
        owner_ids = self.bot.antinuke_mgr.get_extra_owners(ctx.guild.id)
        dot = self.bot.custom_emojis.get("heart_dot", "-")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Extra Owners Registry — {ctx.guild.name}**\n"
                f"> Total Extra Owners: `{len(owner_ids)}`"
            )
        )
        container.add_separator(divider=True)

        if not owner_ids:
            container.add_text(f"{dot} No Extra Owners configured. Use `,extraowner add <user>` to register.")
        else:
            lines = []
            for uid in owner_ids:
                u = self.bot.get_user(uid)
                u_str = f"**{u.name}**" if u else f"<@{uid}>"
                lines.append(f"{dot} {u_str} `「{uid}」`")
            container.add_text("\n".join(lines))

        await send_container_response(ctx, container)

    # ----------------- WHITELIST COMMANDS (OWNER / EXTRA OWNER) -----------------

    @commands.hybrid_group(
        name="whitelist",
        aliases=["wl"],
        description="Manage users or bots immune to antinuke triggers.",
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def whitelist(self, ctx: CustomContext) -> None:
        """View list of all whitelisted entities."""
        await ctx.invoke(self.bot.get_command("whitelist list"))

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
        # Check permissions: Server Owner or Extra Owner
        is_owner = ctx.author.id == ctx.guild.owner_id
        is_eo = self.bot.antinuke_mgr.is_extra_owner(ctx.guild.id, ctx.author.id)
        if not (is_owner or is_eo):
            await ctx.send_error("Only the **Server Owner** or **Extra Owners** can manage the whitelist.")
            return

        is_full = True
        clean_scope = ""
        if scope and scope.strip():
            # Validate modules
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

        dot = self.bot.custom_emojis.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Whitelist Updated**")
        container.add_separator(divider=True)

        tier_str = "Full Whitelist (All Triggers)" if is_full else f"Scoped Whitelist (`{clean_scope}`)"
        container.add_text(
            f"{dot} **Entity:** **{target.name}** `「{target.id}」`\n"
            f"{dot} **Access Level:** {tier_str}"
        )
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

        dot = self.bot.custom_emojis.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Whitelist Entry Removed**")
        container.add_separator(divider=True)
        container.add_text(f"{dot} **Target:** **{target.name}** `「{target.id}」` has been removed from whitelist.")
        await send_container_response(ctx, container)

    @whitelist.command(name="list", description="List all whitelisted users and bots.")
    async def whitelist_list(self, ctx: CustomContext) -> None:
        """Display all whitelisted members and bots with their permissions."""
        wl_dict = self.bot.antinuke_mgr.get_whitelist(ctx.guild.id)
        dot = self.bot.custom_emojis.get("heart_dot", "-")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Antinuke Whitelist Registry — {ctx.guild.name}**\n"
                f"> Total Whitelisted Entries: `{len(wl_dict)}`"
            )
        )
        container.add_separator(divider=True)

        if not wl_dict:
            container.add_text(f"{dot} No members or bots are currently whitelisted.")
            await send_container_response(ctx, container)
            return

        lines = []
        for uid, data in wl_dict.items():
            u = self.bot.get_user(uid)
            u_name = f"**{u.name}**" if u else f"<@{uid}>"

            if data.get("is_extra_owner"):
                lines.append(f"{dot} {u_name} `「{uid}」` — `Extra Owner`")
            elif data.get("is_full"):
                lines.append(f"{dot} {u_name} `「{uid}」` — `Full Whitelist`")
            else:
                scopes = ", ".join(data.get("scope", set()))
                lines.append(f"{dot} {u_name} `「{uid}」` — Scoped: `{scopes}`")

        container.add_text("\n".join(lines[:25]))
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load AntinukeWhitelistCog."""
    await bot.add_cog(AntinukeWhitelistCog(bot))
