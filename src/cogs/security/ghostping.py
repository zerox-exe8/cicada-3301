"""
Kyro Discord Bot - Real-Time Ghost-Ping & Stealth Audit Monitor
Detects stealth deleted messages containing user or role mentions and logs them immediately.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Security.GhostPing")


class GhostPing(commands.Cog):
    """Real-time ghost-ping interceptor and stealth deleted mention detector."""
    category: str = "Security"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # LRU in-memory message cache: message_id -> (author_id, content, mentions, channel_id, timestamp)
        self._message_cache: OrderedDict[int, dict] = OrderedDict()
        self._settings_cache: dict[int, bool] = {}

    async def _is_enabled(self, guild_id: int) -> bool:
        """Check if ghost-ping detection is enabled for guild."""
        if guild_id not in self._settings_cache:
            row = await self.bot.db.fetch_one(
                "SELECT is_enabled FROM guild_ghostping_settings WHERE guild_id = ?;",
                guild_id,
            )
            self._settings_cache[guild_id] = row["is_enabled"] if row else True
        return self._settings_cache[guild_id]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Cache incoming messages that contain mentions."""
        if message.author.bot or not message.guild:
            return

        # Cache if message contains user mentions or role mentions
        if message.mentions or message.role_mentions or message.mention_everyone:
            if len(self._message_cache) > 5000:
                self._message_cache.popitem(last=False)

            self._message_cache[message.id] = {
                "author": message.author,
                "content": message.content,
                "user_mentions": [m.mention for m in message.mentions if not m.bot and m.id != message.author.id],
                "role_mentions": [r.name for r in message.role_mentions],
                "everyone": message.mention_everyone,
                "channel_id": message.channel.id,
                "timestamp": time.time(),
            }

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Detect and expose deleted messages with mentions."""
        if not message.guild:
            return

        is_active = await self._is_enabled(message.guild.id)
        if not is_active:
            return

        entry = self._message_cache.pop(message.id, None)
        if not entry:
            return

        # Only trigger if deleted within 90 seconds
        if time.time() - entry["timestamp"] > 90:
            return

        author = entry["author"]
        mentions = entry["user_mentions"]
        if entry["everyone"]:
            mentions.append("@everyone")
        if entry["role_mentions"]:
            mentions.extend([f"@{r}" for r in entry["role_mentions"]])

        if not mentions:
            return

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "-")
        badge = e_reg.get("icons_guardian", "")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{badge} Ghost-Ping Detected**\n"
                f"> A message containing mentions was deleted in {message.channel.mention}."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Author:** {author.mention} (`{author.id}`)\n"
            f"{dot} **Mentioned:** {', '.join(mentions)}\n"
            f"{dot} **Message Content:**\n```\n{entry['content'][:800]}\n```"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Timestamp: <t:{int(entry['timestamp'])}:R>")

        # Dispatch to mod log or channel
        log_ch = self.bot.log_mgr.get_log_channel(message.guild, "mod")
        target_ch = log_ch if log_ch else message.channel

        try:
            await send_container_response(target_ch, container)
        except Exception as e:
            logger.debug(f"Could not send ghost ping alert in {message.guild.name}: {e}")

    @commands.hybrid_command(
        name="ghostping",
        aliases=["ghostpingdetector"],
        description="Toggle real-time ghost-ping mention detection.",
    )
    @app_commands.describe(state="Action: on or off")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def ghostping_toggle(self, ctx: CustomContext, state: Optional[str] = None) -> None:
        """Toggle ghost-ping detection."""
        current = await self._is_enabled(ctx.guild.id)
        new_state = not current if state is None else state.lower() in ["on", "enable", "true", "yes"]

        await self.bot.db.execute(
            """
            INSERT INTO guild_ghostping_settings (guild_id, is_enabled)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET is_enabled = EXCLUDED.is_enabled;
            """,
            ctx.guild.id,
            new_state,
        )
        self._settings_cache[ctx.guild.id] = new_state

        container = KyroContainer(accent_color=None)
        state_str = "ACTIVATED" if new_state else "DEACTIVATED"
        container.add_section(
            content=(
                f"**Ghost-Ping Detector: {state_str}**\n"
                f"> Kyro will {'now intercept and reveal all deleted ghost-pings' if new_state else 'no longer monitor for deleted mentions'}."
            )
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load the GhostPing Cog into KyroBot."""
    await bot.add_cog(GhostPing(bot))
