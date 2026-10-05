from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.ServerLogs")


def _truncate(text: str, limit: int = 400) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


class ServerLogsCog(commands.Cog):
    """Unified server audit logging — message / member / server / voice.

    All cards use the clean Antinuke-style KyroContainer design.
    Channels resolve via LogManager with fallback to the `all` channel
    (kyro_logs when auto-created by antinuke enable).
    """
    category: str = "Logging"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    async def _send(
        self,
        guild: discord.Guild,
        log_type: str,
        title: str,
        lines: list[str],
    ) -> None:
        if not guild or not lines:
            return
        try:
            channel = self.bot.log_mgr.get_log_channel(guild, log_type)
        except Exception:
            channel = None
        if channel is None:
            return

        e_reg = getattr(self.bot, "custom_emojis", {})
        dot = e_reg.get("heart_dot", "-")

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"**{title}**")
        container.add_separator(divider=True)
        body = "\n".join(f"{dot} {ln}" if not ln.startswith(f"{dot}") else ln for ln in lines)
        container.add_text(body)
        container.add_separator(divider=True)
        container.add_text(f"-# Timestamp: <t:{int(discord.utils.utcnow().timestamp())}:f>")

        try:
            await send_container_response(channel, container)
        except Exception as e:
            logger.debug(f"Server log dispatch failed ({log_type}/{title}): {e}")

    # ---------------- MESSAGE ------------------

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        content = _truncate(message.content or "*No text content (embed/attachment)*")
        await self._send(
            message.guild, "message", "Message Deleted",
            [
                f"**Author:** **{message.author.display_name}** `「{message.author.id}」`",
                f"**Channel:** {message.channel.mention}",
                f"**Content:** `{content}`",
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
                f"**Author:** **{after.author.display_name}** `「{after.author.id}」`",
                f"**Channel:** {after.channel.mention} • [Jump]({after.jump_url})",
                f"**Before:** `{_truncate(before.content or '')}`",
                f"**After:** `{_truncate(after.content or '')}`",
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
            guild, "message", "Bulk Messages Purged",
            [
                f"**Count:** `{len(messages)}`",
                f"**Channel:** {ch.mention if hasattr(ch, 'mention') else ch}",
            ],
        )

    # ---------------- MEMBER ------------------

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        # Skip antinuke's own bot-add handler duplication? No — this is general info.
        if member.bot:
            await self._send(
                member.guild, "member", "Bot Added",
                [f"**Bot:** **{member}** `「{member.id}」`"],
            )
            return
        await self._send(
            member.guild, "member", "Member Joined",
            [
                f"**User:** **{member}** `「{member.id}」`",
                f"**Account Created:** <t:{int(member.created_at.timestamp())}:R>",
            ],
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        await self._send(
            member.guild, "member", "Member Left",
            [f"**User:** **{member}** `「{member.id}」`"],
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        await self._send(
            guild, "member", "Member Banned",
            [f"**User:** **{user}** `「{user.id}」`"],
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        await self._send(
            guild, "member", "Member Unbanned",
            [f"**User:** **{user}** `「{user.id}」`"],
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        lines: list[str] = []
        if before.nick != after.nick:
            lines.append(f"**Nickname:** `{before.nick}` → `{after.nick}`")
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
        lines.insert(0, f"**User:** **{after}** `「{after.id}」`")
        await self._send(after.guild, "member", "Member Updated", lines)

    # ---------------- SERVER ------------------

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
            [f"**Channel:** `#{channel.name}` `「{channel.id}」`"],
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel
    ) -> None:
        if before.name != after.name:
            await self._send(
                after.guild, "server", "Channel Renamed",
                [f"**Before:** `#{before.name}`", f"**After:** {after.mention}"],
            )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self._send(
            role.guild, "server", "Role Created",
            [f"**Role:** {role.mention} `「{role.id}」`"],
        )

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self._send(
            role.guild, "server", "Role Deleted",
            [f"**Role:** `@{role.name}` `「{role.id}」`"],
        )

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        if before.name != after.name:
            await self._send(
                after.guild, "server", "Role Renamed",
                [f"**Before:** `@{before.name}`", f"**After:** {after.mention}"],
            )

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        if before.name != after.name:
            await self._send(
                after, "server", "Server Renamed",
                [f"**Before:** `{before.name}`", f"**After:** `{after.name}`"],
            )

    @commands.Cog.listener()
    async def on_guild_emojis_update(
        self, guild: discord.Guild, before: tuple[discord.Emoji, ...], after: tuple[discord.Emoji, ...]
    ) -> None:
        b_ids = {e.id for e in before}
        a_ids = {e.id for e in after}
        for e in after:
            if e.id not in b_ids:
                await self._send(guild, "server", "Emoji Added", [f"**Emoji:** `{e.name}` `「{e.id}」`"])
        for e in before:
            if e.id not in a_ids:
                await self._send(guild, "server", "Emoji Deleted", [f"**Emoji:** `{e.name}` `「{e.id}」`"])

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite) -> None:
        if not invite.guild:
            return
        inviter = f"**{invite.inviter}**" if invite.inviter else "`Unknown`"
        await self._send(
            invite.guild, "server", "Invite Created",
            [f"**Code:** `{invite.code}`", f"**By:** {inviter}", f"**Channel:** {invite.channel.mention if invite.channel else '`Unknown`'}"],
        )

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel) -> None:
        await self._send(
            channel.guild, "server", "Webhooks Updated",
            [f"**Channel:** {channel.mention}"],
        )

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        await self._send(
            thread.guild, "server", "Thread Created",
            [f"**Thread:** {thread.mention} `「{thread.id}」`"],
        )

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        await self._send(
            thread.guild, "server", "Thread Deleted",
            [f"**Thread:** `{thread.name}` `「{thread.id}」`"],
        )

    # ---------------- VOICE ------------------

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
        if before.channel is None and after.channel is not None:
            await self._send(
                guild, "voice", "Voice Joined",
                [f"**User:** **{member.display_name}** `「{member.id}」`", f"**Channel:** {after.channel.mention}"],
            )
        elif before.channel is not None and after.channel is None:
            await self._send(
                guild, "voice", "Voice Left",
                [f"**User:** **{member.display_name}** `「{member.id}」`", f"**Channel:** {before.channel.mention}"],
            )
        elif before.channel != after.channel:
            await self._send(
                guild, "voice", "Voice Moved",
                [
                    f"**User:** **{member.display_name}** `「{member.id}」`",
                    f"**From:** {before.channel.mention if before.channel else '`—`'}",
                    f"**To:** {after.channel.mention if after.channel else '`—`'}",
                ],
            )
        elif before.mute != after.mute or before.deaf != after.deaf:
            state = []
            if after.mute:
                state.append("Muted")
            if after.deaf:
                state.append("Deafened")
            await self._send(
                guild, "voice", "Voice State Changed",
                [f"**User:** **{member.display_name}** `「{member.id}」`", f"**State:** `{', '.join(state) or 'Unmuted'}`"],
            )


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ServerLogsCog(bot))
