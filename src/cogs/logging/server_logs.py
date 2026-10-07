from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.ServerLogs")

# Ghost ping cache: message_id -> (mentions_str, channel_id, author_str, timestamp)
_ghost_cache: dict[int, tuple[str, int, str, float]] = {}
_GHOST_WINDOW = 30  # seconds — message deleted within this time = ghost ping


def _truncate(text: str, limit: int = 300) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 3] + "..."


class ServerLogsCog(commands.Cog):
    """Unified server audit logging — all server events in clean minimal cards."""

    category: str = "Logging"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    async def _send(self, guild: discord.Guild, log_type: str, title: str, lines: list[str]) -> None:
        if not guild or not lines:
            return
        try:
            channel = self.bot.log_mgr.get_log_channel(guild, log_type)
        except Exception:
            channel = None
        if channel is None:
            return

        dot = getattr(self.bot, "custom_emojis", {}).get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"**{title}**")
        container.add_separator(divider=True)
        body = "\n".join(
            f"> {dot} {ln}" if not ln.startswith("> ") else ln
            for ln in lines
        )
        container.add_text(body)
        container.add_separator(divider=True)
        container.add_text(f"-# <t:{int(discord.utils.utcnow().timestamp())}:f>")

        try:
            await send_container_response(channel, container)
        except Exception as e:
            logger.debug(f"Log dispatch failed ({log_type}/{title}): {e}")

    # ─────────────── MESSAGE ───────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Cache messages with mentions for ghost ping detection."""
        if not message.guild or message.author.bot:
            return
        mentions = [m for m in message.mentions if not m.bot and m.id != message.author.id]
        if mentions:
            mention_str = ", ".join(m.display_name for m in mentions)
            _ghost_cache[message.id] = (
                mention_str,
                message.channel.id,
                f"**{message.author.display_name}** `{message.author.id}`",
                time.monotonic(),
            )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return

        # Ghost ping check
        cached = _ghost_cache.pop(message.id, None)
        if cached:
            mention_str, ch_id, author_str, sent_at = cached
            elapsed = time.monotonic() - sent_at
            if elapsed <= _GHOST_WINDOW:
                await self._send(
                    message.guild, "message", "Ghost Ping Detected",
                    [
                        f"**By:** {author_str}",
                        f"**Pinged:** {mention_str}",
                        f"**Channel:** <#{ch_id}>",
                        f"**Deleted after:** `{elapsed:.1f}s`",
                    ],
                )
                return  # already logged as ghost ping, skip normal delete log

        content = _truncate(message.content or "*No text*")
        await self._send(
            message.guild, "message", "Message Deleted",
            [
                f"**By:** **{message.author.display_name}** `{message.author.id}`",
                f"**Channel:** {message.channel.mention}",
                f"**Content:** {content}",
            ],
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not after.guild or after.author.bot:
            return
        if (before.content or "") == (after.content or ""):
            return
        await self._send(
            after.guild, "message", "Message Edited",
            [
                f"**By:** **{after.author.display_name}** `{after.author.id}`",
                f"**Channel:** {after.channel.mention} • [Jump]({after.jump_url})",
                f"**Before:** {_truncate(before.content or '')}",
                f"**After:** {_truncate(after.content or '')}",
            ],
        )

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        if not messages:
            return
        guild = messages[0].guild
        if not guild:
            return
        ch = messages[0].channel
        await self._send(
            guild, "message", "Bulk Messages Deleted",
            [
                f"**Count:** `{len(messages)}`",
                f"**Channel:** {ch.mention if hasattr(ch, 'mention') else f'`{ch}`'}",
            ],
        )

    # ─────────────── MEMBER ───────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            await self._send(
                member.guild, "member", "Bot Added",
                [f"**Bot:** **{member}** `{member.id}`"],
            )
            return
        await self._send(
            member.guild, "member", "Member Joined",
            [
                f"**User:** **{member}** `{member.id}`",
                f"**Account Age:** <t:{int(member.created_at.timestamp())}:R>",
            ],
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self._send(
            member.guild, "member", "Member Left",
            [f"**User:** **{member}** `{member.id}`"],
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        await self._send(
            guild, "member", "Member Banned",
            [f"**User:** **{user}** `{user.id}`"],
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        await self._send(
            guild, "member", "Member Unbanned",
            [f"**User:** **{user}** `{user.id}`"],
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        lines: list[str] = []
        if before.nick != after.nick:
            lines.append(f"**Nickname:** `{before.nick or '—'}` → `{after.nick or '—'}`")
        added = [r.mention for r in after.roles if r not in before.roles]
        removed = [r.mention for r in before.roles if r not in after.roles]
        if added:
            lines.append(f"**Roles Added:** {', '.join(added)}")
        if removed:
            lines.append(f"**Roles Removed:** {', '.join(removed)}")
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until:
                lines.append(f"**Timed Out Until:** <t:{int(after.timed_out_until.timestamp())}:f>")
            else:
                lines.append("**Timeout Removed**")
        if not lines:
            return
        lines.insert(0, f"**User:** **{after}** `{after.id}`")
        await self._send(after.guild, "member", "Member Updated", lines)

    # ─────────────── SERVER ───────────────

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self._send(
            channel.guild, "server", "Channel Created",
            [f"**Channel:** {channel.mention} `#{channel.name}`"],
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self._send(
            channel.guild, "server", "Channel Deleted",
            [f"**Channel:** `#{channel.name}` `{channel.id}`"],
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        lines: list[str] = []
        if before.name != after.name:
            lines.append(f"**Name:** `{before.name}` → `{after.name}`")
        # Permission changes (broad check)
        if hasattr(before, "overwrites") and before.overwrites != after.overwrites:
            lines.append("**Permissions changed**")
        if not lines:
            return
        lines.insert(0, f"**Channel:** {after.mention}")
        await self._send(after.guild, "server", "Channel Updated", lines)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self._send(
            role.guild, "server", "Role Created",
            [f"**Role:** {role.mention} `{role.id}`"],
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self._send(
            role.guild, "server", "Role Deleted",
            [f"**Role:** `@{role.name}` `{role.id}`"],
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        lines: list[str] = []
        if before.name != after.name:
            lines.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.permissions != after.permissions:
            lines.append("**Permissions changed**")
        if before.color != after.color:
            lines.append(f"**Color:** `{before.color}` → `{after.color}`")
        if not lines:
            return
        lines.insert(0, f"**Role:** {after.mention}")
        await self._send(after.guild, "server", "Role Updated", lines)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        lines: list[str] = []
        if before.name != after.name:
            lines.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.icon != after.icon:
            lines.append("**Icon changed**")
        if before.vanity_url_code != after.vanity_url_code:
            lines.append(f"**Vanity URL:** `{before.vanity_url_code}` → `{after.vanity_url_code}`")
        if not lines:
            return
        await self._send(after, "server", "Server Updated", lines)

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self, guild: discord.Guild,
        before: tuple[discord.Emoji, ...],
        after: tuple[discord.Emoji, ...],
    ) -> None:
        b_ids = {e.id for e in before}
        a_ids = {e.id for e in after}
        for e in after:
            if e.id not in b_ids:
                await self._send(guild, "server", "Emoji Added", [f"**Emoji:** `:{e.name}:` `{e.id}`"])
        for e in before:
            if e.id not in a_ids:
                await self._send(guild, "server", "Emoji Deleted", [f"**Emoji:** `:{e.name}:` `{e.id}`"])

    @commands.Cog.listener()
    async def on_guild_stickers_update(
        self, guild: discord.Guild,
        before: tuple[discord.GuildSticker, ...],
        after: tuple[discord.GuildSticker, ...],
    ) -> None:
        b_ids = {s.id for s in before}
        a_ids = {s.id for s in after}
        for s in after:
            if s.id not in b_ids:
                await self._send(guild, "server", "Sticker Added", [f"**Sticker:** `{s.name}` `{s.id}`"])
        for s in before:
            if s.id not in a_ids:
                await self._send(guild, "server", "Sticker Deleted", [f"**Sticker:** `{s.name}` `{s.id}`"])

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if not invite.guild:
            return
        inviter = f"**{invite.inviter}**" if invite.inviter else "`Unknown`"
        ch = invite.channel.mention if invite.channel and hasattr(invite.channel, "mention") else "`Unknown`"
        await self._send(
            invite.guild, "server", "Invite Created",
            [f"**Code:** `{invite.code}`", f"**By:** {inviter}", f"**Channel:** {ch}"],
        )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite) -> None:
        if not invite.guild:
            return
        ch = invite.channel.mention if invite.channel and hasattr(invite.channel, "mention") else "`Unknown`"
        await self._send(
            invite.guild, "server", "Invite Deleted",
            [f"**Code:** `{invite.code}`", f"**Channel:** {ch}"],
        )

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        """Webhook create/delete — fetch audit log to identify action and executor."""
        await asyncio.sleep(0.5)  # small delay so audit log is available
        action_str = "Webhook Changed"
        executor_str = "`Unknown`"
        try:
            async for entry in channel.guild.audit_logs(limit=3, action=discord.AuditLogAction.webhook_create):
                if abs((discord.utils.utcnow() - entry.created_at).total_seconds()) < 5:
                    action_str = "Webhook Created"
                    executor_str = f"**{entry.user}**" if entry.user else "`Unknown`"
                    break
            else:
                async for entry in channel.guild.audit_logs(limit=3, action=discord.AuditLogAction.webhook_delete):
                    if abs((discord.utils.utcnow() - entry.created_at).total_seconds()) < 5:
                        action_str = "Webhook Deleted"
                        executor_str = f"**{entry.user}**" if entry.user else "`Unknown`"
                        break
        except discord.Forbidden:
            pass
        await self._send(
            channel.guild, "server", action_str,
            [f"**Channel:** {channel.mention}", f"**By:** {executor_str}"],
        )

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        await self._send(
            thread.guild, "server", "Thread Created",
            [f"**Thread:** {thread.mention} in {thread.parent.mention if thread.parent else '`Unknown`'}"],
        )

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        await self._send(
            thread.guild, "server", "Thread Deleted",
            [f"**Thread:** `{thread.name}` `{thread.id}`"],
        )

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent) -> None:
        creator = f"**{event.creator}**" if event.creator else "`Unknown`"
        await self._send(
            event.guild, "server", "Event Scheduled",
            [f"**Event:** `{event.name}`", f"**By:** {creator}"],
        )

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent) -> None:
        await self._send(
            event.guild, "server", "Event Cancelled",
            [f"**Event:** `{event.name}`"],
        )

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction) -> None:
        guild = self.bot.get_guild(execution.guild_id)
        if not guild:
            return
        ch_mention = f"<#{execution.channel_id}>" if execution.channel_id else "`DM/Unknown`"
        matched = f"`{_truncate(execution.matched_content or execution.matched_keyword or '—', 100)}`"
        await self._send(
            guild, "server", "AutoMod Action",
            [
                f"**User:** <@{execution.user_id}>",
                f"**Channel:** {ch_mention}",
                f"**Matched:** {matched}",
            ],
        )

    # ─────────────── VOICE ───────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return
        guild = member.guild
        user_str = f"**{member.display_name}** `{member.id}`"

        if before.channel is None and after.channel is not None:
            await self._send(guild, "voice", "Voice Joined", [f"**User:** {user_str}", f"**Channel:** {after.channel.mention}"])
        elif before.channel is not None and after.channel is None:
            await self._send(guild, "voice", "Voice Left", [f"**User:** {user_str}", f"**Channel:** {before.channel.mention}"])
        elif before.channel != after.channel:
            await self._send(
                guild, "voice", "Voice Moved",
                [
                    f"**User:** {user_str}",
                    f"**From:** {before.channel.mention if before.channel else '`—`'}",
                    f"**To:** {after.channel.mention if after.channel else '`—`'}",
                ],
            )
        elif before.self_mute != after.self_mute or before.self_deaf != after.self_deaf:
            state_parts = []
            if after.self_mute:
                state_parts.append("Self-Muted")
            if after.self_deaf:
                state_parts.append("Self-Deafened")
            state_str = ", ".join(state_parts) or "Unmuted/Undeafened"
            await self._send(guild, "voice", "Voice State Changed", [f"**User:** {user_str}", f"**State:** `{state_str}`"])
        elif before.mute != after.mute or before.deaf != after.deaf:
            state_parts = []
            if after.mute:
                state_parts.append("Server Muted")
            if after.deaf:
                state_parts.append("Server Deafened")
            state_str = ", ".join(state_parts) or "Unmuted/Undeafened"
            await self._send(guild, "voice", "Voice State Changed", [f"**User:** {user_str}", f"**State:** `{state_str}`"])

    # ─────────────── COMMANDS ───────────────

    def _build_logs_overview_card(self, guild: discord.Guild, author_name: str) -> KyroContainer:
        """Construct the Components V2 card showing currently configured log channels."""
        settings = self.bot.log_mgr.get_guild_settings(guild.id)
        dot = getattr(self.bot, "custom_emojis", {}).get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Server Logs Configuration**\n"
                "> Audit logs tracking events across messages, members, roles, and voice."
            )
        )
        container.add_separator(divider=True)

        categories = [
            ("All (Unified)", settings.get("all")),
            ("Moderation", settings.get("mod")),
            ("Message", settings.get("message")),
            ("Member", settings.get("member")),
            ("Server", settings.get("server")),
            ("Voice", settings.get("voice")),
        ]

        lines = []
        for name, ch_id in categories:
            if ch_id:
                ch = guild.get_channel(ch_id)
                ch_str = ch.mention if ch else f"`#{ch_id}`"
            else:
                ch_str = "`Not Set`"
            lines.append(f"> {dot} **{name}:** {ch_str}")

        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {author_name}")
        return container

    @commands.hybrid_group(
        name="logs",
        aliases=["log", "serverlogs"],
        description="View and configure server audit logging channels.",
        invoke_without_command=True,
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def logs(self, ctx: CustomContext) -> None:
        """Display the current logging configuration."""
        card = self._build_logs_overview_card(ctx.guild, ctx.author.display_name)
        await send_container_response(ctx, card)

    @logs.command(name="show", aliases=["view", "config", "status"], description="Display all configured logging channels.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def logs_show(self, ctx: CustomContext) -> None:
        """Display all configured logging channels."""
        card = self._build_logs_overview_card(ctx.guild, ctx.author.display_name)
        await send_container_response(ctx, card)

    @logs.command(name="channel", aliases=["set"], description="Bind a channel for a specific log category.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(
        category="Logging category to set",
        channel="Target channel for logs",
    )
    @app_commands.choices(
        category=[
            app_commands.Choice(name="All (Unified)", value="all"),
            app_commands.Choice(name="Mod", value="mod"),
            app_commands.Choice(name="Message", value="message"),
            app_commands.Choice(name="Member", value="member"),
            app_commands.Choice(name="Server", value="server"),
            app_commands.Choice(name="Voice", value="voice"),
        ]
    )
    async def logs_channel(
        self,
        ctx: CustomContext,
        category: str,
        channel: discord.TextChannel,
    ) -> None:
        """Set a target channel for a logging category."""
        clean_cat = category.lower()
        if clean_cat not in ["all", "mod", "message", "member", "server", "voice"]:
            await ctx.send_error("Invalid category. Choose from: `all`, `mod`, `message`, `member`, `server`, `voice`.")
            return

        await self.bot.log_mgr.set_log_channel(ctx.guild.id, clean_cat, channel.id)

        dot = getattr(self.bot, "custom_emojis", {}).get("heart_dot", "•")
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Server Logs Updated**")
        container.add_separator(divider=True)
        container.add_text(
            f"> {dot} **Category:** `{clean_cat.capitalize()}`\n"
            f"> {dot} **Channel:** {channel.mention}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Configured by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @logs.command(name="reset", description="Clear logging channel configurations.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @app_commands.describe(category="Category to reset (leave blank to reset all)")
    @app_commands.choices(
        category=[
            app_commands.Choice(name="All Categories", value="all_logs"),
            app_commands.Choice(name="Unified (all)", value="all"),
            app_commands.Choice(name="Mod", value="mod"),
            app_commands.Choice(name="Message", value="message"),
            app_commands.Choice(name="Member", value="member"),
            app_commands.Choice(name="Server", value="server"),
            app_commands.Choice(name="Voice", value="voice"),
        ]
    )
    async def logs_reset(
        self,
        ctx: CustomContext,
        category: str | None = None,
    ) -> None:
        """Reset a specific log channel or all log channels."""
        target_cat = category.lower() if category else "all_logs"
        await self.bot.log_mgr.reset_logs(ctx.guild.id, target_cat)

        dot = getattr(self.bot, "custom_emojis", {}).get("heart_dot", "•")
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Server Logs Reset**")
        container.add_separator(divider=True)
        if target_cat == "all_logs":
            container.add_text(f"> {dot} All logging channel bindings have been cleared.")
        else:
            container.add_text(f"> {dot} **Category:** `{target_cat.capitalize()}` has been reset to `Not Set`.")
        container.add_separator(divider=True)
        container.add_text(f"-# Reset by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ServerLogsCog(bot))
