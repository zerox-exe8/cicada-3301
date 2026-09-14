"""
Kyro Discord Bot - Warning System Moderation Module
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import check_hierarchy, dispatch_mod_log
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class WarnCog(commands.Cog):
    """Server member warning system."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="warn",
        description="Issue an official warning to a server member.",
    )
    @app_commands.describe(member="Member to warn", reason="Reason for warning")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def warn(
        self,
        ctx: CustomContext,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Warn a member."""
        allowed, err_msg = check_hierarchy(self.bot, ctx, member)
        if not allowed:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err_msg}")
            await send_container_response(ctx, container)
            return

        await self.bot.db.execute(
            """
            INSERT INTO guild_warns (guild_id, user_id, moderator_id, reason)
            VALUES (?, ?, ?, ?);
            """,
            ctx.guild.id,
            member.id,
            ctx.author.id,
            reason,
        )

        # Count total warns
        count_row = await self.bot.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM guild_warns WHERE guild_id = ? AND user_id = ?;",
            ctx.guild.id,
            member.id,
        )
        total_warns = count_row["cnt"] if count_row else 1

        # Attempt DM notification
        try:
            dm_container = KyroContainer(accent_color=None)
            dm_container.add_section(
                content=(
                    f"**You received a warning in {ctx.guild.name}**\n"
                    f"> Moderator: **{ctx.author}**\n"
                    f"> Reason: `{reason}`\n"
                    f"> Total Warnings: `{total_warns}`"
                )
            )
            await send_container_response(member, dm_container)
        except Exception:
            pass

        await dispatch_mod_log(self.bot, ctx.guild, "Member Warning", member, ctx.author, reason, extra=f"Total Warns: {total_warns}")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Warning Issued**\n"
                f"> **{member}** has been formally warned."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** {member.mention} (`{member.id}`)\n"
            f"{dot} **Total Warnings:** `{total_warns}`\n"
            f"{dot} **Moderator:** {ctx.author.mention}\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="warnings",
        aliases=["warns"],
        description="View all recorded warnings for a member.",
    )
    @app_commands.describe(member="Member whose warnings to inspect")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def warnings(self, ctx: CustomContext, member: discord.Member) -> None:
        """View warnings of a member."""
        records = await self.bot.db.fetch_all(
            """
            SELECT id, moderator_id, reason, created_at
            FROM guild_warns
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at DESC
            LIMIT 10;
            """,
            ctx.guild.id,
            member.id,
        )

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)

        if not records:
            container.add_section(
                content=(
                    f"**Clean Record**\n"
                    f"> **{member}** has no recorded warnings in this server."
                )
            )
            await send_container_response(ctx, container)
            return

        container.add_section(
            content=(
                f"**Member Warnings**\n"
                f"> Showing last {len(records)} warning(s) for **{member}** (`{member.id}`)."
            )
        )
        container.add_separator(divider=True)

        warn_lines = []
        for r in records:
            w_id = r["id"]
            mod_id = r["moderator_id"]
            reason = r["reason"]
            ts = r.get("created_at")
            ts_str = f"<t:{int(ts.timestamp())}:d>" if isinstance(ts, datetime.datetime) else "N/A"
            warn_lines.append(f"{dot} **#{w_id}** by <@{mod_id}> ({ts_str}): `{reason}`")

        container.add_text("\n".join(warn_lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Use `?delwarn <id>` to remove a specific warning.")
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="delwarn",
        aliases=["unwarn", "removewarn"],
        description="Delete a warning record by its ID.",
    )
    @app_commands.describe(warn_id="The ID of the warning to delete")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def delwarn(self, ctx: CustomContext, warn_id: int) -> None:
        """Delete a warning by ID."""
        row = await self.bot.db.fetch_one(
            "SELECT id, user_id FROM guild_warns WHERE id = ? AND guild_id = ?;",
            warn_id,
            ctx.guild.id,
        )
        if not row:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Warning Not Found**\n"
                    f"> No warning with ID `#{warn_id}` exists in this server."
                )
            )
            await send_container_response(ctx, container)
            return

        await self.bot.db.execute(
            "DELETE FROM guild_warns WHERE id = ? AND guild_id = ?;",
            warn_id,
            ctx.guild.id,
        )

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Warning Deleted**\n"
                f"> Warning `#{warn_id}` for <@{row['user_id']}> has been deleted."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Warning ID:** `#{warn_id}`\n"
            f"{dot} **Moderator:** {ctx.author.mention}"
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load the WarnCog into KyroBot."""
    await bot.add_cog(WarnCog(bot))
