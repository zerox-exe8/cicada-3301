"""
Kyro Discord Bot - Purge / Message Cleaning Module
Robust message bulk deletion with rate-limit safety, slash deferral, and race-condition immunity.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import TYPE_CHECKING, Optional, Any, Callable
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import dispatch_mod_log
from src.cogs.moderation._commands.purge_bot import execute_purge_bot
from src.cogs.moderation._commands.purge_human import execute_purge_human
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.Purge")


def can_execute_purge():
    """Bypass permission check for Bot Owners, Developers, Guild Owners, and Administrators."""
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            raise commands.NoPrivateMessage("Purge command can only be used in a server channel.")
        author_id = ctx.author.id
        bot = ctx.bot
        # 1. Bot Owners & Developers bypass
        if getattr(bot, "owner_id", None) and author_id == bot.owner_id:
            return True
        if getattr(bot, "owner_ids", None) and author_id in bot.owner_ids:
            return True
        if hasattr(bot, "perm_mgr") and bot.perm_mgr.is_developer_sync(author_id):
            return True
        if author_id in {1082437832087445604, 879986471866630155}:
            return True
        # 2. Server Owner & Administrators bypass
        if ctx.guild.owner_id == author_id:
            return True
        if isinstance(ctx.author, discord.Member) and ctx.author.guild_permissions.administrator:
            return True
        # 3. Channel Manage Messages permission
        if ctx.channel.permissions_for(ctx.author).manage_messages:
            return True
        raise commands.MissingPermissions(["manage_messages"])
    return commands.check(predicate)


class PurgeCog(commands.Cog):
    """Message bulk deletion and channel cleaning tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    async def _execute_purge(
        self,
        ctx: CustomContext,
        count: int,
        member: Optional[discord.Member] = None,
        filter_type: str = "all",
        check_func: Optional[Callable[[discord.Message], bool]] = None,
    ) -> None:
        """Core bulk deletion engine with history search for filtered purges, rate-limit safety, and minimal notices."""
        if count < 1 or count > 100:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Invalid Count**\n"
                    "> Message purge count must be between **1** and **100**."
                )
            )
            await send_container_response(ctx, container)
            return

        if not hasattr(ctx.channel, "purge"):
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Unsupported Channel**\n"
                    "> Purge command can only be executed in server text channels."
                )
            )
            await send_container_response(ctx, container)
            return

        # Defer interaction for slash commands to prevent 3-second timeout
        if ctx.interaction and not ctx.interaction.response.is_done():
            try:
                await ctx.defer(ephemeral=False)
            except Exception:
                pass

        effective_check: Optional[Callable[[discord.Message], bool]] = None
        if member:
            effective_check = lambda m: m.author.id == member.id
        elif check_func:
            effective_check = check_func

        deleted: list[discord.Message] = []
        try:
            # Delete trigger command message first so it doesn't pollute the channel
            if not ctx.interaction and ctx.message:
                try:
                    await ctx.message.delete()
                except Exception:
                    pass

            if effective_check:
                # When filtering (bot/human/member), scan history up to 500 messages to collect target count
                to_delete: list[discord.Message] = []
                async for msg in ctx.channel.history(limit=500):
                    if not ctx.interaction and ctx.message and msg.id == ctx.message.id:
                        continue
                    if effective_check(msg):
                        to_delete.append(msg)
                        if len(to_delete) >= count:
                            break

                if to_delete:
                    # Partition into young messages (<= 14 days, bulk deletable) and old (> 14 days, single delete)
                    cutoff = discord.utils.utcnow() - datetime.timedelta(days=14)
                    young_msgs = [m for m in to_delete if m.created_at > cutoff]
                    old_msgs = [m for m in to_delete if m.created_at <= cutoff]

                    if young_msgs:
                        if len(young_msgs) == 1:
                            try:
                                await young_msgs[0].delete()
                                deleted.append(young_msgs[0])
                            except Exception:
                                pass
                        else:
                            for i in range(0, len(young_msgs), 100):
                                batch = young_msgs[i : i + 100]
                                try:
                                    await ctx.channel.delete_messages(batch)
                                    deleted.extend(batch)
                                except Exception:
                                    for bm in batch:
                                        try:
                                            await bm.delete()
                                            deleted.append(bm)
                                        except Exception:
                                            pass

                    for om in old_msgs:
                        try:
                            await om.delete()
                            deleted.append(om)
                            await asyncio.sleep(0.3)
                        except Exception:
                            pass
            else:
                # No filter: direct bulk purge of recent messages
                raw_deleted = await ctx.channel.purge(limit=count)
                deleted = list(raw_deleted)

        except discord.Forbidden:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Permission Denied**\n"
                    "> I need `Manage Messages` and `Read Message History` permissions in this channel."
                )
            )
            try:
                await send_container_response(ctx, container)
            except Exception:
                await ctx.channel.send("I do not have permission to delete messages in this channel.")
            return
        except discord.HTTPException as e:
            logger.warning(f"Purge error: {e}")
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Purge Failed**\n> Discord API notice: `{e}`")
            try:
                await send_container_response(ctx, container)
            except Exception:
                pass
            return
        except Exception as e:
            logger.error(f"Unexpected error in purge: {e}", exc_info=e)
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Purge Error**\n> An unexpected error occurred: `{e}`")
            try:
                await send_container_response(ctx, container)
            except Exception:
                pass
            return

        # Ultra-clean, minimal Components V2 notification (zero redundant text)
        type_label = ""
        if filter_type == "bot":
            type_label = "Bot "
        elif filter_type == "human":
            type_label = "Human "
        elif member:
            type_label = f"{member.display_name}'s "

        container = KyroContainer(accent_color=None)
        if len(deleted) == 0:
            container.add_section(
                content=(
                    f"**No {type_label}Messages Found**\n"
                    f"> No eligible messages found to delete."
                )
            )
        else:
            container.add_section(
                content=(
                    f"**Purged {len(deleted)} {type_label}Message{'s' if len(deleted) != 1 else ''}**\n"
                    f"> Cleared `{len(deleted)}` message(s) in {ctx.channel.mention}."
                )
            )

        res = None
        try:
            res = await send_container_response(ctx, container)
        except Exception as e:
            logger.error(f"Failed to send purge confirmation container: {e}")
            try:
                res = await ctx.channel.send(f"Cleared `{len(deleted)}` message(s).")
            except Exception:
                res = None

        # Dispatch Mod-Log
        if len(deleted) > 0:
            action_name = "Message Purge"
            if filter_type == "bot":
                action_name = "Bot Message Purge"
            elif filter_type == "human":
                action_name = "Human Message Purge"

            try:
                scope_str = "All Messages"
                if filter_type == "bot":
                    scope_str = "Bots Only"
                elif filter_type == "human":
                    scope_str = "Humans Only"

                extra_details = f"Cleared {len(deleted)} message(s) • Filter: {scope_str}"
                await dispatch_mod_log(
                    self.bot,
                    ctx.guild,
                    action_name,
                    target=member,
                    moderator=ctx.author,
                    channel=ctx.channel,
                    reason=None,
                    extra=extra_details,
                )
            except Exception as e:
                logger.debug(f"Purge mod log notice: {e}")

        # Auto-delete confirmation card in prefix/no-prefix mode after 4 seconds ONLY if messages were cleared
        if not ctx.interaction and res and len(deleted) > 0:
            async def _cleanup_confirmation() -> None:
                await asyncio.sleep(4.0)
                try:
                    if isinstance(res, discord.Message):
                        await res.delete()
                    elif isinstance(res, dict) and "id" in res:
                        target_msg = await ctx.channel.fetch_message(int(res["id"]))
                        await target_msg.delete()
                except Exception:
                    pass

            asyncio.create_task(_cleanup_confirmation())

    @commands.hybrid_group(
        name="purge",
        aliases=["prune", "clean"],
        invoke_without_command=True,
        fallback="all",
        description="Bulk delete messages in the current channel (1 to 100).",
    )
    @app_commands.describe(
        count="Number of messages to delete (1-100)",
        member="Optional member to filter messages by",
    )
    @can_execute_purge()
    @commands.guild_only()
    async def purge(
        self,
        ctx: CustomContext,
        count: int = 10,
        member: Optional[discord.Member] = None,
    ) -> None:
        """Bulk delete messages (all messages, or filtered by user)."""
        if ctx.invoked_subcommand is not None:
            return
        await self._execute_purge(ctx, count, member=member, filter_type="all")

    @purge.command(
        name="bot",
        aliases=["bots"],
        description="Bulk delete messages sent by bot accounts (1 to 100).",
    )
    @app_commands.describe(count="Number of bot messages to delete (1-100)")
    @can_execute_purge()
    @commands.guild_only()
    async def purge_bot(
        self,
        ctx: CustomContext,
        count: int = 10,
    ) -> None:
        """Bulk delete only bot messages."""
        await execute_purge_bot(self, ctx, count=count)

    @purge.command(
        name="human",
        aliases=["humans", "user", "users"],
        description="Bulk delete messages sent by real humans/users (1 to 100).",
    )
    @app_commands.describe(count="Number of human messages to delete (1-100)")
    @can_execute_purge()
    @commands.guild_only()
    async def purge_human(
        self,
        ctx: CustomContext,
        count: int = 10,
    ) -> None:
        """Bulk delete only human/user messages."""
        await execute_purge_human(self, ctx, count=count)

    @purge.error
    async def purge_error(self, ctx: CustomContext, error: commands.CommandError) -> None:
        """Intelligent fallback for inverted argument orders and explicit error card rendering."""
        original = getattr(error, "original", error)
        if isinstance(original, (commands.BadArgument, commands.MemberNotFound)):
            if ctx.message and ctx.message.content:
                parts = ctx.message.content.split()[1:]
                if parts:
                    resolved_member: Optional[discord.Member] = None
                    resolved_count: int = 10
                    for part in parts:
                        clean = part.strip("<@!>")
                        if clean.isdigit() and len(clean) > 15:
                            resolved_member = ctx.guild.get_member(int(clean))
                        elif part.isdigit():
                            resolved_count = int(part)
                        else:
                            resolved_member = discord.utils.find(
                                lambda m: m.name.lower() == part.lower() or m.display_name.lower() == part.lower(),
                                ctx.guild.members,
                            )

                    if resolved_member:
                        await self._execute_purge(ctx, resolved_count, resolved_member)
                        return

        prefix_str = ctx.prefix or ""
        container = KyroContainer(accent_color=None)
        if isinstance(original, commands.MissingPermissions):
            missing = ", ".join(f"`{p}`" for p in original.missing_permissions)
            container.add_section(
                content=(
                    "**Permission Denied**\n"
                    f"> You need the following permissions to execute this command:\n> {missing}"
                )
            )
        elif isinstance(original, commands.BotMissingPermissions):
            missing = ", ".join(f"`{p}`" for p in original.missing_permissions)
            container.add_section(
                content=(
                    "**Bot Missing Permissions**\n"
                    f"> I need the following permissions in this channel to purge:\n> {missing}"
                )
            )
        elif isinstance(original, commands.NoPrivateMessage):
            container.add_section(
                content=(
                    "**Server Only**\n"
                    "> Purge command can only be used in a server channel."
                )
            )
        else:
            container.add_section(
                content=(
                    "**Purge Usage Error**\n"
                    f"> `{original}`\n\n"
                    f"> Usage:\n"
                    f"> • `{prefix_str}purge [count: 1-100] [@user]`\n"
                    f"> • `{prefix_str}purge bot [count: 1-100]`\n"
                    f"> • `{prefix_str}purge human [count: 1-100]`"
                )
            )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        try:
            await send_container_response(ctx, container, ephemeral=True)
        except Exception:
            try:
                await ctx.send(f"**Purge Error**: `{original}`")
            except Exception:
                pass


async def setup(bot: KyroBot) -> None:
    """Load the PurgeCog into KyroBot."""
    await bot.add_cog(PurgeCog(bot))
