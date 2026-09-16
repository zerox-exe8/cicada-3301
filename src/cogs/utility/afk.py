"""
Kyro Discord Bot - AFK (Away From Keyboard) System
High-performance in-memory cached AFK notifications with database persistence,
smart mention notifications, nickname updates, and automatic status clearing.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time
from typing import TYPE_CHECKING, Optional, Any
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Utility.AFK")


@dataclass
class AFKData:
    """In-memory representation of an AFK user's state."""
    user_id: int
    guild_id: int
    reason: str
    created_at: datetime.datetime
    nickname_changed: bool = False
    original_nickname: Optional[str] = None


def format_duration(seconds: float) -> str:
    """Convert elapsed seconds into a human-readable string (e.g. '2h 15m 30s')."""
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 and len(parts) < 2:
        parts.append(f"{secs}s")
    return " ".join(parts)


class AFKNoteModal(discord.ui.Modal):
    """Modal to leave a private note for an AFK user."""

    def __init__(self, bot: KyroBot, target_id: int, target_name: str, guild_id: int) -> None:
        super().__init__(title=f"Note for {target_name[:20]}")
        self.bot = bot
        self.target_id = target_id
        self.target_name = target_name
        self.guild_id = guild_id

        self.note_input = discord.ui.TextInput(
            label="Your Message / Note",
            style=discord.TextStyle.paragraph,
            placeholder="Write a message to be delivered when they return...",
            required=True,
            max_length=250,
        )
        self.add_item(self.note_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        note_text = self.note_input.value.strip()
        if not note_text:
            await interaction.response.send_message("Note cannot be empty.", ephemeral=True)
            return

        try:
            await self.bot.db.execute(
                """
                INSERT INTO user_afk_notes (target_user_id, sender_id, sender_name, guild_id, note)
                VALUES ($1, $2, $3, $4, $5);
                """,
                self.target_id,
                interaction.user.id,
                interaction.user.display_name,
                self.guild_id,
                note_text,
            )
            await interaction.response.send_message(
                f"Your note for **{self.target_name}** has been saved! They will receive it as soon as they return.",
                ephemeral=True,
            )
        except Exception as e:
            logger.error(f"Failed to save AFK note: {e}")
            await interaction.response.send_message("Failed to save note due to an internal error.", ephemeral=True)


class AFKLeaveNoteView(discord.ui.View):
    """Interactive button to leave a note for an AFK user."""

    def __init__(self, bot: KyroBot, target_id: int, target_name: str, guild_id: int) -> None:
        super().__init__(timeout=300.0)
        self.bot = bot
        self.target_id = target_id
        self.target_name = target_name
        self.guild_id = guild_id

    @discord.ui.button(label="Leave a Note", style=discord.ButtonStyle.secondary, custom_id="afk_leave_note_btn")
    async def leave_note_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id == self.target_id:
            await interaction.response.send_message("You cannot leave a note for yourself.", ephemeral=True)
            return
        modal = AFKNoteModal(self.bot, self.target_id, self.target_name, self.guild_id)
        await interaction.response.send_modal(modal)


class AFKCog(commands.Cog, name="AFK"):
    """Away From Keyboard (AFK) status management."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # In-memory fast cache: (user_id, guild_id) -> AFKData
        self._afk_cache: dict[tuple[int, int], AFKData] = {}
        # Mention notification cooldown: (guild_id, user_id, channel_id) -> last_notified_timestamp
        self._mention_cooldowns: dict[tuple[int, int, int], float] = {}
        self._loaded = False

    async def cog_load(self) -> None:
        """Load persistent AFK states from database into memory on cog startup."""
        asyncio.create_task(self._load_afk_cache())

    async def _load_afk_cache(self) -> None:
        """Initialize AFK table and populate in-memory cache."""
        try:
            # Ensure table exists in case migration hasn't executed
            await self.bot.db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_afk (
                    user_id BIGINT,
                    guild_id BIGINT,
                    reason TEXT DEFAULT 'AFK',
                    nickname_changed BOOLEAN DEFAULT FALSE,
                    original_nickname VARCHAR(64),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, guild_id)
                );
                """
            )
            rows = await self.bot.db.fetch_all("SELECT * FROM user_afk;")
            for row in rows:
                user_id = int(row["user_id"])
                guild_id = int(row["guild_id"])
                raw_created = row.get("created_at")
                if isinstance(raw_created, datetime.datetime):
                    created_at = raw_created
                elif isinstance(raw_created, str):
                    try:
                        created_at = datetime.datetime.fromisoformat(raw_created)
                    except Exception:
                        created_at = discord.utils.utcnow()
                else:
                    created_at = discord.utils.utcnow()

                self._afk_cache[(user_id, guild_id)] = AFKData(
                    user_id=user_id,
                    guild_id=guild_id,
                    reason=row.get("reason") or "AFK",
                    created_at=created_at,
                    nickname_changed=bool(row.get("nickname_changed", False)),
                    original_nickname=row.get("original_nickname"),
                )
            self._loaded = True
            logger.info(f"Loaded {len(self._afk_cache)} active AFK record(s) into memory cache.")
        except Exception as e:
            logger.error(f"Failed to load AFK cache: {e}", exc_info=e)

    @commands.hybrid_command(
        name="afk",
        description="Set your AFK status with an optional reason.",
    )
    @app_commands.describe(reason="Reason for being AFK (optional)")
    @commands.guild_only()
    async def afk(
        self,
        ctx: CustomContext,
        *,
        reason: Optional[str] = None,
    ) -> None:
        """Set your AFK status in this server."""
        if not ctx.guild:
            return

        final_reason = reason.strip() if reason and reason.strip() else "AFK"
        if len(final_reason) > 250:
            final_reason = final_reason[:247] + "..."

        now = discord.utils.utcnow()
        user_id = ctx.author.id
        guild_id = ctx.guild.id
        key = (user_id, guild_id)

        # Handle Nickname update if permissions permit
        nickname_changed = False
        original_nickname: Optional[str] = None
        if isinstance(ctx.author, discord.Member):
            original_nickname = ctx.author.nick or ctx.author.name
            # Check if bot can edit author's nickname
            me = ctx.guild.me
            can_manage = me.guild_permissions.manage_nicknames or me.guild_permissions.administrator
            try:
                is_higher = me.top_role > ctx.author.top_role
            except Exception:
                is_higher = False
            is_owner = ctx.author.id == ctx.guild.owner_id

            if can_manage and is_higher and not is_owner:
                current_display = ctx.author.display_name
                if not current_display.startswith("[AFK] "):
                    new_nick = f"[AFK] {current_display}"[:32]
                    try:
                        await ctx.author.edit(nick=new_nick, reason="Kyro AFK Status Update")
                        nickname_changed = True
                    except Exception as e:
                        logger.debug(f"Unable to update nickname for AFK user {ctx.author}: {e}")

        # Update cache
        afk_entry = AFKData(
            user_id=user_id,
            guild_id=guild_id,
            reason=final_reason,
            created_at=now,
            nickname_changed=nickname_changed,
            original_nickname=original_nickname,
        )
        self._afk_cache[key] = afk_entry

        # Persist to database
        try:
            await self.bot.db.execute(
                """
                INSERT INTO user_afk (user_id, guild_id, reason, nickname_changed, original_nickname, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (user_id, guild_id)
                DO UPDATE SET
                    reason = EXCLUDED.reason,
                    nickname_changed = EXCLUDED.nickname_changed,
                    original_nickname = EXCLUDED.original_nickname,
                    created_at = EXCLUDED.created_at;
                """,
                user_id,
                guild_id,
                final_reason,
                nickname_changed,
                original_nickname,
                now,
            )
        except Exception as e:
            logger.error(f"Failed to persist AFK record for user {user_id}: {e}", exc_info=e)

        # Dispatch confirmation container
        e_reg = getattr(self.bot, "custom_emojis", {})
        dot = e_reg.get("heart_dot", "-")
        clock = e_reg.get("icons_clock", "")
        clock_str = f"{clock} " if clock else ""

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"{clock_str}**AFK Status Set**\n"
                f"> You are now AFK: **{final_reason}**\n"
                f"> I will notify anyone who mentions you and automatically remove your AFK status when you next chat."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **User:** **{ctx.author.display_name}**\n"
            f"{dot} **Reason:** `{final_reason}`\n"
            f"{dot} **Set At:** <t:{int(now.timestamp())}:t> (<t:{int(now.timestamp())}:R>)"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Type a message in any channel to remove your AFK status.")

        await send_container_response(ctx, container)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Monitor messages for AFK authors returning or mentions of AFK members."""
        if message.author.bot or not message.guild:
            return

        author_id = message.author.id
        guild_id = message.guild.id
        now = discord.utils.utcnow()
        author_key = (author_id, guild_id)

        # ----------------------------------------------------
        # 1. Check if the message author was AFK (Welcome back)
        # ----------------------------------------------------
        if author_key in self._afk_cache:
            afk_data = self._afk_cache[author_key]
            # Grace period: ignore messages sent within 6 seconds of setting AFK
            elapsed_seconds = (now - afk_data.created_at).total_seconds()
            if elapsed_seconds > 6.0:
                # Remove from cache & database
                self._afk_cache.pop(author_key, None)
                try:
                    await self.bot.db.execute(
                        "DELETE FROM user_afk WHERE user_id = ? AND guild_id = ?;",
                        author_id,
                        guild_id,
                    )
                except Exception as e:
                    logger.debug(f"Failed to delete AFK record from database: {e}")

                # Restore nickname if it was changed
                if afk_data.nickname_changed and isinstance(message.author, discord.Member):
                    try:
                        current_nick = message.author.nick or ""
                        if current_nick.startswith("[AFK] "):
                            await message.author.edit(
                                nick=afk_data.original_nickname,
                                reason="Kyro AFK Status Removal",
                            )
                    except Exception as e:
                        logger.debug(f"Unable to revert nickname for {message.author}: {e}")

                # Check and deliver pending AFK notes / voice mails
                pending_notes = []
                try:
                    pending_notes = await self.bot.db.fetch_all(
                        "SELECT sender_name, note, created_at FROM user_afk_notes WHERE target_user_id = $1 AND guild_id = $2 ORDER BY created_at ASC LIMIT 8;",
                        author_id,
                        guild_id,
                    )
                    if pending_notes:
                        await self.bot.db.execute(
                            "DELETE FROM user_afk_notes WHERE target_user_id = $1 AND guild_id = $2;",
                            author_id,
                            guild_id,
                        )
                except Exception as e:
                    logger.debug(f"Failed to fetch AFK notes: {e}")

                # Send welcome back card
                e_reg = getattr(self.bot, "custom_emojis", {})
                dot = e_reg.get("heart_dot", "-")
                wave = e_reg.get("icons_correct", "")
                wave_str = f"{wave} " if wave else ""
                duration_str = format_duration(elapsed_seconds)

                container = KyroContainer(accent_color=None)
                container.add_section(
                    content=(
                        f"{wave_str}**Welcome Back, {message.author.display_name}!**\n"
                        f"> Your AFK status has been automatically removed."
                    )
                )
                container.add_separator(divider=True)
                container.add_text(
                    f"{dot} **Time AFK:** `{duration_str}`\n"
                    f"{dot} **Reason was:** `{afk_data.reason}`"
                )

                if pending_notes:
                    container.add_separator(divider=True)
                    notes_lines = []
                    for n in pending_notes:
                        s_name = n.get("sender_name", "Someone")
                        note_msg = n.get("note", "")
                        notes_lines.append(f"> **{s_name}:** {note_msg}")
                    container.add_section(
                        content=(
                            f"**AFK Voice Mail ({len(pending_notes)} Note{'s' if len(pending_notes) > 1 else ''} Received)**\n"
                            + "\n".join(notes_lines)
                        )
                    )

                container.add_separator(divider=True)
                delete_delay = 18.0 if pending_notes else 7.0
                container.add_text(f"-# This notice will automatically delete in {int(delete_delay)} seconds.")

                try:
                    notice_msg = await send_container_response(message.channel, container)
                    if notice_msg and isinstance(notice_msg, discord.Message):
                        async def _cleanup_notice(m: discord.Message) -> None:
                            await asyncio.sleep(delete_delay)
                            try:
                                await m.delete()
                            except Exception:
                                pass

                        asyncio.create_task(_cleanup_notice(notice_msg))
                except Exception as e:
                    logger.debug(f"Failed to send AFK welcome back notice: {e}")

        # ----------------------------------------------------
        # 2. Check if any mentioned users are AFK
        # ----------------------------------------------------
        if message.mentions:
            now_ts = time.time()
            for mentioned_user in message.mentions:
                if mentioned_user.id == author_id or mentioned_user.bot:
                    continue

                mentioned_key = (mentioned_user.id, guild_id)
                if mentioned_key in self._afk_cache:
                    cooldown_key = (guild_id, mentioned_user.id, message.channel.id)
                    last_notified = self._mention_cooldowns.get(cooldown_key, 0.0)
                    # 10s cooldown per AFK user per channel to prevent notification spam
                    if now_ts - last_notified < 10.0:
                        continue
                    self._mention_cooldowns[cooldown_key] = now_ts

                    target_afk = self._afk_cache[mentioned_key]
                    e_reg = getattr(self.bot, "custom_emojis", {})
                    dot = e_reg.get("heart_dot", "-")
                    clock = e_reg.get("icons_clock", "")
                    clock_str = f"{clock} " if clock else ""

                    container = KyroContainer(accent_color=None)
                    container.add_section(
                        content=(
                            f"{clock_str}**{mentioned_user.display_name} is currently AFK**\n"
                            f"> {target_afk.reason}"
                        )
                    )
                    container.add_separator(divider=True)
                    container.add_text(
                        f"{dot} **Reason:** `{target_afk.reason}`\n"
                        f"{dot} **Went AFK:** <t:{int(target_afk.created_at.timestamp())}:R>"
                    )
                    container.add_separator(divider=True)
                    container.add_text(f"-# Mentioned by {message.author.display_name} | Click below to leave a note")

                    view = AFKLeaveNoteView(self.bot, mentioned_user.id, mentioned_user.display_name, guild_id)
                    try:
                        await send_container_response(message.channel, container, view=view)
                    except Exception as e:
                        logger.debug(f"Failed to send AFK mention notification: {e}")


async def setup(bot: KyroBot) -> None:
    """Load the AFKCog into KyroBot."""
    await bot.add_cog(AFKCog(bot))
