from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Optional
import discord

from src.utils.containers import KyroContainer

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Antinuke.Helpers")

DANGEROUS_PERMISSIONS = {
    "administrator",
    "manage_guild",
    "manage_roles",
    "manage_channels",
    "ban_members",
    "kick_members",
    "mention_everyone",
    "manage_webhooks",
}


async def execute_punishment(
    bot: KyroBot,
    guild: discord.Guild,
    offender: discord.Member | discord.User,
    action_name: str,
    reason: str = "Kyro Antinuke Protocol",
) -> str:
    """
    Executes configured punishment on the unauthorized perpetrator.
    Step 1: Instantly strip all roles (neutralizes permissions in <50ms).
    Step 2: Ban or Kick according to guild configuration.
    """
    if offender.id == guild.owner_id:
        return "Owner Immune"

    if bot.user and offender.id == bot.user.id:
        return "Self Immune"

    punishment = bot.antinuke_mgr.get_punishment(guild.id)
    audit_reason = f"Kyro Antinuke | {action_name} — {reason}"

    member: discord.Member | None = guild.get_member(offender.id)

    # 1. Neutralize permissions by stripping roles if member is in guild
    if member and member.roles:
        try:
            # Keep @everyone role, strip all manageable custom roles
            strip_targets = [r for r in member.roles if not r.is_default() and r < guild.me.top_role]
            if strip_targets:
                await member.remove_roles(*strip_targets, reason="Kyro Antinuke: Instant Permission Neutralization")
                logger.info(f"Guild {guild.id}: Stripped {len(strip_targets)} role(s) from perpetrator {offender.id}")
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.warning(f"Guild {guild.id}: Could not strip roles from perpetrator {offender.id}: {e}")

    # 2. Execute Ban / Kick / Strip
    if punishment == "ban":
        try:
            await guild.ban(offender, reason=audit_reason, delete_message_seconds=0)
            return "Banned"
        except discord.Forbidden:
            logger.warning(f"Guild {guild.id}: Missing permissions to ban offender {offender.id}")
            return "Failed (Hierarchy / Permissions)"
        except Exception as e:
            logger.error(f"Guild {guild.id}: Error banning offender {offender.id}: {e}")
            return f"Failed ({e})"

    elif punishment == "kick":
        if member:
            try:
                await member.kick(reason=audit_reason)
                return "Kicked"
            except discord.Forbidden:
                return "Failed (Hierarchy / Permissions)"
            except Exception as e:
                return f"Failed ({e})"
        else:
            return "Offender not in guild"

    return "Roles Stripped"


async def restore_channel(guild: discord.Guild, cached_data: dict[str, Any]) -> discord.abc.GuildChannel | None:
    """Restore a deleted channel using its in-memory snapshot."""
    try:
        ch_type = cached_data.get("type")
        name = cached_data.get("name", "recovered-channel")
        category_id = cached_data.get("category_id")
        category = guild.get_channel(category_id) if category_id else None
        if not isinstance(category, discord.CategoryChannel):
            category = None

        overwrites = {}
        for target_id, (target_obj, ow) in cached_data.get("overwrites", {}).items():
            # Resolve target in guild if still present
            live_target = guild.get_role(target_id) or guild.get_member(target_id)
            if live_target:
                overwrites[live_target] = ow

        if ch_type == discord.ChannelType.text:
            return await guild.create_text_channel(
                name=name,
                category=category,
                topic=cached_data.get("topic"),
                nsfw=cached_data.get("nsfw", False),
                overwrites=overwrites,
                reason="Kyro Antinuke: Self-Healing Channel Recreation",
            )
        elif ch_type == discord.ChannelType.voice:
            return await guild.create_voice_channel(
                name=name,
                category=category,
                overwrites=overwrites,
                reason="Kyro Antinuke: Self-Healing Voice Channel Recreation",
            )
        elif ch_type == discord.ChannelType.category:
            return await guild.create_category(
                name=name,
                overwrites=overwrites,
                reason="Kyro Antinuke: Self-Healing Category Recreation",
            )
    except Exception as e:
        logger.error(f"Guild {guild.id}: Failed to restore channel: {e}")
    return None


async def restore_role(guild: discord.Guild, cached_data: dict[str, Any]) -> discord.Role | None:
    """Restore a deleted role using its in-memory snapshot."""
    try:
        return await guild.create_role(
            name=cached_data.get("name", "recovered-role"),
            permissions=cached_data.get("permissions", discord.Permissions.none()),
            color=cached_data.get("color", discord.Color.default()),
            hoist=cached_data.get("hoist", False),
            mentionable=cached_data.get("mentionable", False),
            reason="Kyro Antinuke: Self-Healing Role Recreation",
        )
    except Exception as e:
        logger.error(f"Guild {guild.id}: Failed to restore role: {e}")
    return None


async def restore_vanity(bot: KyroBot, guild: discord.Guild, original_vanity: str) -> bool:
    """Attempt to restore the server's legitimate vanity URL code."""
    if not original_vanity:
        return False
    try:
        # Direct HTTP PATCH to restore vanity
        route = discord.http.Route("PATCH", "/guilds/{guild_id}/vanity-url", guild_id=guild.id)
        await bot.http.request(route, json={"code": original_vanity})
        logger.info(f"Guild {guild.id}: Restored vanity URL to '{original_vanity}'")
        return True
    except Exception as e:
        logger.error(f"Guild {guild.id}: Failed to restore vanity code '{original_vanity}': {e}")
        return False


async def disarm_dangerous_permissions(role: discord.Role) -> bool:
    """Disarm administrative and dangerous permissions from a compromised role."""
    try:
        perms = role.permissions
        changes = {}
        for p in DANGEROUS_PERMISSIONS:
            if getattr(perms, p, False):
                changes[p] = False

        if changes:
            await role.edit(
                permissions=discord.Permissions(**{**dict(perms), **changes}),
                reason="Kyro Antinuke: Disarming Unauthorized Dangerous Permissions",
            )
            return True
    except Exception as e:
        logger.error(f"Guild {role.guild.id}: Failed to disarm permissions from role {role.id}: {e}")
    return False


async def dispatch_antinuke_log(
    bot: KyroBot,
    guild: discord.Guild,
    action: str,
    offender: discord.Member | discord.User,
    punishment_result: str,
    recovery_status: str,
    extra: Optional[str] = None,
) -> None:
    """
    Format and send an incident report card to the configured log channel,
    and trigger a critical DM alert to the server owner when appropriate.
    """
    log_channel = bot.antinuke_mgr.get_log_channel(guild)
    if not log_channel:
        # Fallback to general/mod log channel if antinuke channel is unconfigured
        log_channel = bot.log_mgr.get_log_channel(guild, "mod")

    e_reg = getattr(bot, "custom_emojis", {})
    dot = e_reg.get("heart_dot", "-")
    shield = e_reg.get("icon_shield", "")
    badge_str = f"{shield} " if shield else ""

    container = KyroContainer(accent_color=None)
    container.add_section(content=f"**Security Alert — {action}**")
    container.add_separator(divider=True)

    items = [
        f"• **Perpetrator:** **{offender}** `「{offender.id}」`",
        f"• **Punishment:** `{punishment_result}`",
        f"• **Mitigation:** `{recovery_status}`",
    ]

    if extra:
        items.append(f"• **Details:** {extra}")

    container.add_text("\n".join(items))

    # Send to log channel
    if log_channel:
        try:
            from src.utils.containers import build_container_payload
            payload = build_container_payload(container)
            await log_channel.send(**payload)
        except Exception as e:
            logger.warning(f"Guild {guild.id}: Could not send antinuke log to channel {log_channel.id}: {e}")

    # Critical DM Alert to Server Owner
    critical_actions = ["Vanity Hijack", "Everyone Disarm", "Mass Ban Attack", "Mass Channel Delete", "Mass Role Delete"]
    if any(c in action for c in critical_actions):
        try:
            owner = guild.owner or await guild.fetch_member(guild.owner_id)
            if owner:
                from src.utils.containers import build_container_payload
                dm_container = KyroContainer(accent_color=None)
                dm_container.add_section(
                    content=f"**Critical Security Incident in {guild.name}**"
                )
                dm_container.add_separator(divider=True)
                dm_container.add_text("\n".join(items))
                payload = build_container_payload(dm_container)
                await owner.send(**payload)
        except Exception as e:
            logger.debug(f"Notice sending owner DM alert: {e}")
