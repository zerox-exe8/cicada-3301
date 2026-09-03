"""
Kyro Discord Bot - Global Blacklist Management Module
Restricts abusive users or rogue guilds across the entire Kyro network.
Designed identically to No-Prefix protocol with precision Components V2 cards.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Developer.Blacklist")


class BlacklistCog(commands.Cog, name="Developer-Blacklist"):
    """Global access restriction and blacklist enforcement."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.group(
        name="blacklist",
        aliases=["bl"],
        invoke_without_command=True,
        description="Manage Global Blacklist restrictions for users or guilds.",
    )
    @is_developer()
    async def blacklist(self, ctx: CustomContext) -> None:
        """Overview of Blacklist management commands."""
        total_blocked = len(self.bot.blacklist_mgr._blacklisted_users) + len(self.bot.blacklist_mgr._blacklisted_guilds)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Blacklist Protocol**\n"
                f"> **add** • `?bl add <@user | id> [reason]`\n"
                f"> **remove** • `?bl remove <@user | id>`\n"
                f"> **list** • `?bl list`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Active Restricted: {total_blocked} entities")
        await send_container_response(ctx, container)

    @blacklist.command(name="add")
    @is_developer()
    async def bl_add(self, ctx: CustomContext, target: Optional[str] = None, *, reason: Optional[str] = None) -> None:
        """Globally ban a user or guild from using the bot."""
        resolved_id: int | None = None
        target_name: str = ""
        target_type: str = "user"
        actual_reason = reason.strip() if reason else "Violation of bot usage terms"

        # 1. Check if user replied to a message
        if not target and ctx.message.reference and ctx.message.reference.message_id:
            try:
                ref_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                resolved_id = ref_msg.author.id
                target_name = ref_msg.author.name
            except Exception:
                pass

        # 2. Parse target parameter if provided
        if not resolved_id and target:
            clean = target.strip("<@!#&> ")
            if clean.isdigit():
                resolved_id = int(clean)
                guild_obj = self.bot.get_guild(resolved_id)
                user_obj = self.bot.get_user(resolved_id)
                if guild_obj:
                    target_name = guild_obj.name
                    target_type = "guild"
                elif user_obj:
                    target_name = user_obj.name
                    target_type = "user"
                else:
                    target_name = f"Entity {resolved_id}"
            else:
                try:
                    user_obj = await commands.UserConverter().convert(ctx, target)
                    resolved_id = user_obj.id
                    target_name = user_obj.name
                    target_type = "user"
                except Exception:
                    pass

        if not resolved_id:
            container = KyroContainer(accent_color=None)
            container.add_text(
                "**Error:** Could not resolve target. Provide a mention, user/guild ID, or reply to a message."
            )
            await send_container_response(ctx, container)
            return

        # 3. Security Guard: Prevent blacklisting Bot Owner or Developers
        if await self.bot.perm_mgr.is_developer(resolved_id):
            container = KyroContainer(accent_color=None)
            container.add_text("**Security Violation:** Root administrators and developers cannot be blacklisted.")
            await send_container_response(ctx, container)
            return

        # 4. Check if already blacklisted
        if (target_type == "user" and self.bot.blacklist_mgr.is_user_blacklisted(resolved_id)) or \
           (target_type == "guild" and self.bot.blacklist_mgr.is_guild_blacklisted(resolved_id)):
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Notice:** `{target_name}` is already globally restricted.")
            await send_container_response(ctx, container)
            return

        # 5. Enforce Blacklist via Manager (updates memory cache and PostgreSQL)
        try:
            await self.bot.blacklist_mgr.add_blacklist(
                target_id=resolved_id,
                target_type=target_type,
                reason=actual_reason,
                added_by=ctx.author.id,
            )
        except Exception as e:
            logger.error(f"Failed to persist blacklist: {e}")

        # If it's a guild, leave it immediately
        if target_type == "guild":
            guild_obj = self.bot.get_guild(resolved_id)
            if guild_obj:
                try:
                    await guild_obj.leave()
                except Exception:
                    pass

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Entity Blacklisted**\n"
                f"> **Target:** `{target_name}` (`{resolved_id}`)\n"
                f"> **Scope:** `Global {target_type.capitalize()} Restriction`\n"
                f"> **Reason:** `{actual_reason}`\n"
                f"> **Enforced By:** `{ctx.author.name}`"
            )
        )
        await send_container_response(ctx, container)

    @blacklist.command(name="remove", aliases=["rm", "del", "unbl", "unblacklist"])
    @is_developer()
    async def bl_remove(self, ctx: CustomContext, *, target: str) -> None:
        """Remove a user or guild from global blacklist."""
        clean = target.strip("<@!#&> ")
        resolved_id: int | None = None
        target_name: str = ""

        if clean.isdigit():
            resolved_id = int(clean)
            user_obj = self.bot.get_user(resolved_id)
            guild_obj = self.bot.get_guild(resolved_id)
            target_name = user_obj.name if user_obj else (guild_obj.name if guild_obj else f"Entity {resolved_id}")
        else:
            try:
                user_obj = await commands.UserConverter().convert(ctx, target)
                resolved_id = user_obj.id
                target_name = user_obj.name
            except Exception:
                pass

        if not resolved_id:
            container = KyroContainer(accent_color=None)
            container.add_text("**Error:** Could not resolve target ID. Provide a valid mention or ID.")
            await send_container_response(ctx, container)
            return

        if not self.bot.blacklist_mgr.is_user_blacklisted(resolved_id) and \
           not self.bot.blacklist_mgr.is_guild_blacklisted(resolved_id):
            container = KyroContainer(accent_color=None)
            container.add_text(f"**Notice:** `{target_name}` is not currently restricted.")
            await send_container_response(ctx, container)
            return

        # Remove from Manager
        try:
            await self.bot.blacklist_mgr.remove_blacklist(resolved_id)
        except Exception as e:
            logger.error(f"Failed to delete blacklist: {e}")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Entity Unblacklisted**\n"
                f"> **Target:** `{target_name}` (`{resolved_id}`)\n"
                f"> **Standing:** `Restoration Approved • Access Restored`"
            )
        )
        await send_container_response(ctx, container)

    @blacklist.command(name="list", aliases=["ls", "show"])
    @is_developer()
    async def bl_list(self, ctx: CustomContext) -> None:
        """Display list of all globally restricted users and servers."""
        users_map = self.bot.blacklist_mgr._blacklisted_users
        guilds_map = self.bot.blacklist_mgr._blacklisted_guilds

        if not users_map and not guilds_map:
            container = KyroContainer(accent_color=None)
            container.add_text("**Blacklist Directory:** `Empty` (No entities restricted)")
            await send_container_response(ctx, container)
            return

        entries = []
        for uid, rsn in list(users_map.items())[:10]:
            user_obj = self.bot.get_user(uid)
            uname = f"`{user_obj.name}`" if user_obj else f"`ID: {uid}`"
            entries.append(f"> User {uname} • `{rsn}`")

        for gid, rsn in list(guilds_map.items())[:5]:
            guild_obj = self.bot.get_guild(gid)
            gname = f"`{guild_obj.name}`" if guild_obj else f"`Guild: {gid}`"
            entries.append(f"> Server {gname} • `{rsn}`")

        total = len(users_map) + len(guilds_map)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Blacklist Directory**\n"
                + ("\n".join(entries) if entries else "> No entries found")
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Total Restricted: {total} entities")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(BlacklistCog(bot))
