"""
Kyro Discord Bot - Sticky Messages Cog
Auto-pinned live notices that stay pinned to the bottom of the channel with rate-limit debounce.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.bot import KyroBot
from src.utils.containers import KyroContainer

logger = logging.getLogger("Kyro.Cogs.Sticky")


class Sticky(commands.Cog):
    """Sticky message system that automatically resends notices to stay at the bottom of active channels."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    # ─── MESSAGE LISTENER WITH DEBOUNCE ───────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Monitor chat activity and move sticky notice to the bottom."""
        # 1. Ignore bot messages, system messages, or DMs
        if message.author.bot or not message.guild or not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return

        channel_id = message.channel.id

        # 2. Check if channel has an active sticky message
        if not self.bot.sticky_mgr.has_sticky(channel_id):
            return

        # 3. Debounce check: ensure at least 1 message and 2.0s passed to prevent 429 rate limit spam
        if not self.bot.sticky_mgr.increment_and_check_debounce(channel_id, min_messages=1, min_seconds=2.0):
            return

        sticky_data = self.bot.sticky_mgr.get_sticky(channel_id)
        if not sticky_data or not sticky_data.get("is_enabled", True):
            return

        lock = self.bot.sticky_mgr.get_lock(channel_id)
        async with lock:
            # 4. Safe deletion of previous sticky message
            old_msg_id = sticky_data.get("last_message_id")
            if old_msg_id:
                try:
                    old_msg = await message.channel.fetch_message(old_msg_id)
                    await old_msg.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
                except Exception as e:
                    logger.debug(f"Notice deleting old sticky message in {channel_id}: {e}")

            # 5. Build and send new sticky note at the bottom
            container = KyroContainer(accent_color=None)
            title = sticky_data.get("embed_title") or "📌 Pinned Notice"
            container.add_section(
                content=(
                    f"### {title}\n"
                    f"{sticky_data['content']}"
                )
            )

            try:
                new_msg = await message.channel.send(embed=container.to_embed())
                await self.bot.sticky_mgr.update_last_message_id(channel_id, new_msg.id)
                self.bot.sticky_mgr.reset_debounce(channel_id)
            except (discord.Forbidden, discord.HTTPException) as e:
                logger.debug(f"Could not dispatch sticky message in {channel_id}: {e}")

    # ─── SLASH COMMANDS ───────────────────────────────────────────────────────

    sticky_group = app_commands.Group(name="sticky", description="Manage auto-pinned sticky messages in channels")

    @sticky_group.command(name="set", description="Set or update an auto-pinned sticky notice for a channel")
    @app_commands.describe(
        channel="The channel where the message should stick to the bottom",
        message="The notice content or rules to display",
        title="Optional custom header title for the notice",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_set(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str,
        title: Optional[str] = "📌 Pinned Notice",
    ) -> None:
        """Create or update a sticky message."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        # Check bot permissions in target channel
        perms = channel.permissions_for(guild.me)
        if not perms.send_messages or not perms.embed_links:
            await interaction.followup.send(
                f"I need `Send Messages` and `Embed Links` permissions in {channel.mention} to post sticky messages.",
                ephemeral=True,
            )
            return

        # Save to database and cache
        await self.bot.sticky_mgr.set_sticky(
            channel_id=channel.id,
            guild_id=guild.id,
            content=message.strip(),
            embed_title=title.strip() if title else None,
            created_by=interaction.user.id,
        )

        # Immediately dispatch first sticky post in the channel
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### {title or '📌 Pinned Notice'}\n"
                f"{message.strip()}"
            )
        )
        try:
            first_msg = await channel.send(embed=container.to_embed())
            await self.bot.sticky_mgr.update_last_message_id(channel.id, first_msg.id)
            self.bot.sticky_mgr.reset_debounce(channel.id)
        except discord.HTTPException as e:
            logger.debug(f"Notice dispatching initial sticky in {channel.id}: {e}")

        resp_container = KyroContainer(accent_color=None)
        resp_container.add_section(
            content=(
                f"### Sticky Notice Configured\n"
                f"> Sticky message is now active in {channel.mention}. It will automatically re-pin itself to the bottom of the chat as members talk."
            )
        )
        resp_container.add_separator(divider=True)
        resp_container.add_field("Channel", channel.mention, inline=True)
        resp_container.add_field("Title", title or "📌 Pinned Notice", inline=True)

        await interaction.followup.send(embed=resp_container.to_embed(), ephemeral=True)

    @sticky_group.command(name="remove", description="Remove the sticky message from a channel")
    @app_commands.describe(channel="The channel to remove the sticky notice from")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_remove(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Remove and delete existing sticky notice."""
        await interaction.response.defer(ephemeral=True)

        sticky_data = self.bot.sticky_mgr.get_sticky(channel.id)
        if not sticky_data:
            await interaction.followup.send(f"There is no active sticky message in {channel.mention}.", ephemeral=True)
            return

        # Delete existing message if present
        old_msg_id = sticky_data.get("last_message_id")
        if old_msg_id:
            try:
                old_msg = await channel.fetch_message(old_msg_id)
                await old_msg.delete()
            except Exception:
                pass

        await self.bot.sticky_mgr.remove_sticky(channel.id)
        await interaction.followup.send(
            f"**Sticky Removed**: Sticky message has been completely deactivated and deleted from {channel.mention}.",
            ephemeral=True,
        )

    @sticky_group.command(name="list", description="List all active sticky notices in this server")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_list(self, interaction: discord.Interaction) -> None:
        """Display all active stickies in current guild."""
        if not interaction.guild:
            return

        stickies = self.bot.sticky_mgr.get_guild_stickies(interaction.guild.id)
        if not stickies:
            await interaction.response.send_message("No active sticky messages configured in this server.", ephemeral=True)
            return

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Active Server Sticky Notices ({len(stickies)})\n"
                f"> Below are the channels currently configured with auto-pinned messages:"
            )
        )
        container.add_separator(divider=True)

        for cid, data in stickies:
            status = "Active" if data.get("is_enabled") else "Paused"
            title = data.get("embed_title") or "Notice"
            snippet = data["content"][:60] + "..." if len(data["content"]) > 60 else data["content"]
            container.add_field(
                f"<#{cid}> • {title}",
                f"**Status**: {status}\n**Preview**: {snippet}",
                inline=False,
            )

        await interaction.response.send_message(embed=container.to_embed(), ephemeral=True)

    @sticky_group.command(name="toggle", description="Pause or resume the sticky message in a channel")
    @app_commands.describe(channel="The channel to toggle")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def sticky_toggle(self, interaction: discord.Interaction, channel: discord.TextChannel) -> None:
        """Pause or unpause sticky updates."""
        if not self.bot.sticky_mgr.has_sticky(channel.id) and not self.bot.sticky_mgr.get_sticky(channel.id):
            await interaction.response.send_message(f"No sticky message configured in {channel.mention}.", ephemeral=True)
            return

        new_status = await self.bot.sticky_mgr.toggle_sticky(channel.id)
        status_word = "Resumed (Active)" if new_status else "Paused (Inactive)"
        await interaction.response.send_message(
            f"**Sticky Status**: Notice in {channel.mention} is now **{status_word}**.",
            ephemeral=True,
        )


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Sticky(bot))
