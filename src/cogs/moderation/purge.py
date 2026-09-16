"""
Kyro Discord Bot - Purge / Message Cleaning Module
Robust message bulk deletion with rate-limit safety, slash deferral, and race-condition immunity.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional, Any
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import dispatch_mod_log
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.Purge")


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
    ) -> None:
        """Core bulk deletion engine with race-condition immunity and error handling."""
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

        check_filter = (lambda m: m.author.id == member.id) if member else None

        try:
            # Pass before=ctx.message for prefix commands to eliminate Error 10008 (Unknown Message race condition)
            if not ctx.interaction and ctx.message:
                deleted = await ctx.channel.purge(limit=count, check=check_filter, before=ctx.message)
                try:
                    await ctx.message.delete()
                except Exception:
                    pass
            else:
                deleted = await ctx.channel.purge(limit=count, check=check_filter)
        except discord.Forbidden:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Permission Denied**\n"
                    "> I do not have permission to delete messages in this channel.\n"
                    "> Please ensure I have `Manage Messages` and `Read Message History` permissions."
                )
            )
            await send_container_response(ctx, container)
            return
        except discord.HTTPException as e:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Purge Failed**\n"
                    f"> Discord API returned an error: `{e.text or e}`\n"
                    "> Note: Discord does not permit bulk-deleting messages older than 14 days."
                )
            )
            await send_container_response(ctx, container)
            return
        except Exception as e:
            logger.error(f"Unexpected error in purge: {e}", exc_info=e)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Purge Error**\n"
                    f"> An unexpected error occurred while deleting messages: `{e}`"
                )
            )
            await send_container_response(ctx, container)
            return

        # Build signature success container
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        badge = e_reg.get("icon_moderation", "")
        badge_str = f"{badge} " if badge else ""

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"{badge_str}**Messages Purged**\n"
                f"> Successfully cleared **{len(deleted)}** message(s)."
            )
        )
        container.add_separator(divider=True)

        info = f"{dot} **Deleted:** `{len(deleted)}` message(s)\n{dot} **Channel:** {ctx.channel.mention}"
        if member:
            info += f"\n{dot} **Target User:** {member.mention} (`{member.id}`)"
        info += f"\n{dot} **Moderator:** {ctx.author.mention}"
        container.add_text(info)

        if not ctx.interaction:
            container.add_separator(divider=True)
            container.add_text("-# This notice will automatically delete in 5 seconds.")

        res = await send_container_response(ctx, container)

        # Dispatch Mod-Log
        try:
            await dispatch_mod_log(
                self.bot,
                ctx.guild,
                "Message Purge",
                member or ctx.author,
                ctx.author,
                reason=f"Purged {len(deleted)} message(s) in #{ctx.channel.name}",
                extra=f"Count: {len(deleted)}" + (f" | Target: {member}" if member else ""),
            )
        except Exception as e:
            logger.debug(f"Purge mod log notice: {e}")

        # Auto-delete confirmation card in prefix mode after 5 seconds to keep channel spotless
        if not ctx.interaction and isinstance(res, dict) and "id" in res:
            msg_id = int(res["id"])
            channel_obj = ctx.channel

            async def _cleanup_confirmation() -> None:
                await asyncio.sleep(5.0)
                try:
                    target_msg = await channel_obj.fetch_message(msg_id)
                    await target_msg.delete()
                except Exception:
                    pass

            asyncio.create_task(_cleanup_confirmation())

    @commands.hybrid_command(
        name="purge",
        aliases=["prune", "clean"],
        description="Bulk delete messages in the current channel (1 to 100).",
    )
    @app_commands.describe(
        count="Number of messages to delete (1-100)",
        member="Optional member to filter messages by",
    )
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    @commands.guild_only()
    async def purge(
        self,
        ctx: CustomContext,
        count: int = 10,
        member: Optional[discord.Member] = None,
    ) -> None:
        """Bulk delete messages."""
        await self._execute_purge(ctx, count, member)

    @purge.error
    async def purge_error(self, ctx: CustomContext, error: commands.CommandError) -> None:
        """Intelligent fallback for inverted argument orders (e.g. ?purge @user 10)."""
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

        # If recovery was not possible, pass to global error handler
        await self.bot.on_command_error(ctx, error)


async def setup(bot: KyroBot) -> None:
    """Load the PurgeCog into KyroBot."""
    await bot.add_cog(PurgeCog(bot))
