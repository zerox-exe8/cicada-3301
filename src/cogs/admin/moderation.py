"""
Kyro Discord Bot - Comprehensive Moderation Engine
Provides full server moderation suite: ban, unban, kick, timeout, unmute, purge,
channel lock/unlock, slowmode, persistent warnings, and audit logging.
Uses Discord Components V2 Container Cards with sleek typography and role hierarchy safeguards.
"""

from __future__ import annotations

import datetime
import logging
import re
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation")


def parse_duration(duration_str: str) -> Optional[datetime.timedelta]:
    """Parse duration string like '10s', '15m', '2h', '7d' into timedelta."""
    match = re.match(r"^(\d+)([smhd])$", duration_str.strip().lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    if unit == "s":
        return datetime.timedelta(seconds=value)
    elif unit == "m":
        return datetime.timedelta(minutes=value)
    elif unit == "h":
        return datetime.timedelta(hours=value)
    elif unit == "d":
        return datetime.timedelta(days=value)
    return None


class Moderation(commands.Cog):
    """Server moderation and administrative tools."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    def _check_hierarchy(self, ctx: CustomContext, target: discord.Member) -> tuple[bool, str | None]:
        """Verify role hierarchy rules between author, bot, and target."""
        if target.id == ctx.author.id:
            return False, "You cannot execute moderation actions on yourself."
        if self.bot.user and target.id == self.bot.user.id:
            return False, "I cannot execute moderation actions on myself."
        if target.id == ctx.guild.owner_id:
            return False, "You cannot moderate the server owner."

        # Check author hierarchy (server owner bypasses)
        if ctx.author.id != ctx.guild.owner_id and target.top_role >= ctx.author.top_role:
            return False, "You cannot moderate this member because their highest role is equal to or higher than yours."

        # Check bot hierarchy
        if target.top_role >= ctx.guild.me.top_role:
            return False, "I cannot moderate this member because their highest role is equal to or higher than mine."

        return True, None

    async def _dispatch_mod_log(
        self,
        guild: discord.Guild,
        action: str,
        target: discord.User | discord.Member,
        moderator: discord.User | discord.Member,
        reason: str,
        extra: Optional[str] = None,
    ) -> None:
        """Post a sleek audit log card to the configured mod-log channel if available."""
        log_channel = self.bot.log_mgr.get_log_channel(guild, "mod")
        if not log_channel:
            return

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        badge = e_reg.get("icon_moderation", "")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{badge} Moderation Action: {action}**\n"
                f"> Target: **{target}** (`{target.id}`)"
            )
        )
        container.add_separator(divider=True)

        details = (
            f"{dot} **Moderator:** {moderator.mention} (`{moderator.id}`)\n"
            f"{dot} **Target:** {target.mention} (`{target.id}`)\n"
            f"{dot} **Reason:** `{reason}`"
        )
        if extra:
            details += f"\n{dot} **Details:** `{extra}`"

        container.add_text(details)
        container.add_separator(divider=True)
        container.add_text(f"-# Timestamp: <t:{int(discord.utils.utcnow().timestamp())}:F>")

        try:
            await send_container_response(log_channel, container)
        except Exception as e:
            logger.warning(f"Failed to dispatch mod log in {guild.name}: {e}")

    # ==========================================
    # Ban & Unban Commands
    # ==========================================

    @commands.hybrid_command(
        name="ban",
        description="Ban a member from the server.",
    )
    @app_commands.describe(member="Member to ban", reason="Reason for the ban")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self, ctx: CustomContext, member: discord.Member, *, reason: str = "No reason provided") -> None:
        """Ban a member from the server."""
        allowed, err_msg = self._check_hierarchy(ctx, member)
        if not allowed:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err_msg}")
            await send_container_response(ctx, container)
            return

        # Attempt DM notification
        try:
            dm_container = KyroContainer(accent_color=None)
            dm_container.add_section(
                content=(
                    f"**You were banned from {ctx.guild.name}**\n"
                    f"> Moderator: **{ctx.author}**\n"
                    f"> Reason: `{reason}`"
                )
            )
            await send_container_response(member, dm_container)
        except Exception:
            pass

        await ctx.guild.ban(member, reason=f"{ctx.author} ({ctx.author.id}): {reason}", delete_message_days=0)
        await self._dispatch_mod_log(ctx.guild, "Member Ban", member, ctx.author, reason)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Member Banned**\n"
                f"> **{member}** has been banned from the server."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** {member.mention} (`{member.id}`)\n"
            f"{dot} **Moderator:** {ctx.author.mention}\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="unban",
        description="Unban a user by their user ID or tag.",
    )
    @app_commands.describe(user="User ID or mention to unban", reason="Reason for unbanning")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(self, ctx: CustomContext, user: discord.User, *, reason: str = "No reason provided") -> None:
        """Unban a previously banned user."""
        try:
            await ctx.guild.unban(user, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        except discord.NotFound:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Not Found**\n> This user is not currently banned in this server.")
            await send_container_response(ctx, container)
            return

        await self._dispatch_mod_log(ctx.guild, "Member Unban", user, ctx.author, reason)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Member Unbanned**\n"
                f"> **{user}** has been unbanned from the server."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** {user.mention} (`{user.id}`)\n"
            f"{dot} **Moderator:** {ctx.author.mention}\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

    # ==========================================
    # Kick Command
    # ==========================================

    @commands.hybrid_command(
        name="kick",
        description="Kick a member from the server.",
    )
    @app_commands.describe(member="Member to kick", reason="Reason for kicking")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx: CustomContext, member: discord.Member, *, reason: str = "No reason provided") -> None:
        """Kick a member from the server."""
        allowed, err_msg = self._check_hierarchy(ctx, member)
        if not allowed:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err_msg}")
            await send_container_response(ctx, container)
            return

        try:
            dm_container = KyroContainer(accent_color=None)
            dm_container.add_section(
                content=(
                    f"**You were kicked from {ctx.guild.name}**\n"
                    f"> Moderator: **{ctx.author}**\n"
                    f"> Reason: `{reason}`"
                )
            )
            await send_container_response(member, dm_container)
        except Exception:
            pass

        await member.kick(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await self._dispatch_mod_log(ctx.guild, "Member Kick", member, ctx.author, reason)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Member Kicked**\n"
                f"> **{member}** has been kicked from the server."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** {member.mention} (`{member.id}`)\n"
            f"{dot} **Moderator:** {ctx.author.mention}\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

    # ==========================================
    # Timeout / Mute Commands
    # ==========================================

    @commands.hybrid_command(
        name="timeout",
        aliases=["mute"],
        description="Timeout a member for a specified duration (e.g., 10m, 1h, 1d).",
    )
    @app_commands.describe(
        member="Member to timeout",
        duration="Duration (e.g. 10m, 1h, 1d, max 28d)",
        reason="Reason for timeout",
    )
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def timeout(
        self,
        ctx: CustomContext,
        member: discord.Member,
        duration: str = "10m",
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Timeout/mute a member."""
        allowed, err_msg = self._check_hierarchy(ctx, member)
        if not allowed:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err_msg}")
            await send_container_response(ctx, container)
            return

        delta = parse_duration(duration)
        if not delta:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Invalid Duration Format**\n"
                    "> Please use format: `10s`, `15m`, `2h`, or `7d` (Max: `28d`)."
                )
            )
            await send_container_response(ctx, container)
            return

        if delta > datetime.timedelta(days=28):
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Duration Exceeded**\n"
                    "> Discord maximum timeout duration is 28 days."
                )
            )
            await send_container_response(ctx, container)
            return

        until = discord.utils.utcnow() + delta
        await member.timeout(until, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await self._dispatch_mod_log(ctx.guild, "Member Timeout", member, ctx.author, reason, extra=f"Duration: {duration}")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Member Timed Out**\n"
                f"> **{member}** has been timed out."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** {member.mention} (`{member.id}`)\n"
            f"{dot} **Duration:** `{duration}` (Expires: <t:{int(until.timestamp())}:R>)\n"
            f"{dot} **Moderator:** {ctx.author.mention}\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="unmute",
        aliases=["untimeout"],
        description="Remove timeout from a member.",
    )
    @app_commands.describe(member="Member to remove timeout from", reason="Reason for removing timeout")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    @commands.guild_only()
    async def unmute(
        self,
        ctx: CustomContext,
        member: discord.Member,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Remove timeout/unmute a member."""
        allowed, err_msg = self._check_hierarchy(ctx, member)
        if not allowed:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**Hierarchy Error**\n> {err_msg}")
            await send_container_response(ctx, container)
            return

        await member.timeout(None, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        await self._dispatch_mod_log(ctx.guild, "Timeout Removed", member, ctx.author, reason)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Timeout Removed**\n"
                f"> **{member}** is no longer timed out."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** {member.mention} (`{member.id}`)\n"
            f"{dot} **Moderator:** {ctx.author.mention}\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

    # ==========================================
    # Purge / Clear Messages Command
    # ==========================================

    @commands.hybrid_command(
        name="purge",
        aliases=["prune"],
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
        if count < 1 or count > 100:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Invalid Count**\n"
                    "> Message purge count must be between 1 and 100."
                )
            )
            await send_container_response(ctx, container)
            return

        # For prefix command, delete invoking message first if possible
        if not ctx.interaction and ctx.message:
            try:
                await ctx.message.delete()
            except Exception:
                pass

        check = (lambda m: m.author.id == member.id) if member else None
        deleted = await ctx.channel.purge(limit=count, check=check)

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Messages Purged**\n"
                f"> Successfully cleared **{len(deleted)}** message(s)."
            )
        )
        container.add_separator(divider=True)
        info = f"{dot} **Deleted:** `{len(deleted)}` message(s)\n{dot} **Channel:** {ctx.channel.mention}"
        if member:
            info += f"\n{dot} **Filter:** Messages from {member.mention}"
        container.add_text(info)

        msg = await send_container_response(ctx, container)
        # Auto-delete confirmation after 5 seconds to keep channel clean
        if msg and isinstance(msg, discord.Message):
            try:
                await msg.delete(delay=5.0)
            except Exception:
                pass

    # ==========================================
    # Channel Lock & Unlock
    # ==========================================

    @commands.hybrid_command(
        name="lock",
        description="Lock a channel to prevent regular members from sending messages.",
    )
    @app_commands.describe(channel="Channel to lock (defaults to current)", reason="Reason for locking")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def lock(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Lock a channel."""
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Error**\n> Lock command only applies to text channels.")
            await send_container_response(ctx, container)
            return

        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await target_channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: {reason}")

        await self._dispatch_mod_log(ctx.guild, "Channel Lock", ctx.author, ctx.author, reason, extra=f"Channel: {target_channel.mention}")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Channel Locked**\n"
                f"> {target_channel.mention} has been locked."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Channel:** {target_channel.mention}\n"
            f"{dot} **Moderator:** {ctx.author.mention}\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

    @commands.hybrid_command(
        name="unlock",
        description="Unlock a channel to allow members to send messages.",
    )
    @app_commands.describe(channel="Channel to unlock (defaults to current)", reason="Reason for unlocking")
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def unlock(
        self,
        ctx: CustomContext,
        channel: Optional[discord.TextChannel] = None,
        *,
        reason: str = "No reason provided",
    ) -> None:
        """Unlock a channel."""
        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Error**\n> Unlock command only applies to text channels.")
            await send_container_response(ctx, container)
            return

        overwrite = target_channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await target_channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author}: {reason}")

        await self._dispatch_mod_log(ctx.guild, "Channel Unlock", ctx.author, ctx.author, reason, extra=f"Channel: {target_channel.mention}")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Channel Unlocked**\n"
                f"> {target_channel.mention} has been unlocked."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Channel:** {target_channel.mention}\n"
            f"{dot} **Moderator:** {ctx.author.mention}\n"
            f"{dot} **Reason:** `{reason}`"
        )
        await send_container_response(ctx, container)

    # ==========================================
    # Slowmode Command
    # ==========================================

    @commands.hybrid_command(
        name="slowmode",
        description="Set slowmode delay for a channel (0 to disable, max 21600s).",
    )
    @app_commands.describe(
        seconds="Slowmode delay in seconds (0 to 21600)",
        channel="Channel to adjust (defaults to current)",
    )
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    @commands.guild_only()
    async def slowmode(
        self,
        ctx: CustomContext,
        seconds: int = 0,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        """Set channel slowmode delay."""
        if seconds < 0 or seconds > 21600:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Invalid Seconds**\n"
                    "> Slowmode seconds must be between `0` and `21600` (6 hours)."
                )
            )
            await send_container_response(ctx, container)
            return

        target_channel = channel or ctx.channel
        if not isinstance(target_channel, discord.TextChannel):
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Error**\n> Slowmode only applies to text channels.")
            await send_container_response(ctx, container)
            return

        await target_channel.edit(slowmode_delay=seconds, reason=f"Slowmode set by {ctx.author}")

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        container = KyroContainer(accent_color=None)
        if seconds == 0:
            container.add_section(
                content=(
                    f"**Slowmode Disabled**\n"
                    f"> Slowmode has been deactivated for {target_channel.mention}."
                )
            )
        else:
            container.add_section(
                content=(
                    f"**Slowmode Updated**\n"
                    f"> Slowmode set to **{seconds}s** for {target_channel.mention}."
                )
            )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Channel:** {target_channel.mention}\n"
            f"{dot} **Delay:** `{seconds} seconds`\n"
            f"{dot} **Moderator:** {ctx.author.mention}"
        )
        await send_container_response(ctx, container)

    # ==========================================
    # Warnings System
    # ==========================================

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
        allowed, err_msg = self._check_hierarchy(ctx, member)
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

        await self._dispatch_mod_log(ctx.guild, "Member Warning", member, ctx.author, reason, extra=f"Total Warns: {total_warns}")

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

    # ==========================================
    # Mod Log Configuration
    # ==========================================

    @commands.hybrid_command(
        name="modlog",
        description="Set or disable the moderation audit log channel.",
    )
    @app_commands.describe(channel="Channel for moderation logs (leave empty to view current)")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def modlog(self, ctx: CustomContext, channel: Optional[discord.TextChannel] = None) -> None:
        """Set or view the moderation audit log channel."""
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")

        if channel is None:
            current = self.bot.log_mgr.get_log_channel(ctx.guild, "mod")
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Moderation Log Configuration**\n"
                    f"> Current mod log channel: {current.mention if current else '`None (Disabled)`'}"
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"{dot} Use `?modlog #channel` to configure the moderation audit log.")
            await send_container_response(ctx, container)
            return

        await self.bot.log_mgr.set_log_channel(ctx.guild.id, "mod", channel.id)

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Moderation Log Updated**\n"
                f"> Moderation audit logs will now be dispatched to {channel.mention}."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Configured Channel:** {channel.mention}\n"
            f"{dot} **Configured By:** {ctx.author.mention}"
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load the Moderation Cog into KyroBot."""
    await bot.add_cog(Moderation(bot))
