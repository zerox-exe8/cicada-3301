"""
Kyro Discord Bot - Core Greetings & Introduction Cards
Dedicated module for generating and dispatching clean Discord Components V2
containers for bot mentions (@Kyro) and server invite welcomes (on_guild_join).
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Optional

import discord

from src.core.config import Config
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Greetings")


async def send_bot_mention_card(bot: KyroBot, message: discord.Message) -> None:
    """Send the clean introduction container when Kyro is mentioned."""
    current_prefix = bot.guild_mgr.get_prefix(message.guild.id if message.guild else None)
    ws_ping = round(bot.latency * 1000) if (bot.latency and not math.isnan(bot.latency)) else 0
    dot = bot.custom_emojis.get("heart_dot", "•")

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**Hey, I'm {Config.BOT_NAME}**\n"
            f"> Built for our community — keeping your server safe, active, and effortlessly connected."
        )
    )
    container.add_separator(divider=True)
    container.add_text(
        f"{dot} **Prefix:** `{current_prefix}` | **Slash:** `/`\n"
        f"{dot} **Latency:** `{ws_ping}ms` | **Status:** `Ready`\n"
        f"{dot} **Quick Start:** `{current_prefix}help`"
    )
    container.add_separator(divider=True)
    container.add_text(f"-# **Requested by {message.author.display_name}**")
    container.add_separator(divider=True)

    buttons = []
    if Config.INVITE_URL:
        buttons.append({
            "type": 2,
            "style": 5,
            "label": "Invite Kyro",
            "url": Config.INVITE_URL,
        })
    if Config.SUPPORT_URL:
        buttons.append({
            "type": 2,
            "style": 5,
            "label": "Support Server",
            "url": Config.SUPPORT_URL,
        })
    if buttons:
        container.add_action_row(buttons)

    try:
        await send_container_response(message.channel, container)
    except Exception as e:
        logger.warning(f"Failed to send bot mention container in channel {message.channel.id}: {e}")


async def send_guild_welcome_card(bot: KyroBot, guild: discord.Guild) -> None:
    """Send the clean server introduction container when Kyro is invited to a new server."""
    logger.info(f"Joined new guild: {guild.name} ({guild.id}) with {getattr(guild, 'member_count', 0)} members.")

    # Find the best text channel to send the welcome card
    target_channel: Optional[discord.TextChannel] = None
    if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
        target_channel = guild.system_channel
    else:
        for ch in guild.text_channels:
            perms = ch.permissions_for(guild.me)
            if perms.send_messages and perms.embed_links:
                if ch.name.lower() in ["general", "chat", "main", "bot-commands", "commands", "lounge"]:
                    target_channel = ch
                    break
        if not target_channel:
            for ch in guild.text_channels:
                perms = ch.permissions_for(guild.me)
                if perms.send_messages and perms.embed_links:
                    target_channel = ch
                    break

    if not target_channel:
        logger.warning(f"No writable channel found to dispatch welcome card in {guild.name} ({guild.id}).")
        return

    prefix = bot.guild_mgr.get_prefix(guild.id)
    dot = bot.custom_emojis.get("heart_dot", "•")

    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"**Thanks for inviting {Config.BOT_NAME}!**\n"
            f"> Built for our community — keeping your server safe, active, and effortlessly connected."
        )
    )
    container.add_separator(divider=True)
    container.add_text(
        f"{dot} **Prefix:** `{prefix}` | **Slash:** `/`\n"
        f"{dot} **Quick Start:** `{prefix}help`"
    )
    container.add_separator(divider=True)
    container.add_text(f"-# Configured for {guild.name}")

    buttons = []
    if Config.INVITE_URL:
        buttons.append({
            "type": 2,
            "style": 5,
            "label": "Invite Kyro",
            "url": Config.INVITE_URL,
        })
    if Config.SUPPORT_URL:
        buttons.append({
            "type": 2,
            "style": 5,
            "label": "Support Server",
            "url": Config.SUPPORT_URL,
        })
    if buttons:
        container.add_action_row(buttons)

    try:
        await send_container_response(target_channel, container)
    except Exception as e:
        logger.warning(f"Failed to send welcome container in {guild.name}: {e}")
