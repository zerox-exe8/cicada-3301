"""
Kyro Discord Bot - Server Auto-Events (Welcome, Leave, Boost) Cog
Binds saved named Components V2 container cards and outer ping messages with dynamic variables
to member join, member leave, and server boost events.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional, Dict
import discord
from discord import app_commands
from discord.ext import commands

from src.core.bot import KyroBot
from src.core.context import CustomContext
from src.cogs.moderation._helpers import resolve_role
from src.cogs.utility.embed_builder import ContainerDraft
from src.utils.containers import KyroContainer, send_container_response
from src.utils.placeholders import resolve_placeholders

logger = logging.getLogger("Kyro.Events")


class AutoEvents(commands.Cog):
    """Automated Welcome, Farewell/Leave, and Boost Container Dispatcher."""
    category: str = "Welcomer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Dynamically attach embed announce command to embed group so ?embed announce works."""
        embed_group = self.bot.get_command("embed")
        if embed_group and isinstance(embed_group, commands.Group):
            if not embed_group.get_command("announce"):
                cmd = self.embed_announce_cmd.copy()
                cmd.cog = self
                embed_group.add_command(cmd)

    async def cog_unload(self) -> None:
        """Detach dynamic announce command on cog unload."""
        embed_group = self.bot.get_command("embed")
        if embed_group and isinstance(embed_group, commands.Group):
            cmd = embed_group.get_command("announce")
            if cmd and getattr(cmd, "cog", None) == self:
                embed_group.remove_command("announce")

    async def _send_event_card(
        self,
        event_type: str,
        guild: discord.Guild,
        member: discord.Member | discord.User,
        extra: dict[str, Any] | None = None,
        test_channel: discord.TextChannel | discord.Thread | None = None,
    ) -> tuple[bool, str | None]:
        """Helper to render and dispatch an event container card + outer message."""
        config = await self.bot.event_mgr.get_event_config(guild.id, event_type)
        if not config and not test_channel:
            logger.warning(f"No config found for {event_type} in {guild.name}")
            return False, "No event configuration found. Use `set` command first."

        if not test_channel and not config.get("is_enabled", True):
            return False, "Event system is currently disabled for this server."

        channel_id = test_channel.id if test_channel else config.get("channel_id")
        if not channel_id:
            logger.warning(f"No channel_id found for {event_type} in {guild.name}")
            return False, "No target channel is configured."

        channel = test_channel
        if not channel:
            channel = guild.get_channel(channel_id) or self.bot.get_channel(channel_id)
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception as e:
                    logger.error(f"Failed to fetch channel {channel_id} for {event_type}: {e}")
                    return False, f"Could not find or fetch target channel: {e}"

        if not channel or not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logger.warning(f"Channel {channel_id} is not a TextChannel/Thread in {guild.name}")
            return False, "Target channel is not a valid text channel or thread."

        # Permission verification
        if isinstance(channel, discord.TextChannel):
            bot_member = guild.me
            perms = channel.permissions_for(bot_member)
            if not perms.view_channel:
                return False, f"Bot is missing `View Channel` permission in {channel.mention}."
            if not perms.send_messages:
                return False, f"Bot is missing `Send Messages` permission in {channel.mention}."
            if not perms.embed_links:
                return False, f"Bot is missing `Embed Links` permission in {channel.mention}."
            if not perms.manage_webhooks:
                return False, f"Bot requires `Manage Webhooks` permission in {channel.mention} to render Discord Components V2 Container Cards."

        embed_name = config.get("embed_name") if config else None
        msg_template = config.get("message_content") if config else None

        # resolve Outer Message Content (Ping message)
        outer_content = None
        if msg_template:
            if msg_template.strip().lower() in ["none", "no_ping", "silent"]:
                outer_content = None
            else:
                outer_content = resolve_placeholders(msg_template, user=member, guild=guild, extra=extra)

        # build Container from saved embed or fallback container
        container = None
        if embed_name:
            template_data = await self.bot.embed_mgr.get_template(guild.id, embed_name)
            if template_data:
                draft = ContainerDraft.from_dict(template_data)
                avatar_url = str(self.bot.user.display_avatar.url) if self.bot and self.bot.user else ""
                container = draft.to_container(
                    user=member,
                    guild=guild,
                    channel=channel,
                    bot=self.bot,
                    default_avatar=avatar_url,
                )
            else:
                logger.warning(f"Bound template '{embed_name}' not found for {event_type} in guild {guild.id}")

        if not container:
            # Fallback container
            container = KyroContainer(accent_color=None)
            if event_type == "welcome":
                container.add_section(
                    content=(
                        f"**Welcome to {guild.name}!**\n"
                        f"> Hey {member.mention}, welcome to the server!\n"
                        f"> You are our **{guild.member_count:,}th** member."
                    )
                )
            elif event_type == "leave":
                container.add_section(
                    content=(
                        f"**Goodbye!**\n"
                        f"> **{member.name}** has left **{guild.name}**.\n"
                        f"> We now have **{guild.member_count:,}** members."
                    )
                )
            elif event_type == "boost":
                container.add_section(
                    content=(
                        f"**Server Boost!**\n"
                        f"> Thank you {member.mention} for boosting **{guild.name}**!\n"
                        f"> We are now at **{guild.premium_subscription_count}** boosts ({guild.premium_tier})."
                    )
                )
            container.add_separator(divider=True)
            container.add_text(f"-# {guild.name}")

        try:
            target_msg = await send_container_response(
                channel,
                container,
                content=outer_content,
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )
            # If template has interactive modules, register card for page switching
            msg_id = None
            if isinstance(target_msg, dict) and "id" in target_msg:
                msg_id = int(target_msg["id"])
            elif hasattr(target_msg, "id"):
                msg_id = int(target_msg.id)

            if container and embed_name and msg_id:
                draft_data = await self.bot.embed_mgr.get_template(guild.id, embed_name)
                if draft_data:
                    await self.bot.embed_mgr.record_interactive_card(
                        guild_id=guild.id,
                        message_id=msg_id,
                        template_name=embed_name,
                        payload=draft_data,
                    )
            return True, None
        except discord.Forbidden as e:
            logger.error(f"Missing permissions to send {event_type} in {channel.name}: {e}")
            return False, f"Permission Denied (403): Bot lacks permissions to send in {channel.mention}. Please grant `Send Messages` and `Embed Links` in channel settings."
        except Exception as e:
            logger.error(f"Failed to dispatch {event_type} card in {guild.name}: {e}", exc_info=e)
            return False, f"Error sending message: {e}"

    async def _get_autorole_ids(self, guild_id: int, target: str = "human") -> list[int]:
        """Fetch list of configured autorole IDs with L1 cache and database fallback ('human' or 'bot')."""
        cached = self.bot.cache.get_autorole_list(guild_id, target=target)
        if cached is not None:
            return list(cached)

        try:
            row = await self.bot.db.fetch_one(
                "SELECT role_id, human_role_id, bot_role_id, human_role_ids, bot_role_ids FROM guild_autoroles WHERE guild_id = ?;",
                guild_id,
            )
        except Exception:
            try:
                row = await self.bot.db.fetch_one(
                    "SELECT role_id, human_role_id, bot_role_id FROM guild_autoroles WHERE guild_id = ?;",
                    guild_id,
                )
            except Exception:
                row = await self.bot.db.fetch_one(
                    "SELECT role_id FROM guild_autoroles WHERE guild_id = ?;",
                    guild_id,
                )

        if not row:
            self.bot.cache.set_autorole_list(guild_id, [], target="human")
            self.bot.cache.set_autorole_list(guild_id, [], target="bot")
            return []

        # Parse humans
        human_ids: list[int] = []
        raw_human_csv = row.get("human_role_ids")
        if raw_human_csv:
            human_ids = [int(x.strip()) for x in str(raw_human_csv).split(",") if x.strip().isdigit()]
        elif row.get("human_role_id"):
            human_ids = [int(row["human_role_id"])]
        elif row.get("role_id"):
            human_ids = [int(row["role_id"])]

        # Parse bots
        bot_ids: list[int] = []
        raw_bot_csv = row.get("bot_role_ids")
        if raw_bot_csv:
            bot_ids = [int(x.strip()) for x in str(raw_bot_csv).split(",") if x.strip().isdigit()]
        elif row.get("bot_role_id"):
            bot_ids = [int(row["bot_role_id"])]

        self.bot.cache.set_autorole_list(guild_id, human_ids, target="human")
        self.bot.cache.set_autorole_list(guild_id, bot_ids, target="bot")

        return list(bot_ids if target == "bot" else human_ids)

    async def _get_autorole_id(self, guild_id: int, target: str = "human") -> int | None:
        """Fetch primary autorole ID (single role backward compatibility)."""
        roles = await self._get_autorole_ids(guild_id, target=target)
        return roles[0] if roles else None

    async def _set_autorole_ids(self, guild_id: int, role_ids: list[int], target: str = "human") -> None:
        """Persist autorole IDs to database and update L1 cache."""
        clean_ids = [r for r in role_ids if r and r > 0]
        csv_ids = ",".join(str(r) for r in clean_ids)
        primary_id = clean_ids[0] if clean_ids else None

        if target == "bot":
            await self.bot.db.execute(
                """
                INSERT INTO guild_autoroles (guild_id, bot_role_id, bot_role_ids)
                VALUES (?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    bot_role_id = EXCLUDED.bot_role_id,
                    bot_role_ids = EXCLUDED.bot_role_ids,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                guild_id,
                primary_id,
                csv_ids,
            )
            self.bot.cache.set_autorole_list(guild_id, clean_ids, target="bot")
        else:
            await self.bot.db.execute(
                """
                INSERT INTO guild_autoroles (guild_id, human_role_id, role_id, human_role_ids)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (guild_id) DO UPDATE SET
                    human_role_id = EXCLUDED.human_role_id,
                    role_id = EXCLUDED.role_id,
                    human_role_ids = EXCLUDED.human_role_ids,
                    updated_at = CURRENT_TIMESTAMP;
                """,
                guild_id,
                primary_id,
                primary_id,
                csv_ids,
            )
            self.bot.cache.set_autorole_list(guild_id, clean_ids, target="human")

    # ─── Event Listeners ─────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Handle welcome greeting and auto-role on member join (separate human and bot roles)."""
        # Handle Auto-Role assignment (for both humans and bots)
        target_type = "bot" if member.bot else "human"
        role_ids = await self._get_autorole_ids(member.guild.id, target=target_type)
        if role_ids and member.guild.me.guild_permissions.manage_roles:
            roles_to_add: list[discord.Role] = []
            for r_id in role_ids:
                role = member.guild.get_role(r_id)
                if role and member.guild.me.top_role > role:
                    roles_to_add.append(role)
            if roles_to_add:
                try:
                    await member.add_roles(*roles_to_add, reason=f"Kyro Auto-Role System ({target_type.capitalize()})")
                    role_names = ", ".join(f"@{r.name}" for r in roles_to_add)
                    logger.info(f"Assigned {target_type} autorole(s) [{role_names}] to {member} in {member.guild.name}")
                except Exception as e:
                    logger.warning(f"Failed to assign {target_type} autorole(s) in {member.guild.name}: {e}")

        # Welcome greetings and DMs are only for real human members
        if member.bot:
            return

        await self._send_event_card("welcome", member.guild, member)

        # Handle DM Welcome if enabled
        config = await self.bot.event_mgr.get_event_config(member.guild.id, "welcome")
        if config and config.get("dm_enabled") and config.get("dm_embed_name"):
            dm_name = config["dm_embed_name"]
            dm_data = await self.bot.embed_mgr.get_template(member.guild.id, dm_name)
            if dm_data:
                try:
                    draft = ContainerDraft.from_dict(dm_data)
                    avatar_url = str(self.bot.user.display_avatar.url) if self.bot and self.bot.user else ""
                    dm_container = draft.to_container(
                        user=member,
                        guild=member.guild,
                        bot=self.bot,
                        default_avatar=avatar_url,
                    )
                    await send_container_response(member, dm_container)
                except Exception:
                    pass  # User DMs closed

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Handle farewell on member leave."""
        if member.bot:
            return
        await self._send_event_card("leave", member.guild, member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        """Handle server boost event."""
        if not before.premium_since and after.premium_since:
            extra = {
                "booster": after.mention,
                "boost_count": getattr(after.guild, "premium_subscription_count", 0),
                "boost_tier": f"Level {getattr(after.guild, 'premium_tier', 0)}",
            }
            await self._send_event_card("boost", after.guild, after, extra=extra)

    # ─── Auto-Role Command Group ─────────────────────────────────────────────

    def _validate_autorole(self, ctx: CustomContext, role: discord.Role) -> str | None:
        """Validate if a role can be safely configured as an auto-role."""
        if role.is_default() or role.managed:
            return "Cannot set `@everyone` or a bot-managed integration role as auto-role."
        if role >= ctx.guild.me.top_role:
            return f"The role {role.mention} is higher than or equal to my highest role. Please move my role above {role.mention} in Server Settings."
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            return f"You cannot set {role.mention} because it is higher than or equal to your highest role."
        return None

    @commands.hybrid_group(
        name="autorole",
        aliases=["joinrole"],
        description="Configure automatic role assignment for humans and bots.",
        fallback="status",
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole_group(self, ctx: CustomContext) -> None:
        """View auto-role commands."""
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "❤")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Auto-Role Commands**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} `{prefix}autorole human <role> | remove`\n"
            f"{dot} `{prefix}autorole bot <role> | remove`\n"
            f"{dot} `{prefix}autorole show`\n"
            f"{dot} `{prefix}autorole reset`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    # ─── Auto-Role Shared Handlers ───────────────────────────────────────────

    async def _handle_autorole_add(
        self,
        ctx: CustomContext,
        target: str,
        role: discord.Role,
    ) -> None:
        """Shared logic for adding an autorole with duplicate check and hierarchy validation."""
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "❤")

        err = self._validate_autorole(ctx, role)
        if err:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Auto-Role Error**")
            container.add_separator(divider=True)
            container.add_text(f"> {err}")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        current_ids = await self._get_autorole_ids(ctx.guild.id, target=target)
        if role.id in current_ids:
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**{'Human' if target == 'human' else 'Bot'} Auto-Role**")
            container.add_separator(divider=True)
            container.add_text(f"> {role.mention} is already configured as the {target} auto-role.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        current_ids.append(role.id)
        await self._set_autorole_ids(ctx.guild.id, current_ids, target=target)

        container = KyroContainer(accent_color=None)
        container.add_section(content=f"**{'Human' if target == 'human' else 'Bot'} Auto-Role Command**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Target:** `{'Humans Only' if target == 'human' else 'Bots Only'}`\n"
            f"{dot} **Assigned Role:** @{role.name} `「{role.id}」`\n"
            f"{dot} **Moderator:** **{ctx.author.display_name}**"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    async def _handle_autorole_remove(
        self,
        ctx: CustomContext,
        target: str,
        role: Optional[discord.Role] = None,
    ) -> None:
        """Shared logic for removing a specific autorole or clearing target autoroles."""
        current_ids = await self._get_autorole_ids(ctx.guild.id, target=target)
        target_name = "human" if target == "human" else "bot"

        if role:
            if role.id not in current_ids:
                container = KyroContainer(accent_color=None)
                container.add_section(content=f"**{'Human' if target == 'human' else 'Bot'} Auto-Role**")
                container.add_separator(divider=True)
                container.add_text(f"> {role.mention} is not in the {target_name} auto-role list.")
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container)
                return

            current_ids.remove(role.id)
            await self._set_autorole_ids(ctx.guild.id, current_ids, target=target)

            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**{'Human' if target == 'human' else 'Bot'} Auto-Role Removed**")
            container.add_separator(divider=True)
            container.add_text(f"> @{role.name} `「{role.id}」` has been removed from {target_name} auto-roles.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
        else:
            await self._set_autorole_ids(ctx.guild.id, [], target=target)
            container = KyroContainer(accent_color=None)
            container.add_section(content=f"**{'Human' if target == 'human' else 'Bot'} Auto-Role Disabled**")
            container.add_separator(divider=True)
            container.add_text(f"> Automatic role assignment for {'human members' if target == 'human' else 'bot accounts'} has been deactivated.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)

    @autorole_group.command(
        name="show",
        aliases=["config", "status", "list"],
        description="View current auto-role configuration for this server.",
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole_show(self, ctx: CustomContext) -> None:
        """View configured human and bot auto-roles."""
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "❤")

        human_role_ids = await self._get_autorole_ids(ctx.guild.id, target="human")
        bot_role_ids = await self._get_autorole_ids(ctx.guild.id, target="bot")

        human_roles = [ctx.guild.get_role(r) for r in human_role_ids if ctx.guild.get_role(r)]
        bot_roles = [ctx.guild.get_role(r) for r in bot_role_ids if ctx.guild.get_role(r)]

        human_str = ", ".join(f"@{r.name} `「{r.id}」`" for r in human_roles) if human_roles else "`Disabled`"
        bot_str = ", ".join(f"@{r.name} `「{r.id}」`" for r in bot_roles) if bot_roles else "`Disabled`"

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Auto-Role Show**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Human Role:** {human_str}\n"
            f"{dot} **Bot Role:** {bot_str}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @autorole_group.command(
        name="reset",
        aliases=["clear"],
        description="Disable all auto-roles (humans and bots).",
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole_reset(self, ctx: CustomContext) -> None:
        """Disable all auto-roles."""
        await self.bot.db.execute(
            "UPDATE guild_autoroles SET human_role_id = NULL, bot_role_id = NULL, role_id = NULL, human_role_ids = '', bot_role_ids = '' WHERE guild_id = ?;",
            ctx.guild.id,
        )
        self.bot.cache.set_autorole_list(ctx.guild.id, [], target="human")
        self.bot.cache.set_autorole_list(ctx.guild.id, [], target="bot")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Auto-Role Reset**")
        container.add_separator(divider=True)
        container.add_text("> All automatic role assignments have been deactivated.")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @autorole_group.command(
        name="add",
        description="Add an auto-role for humans or bots.",
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole_add_cmd(
        self,
        ctx: CustomContext,
        target_or_role: str,
        *,
        role_arg: Optional[str] = None,
    ) -> None:
        """Add an auto-role for humans (default) or bots."""
        lowered = target_or_role.lower()
        if lowered in ("bot", "bots"):
            target = "bot"
            query = role_arg
        elif lowered in ("human", "humans", "user", "users"):
            target = "human"
            query = role_arg
        else:
            target = "human"
            query = f"{target_or_role} {role_arg}".strip() if role_arg else target_or_role

        if not query:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Auto-Role Error**")
            container.add_separator(divider=True)
            container.add_text("> Please specify a role to add (e.g. `?autorole add @role` or `?autorole add bot @role`).")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        role = resolve_role(ctx.guild, query)
        if not role:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Auto-Role Error**")
            container.add_separator(divider=True)
            container.add_text(f"> Could not find role `{query}` in this server.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        await self._handle_autorole_add(ctx, target, role)

    @autorole_group.command(
        name="remove",
        aliases=["del", "delete"],
        description="Remove a configured auto-role or disable it.",
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole_remove_cmd(
        self,
        ctx: CustomContext,
        target_or_role: Optional[str] = None,
        *,
        role_arg: Optional[str] = None,
    ) -> None:
        """Remove a configured auto-role."""
        if not target_or_role:
            await self.autorole_group(ctx)
            return

        lowered = target_or_role.lower()
        if lowered in ("bot", "bots"):
            target = "bot"
            role = resolve_role(ctx.guild, role_arg) if role_arg else None
            await self._handle_autorole_remove(ctx, target, role)
        elif lowered in ("human", "humans", "user", "users"):
            target = "human"
            role = resolve_role(ctx.guild, role_arg) if role_arg else None
            await self._handle_autorole_remove(ctx, target, role)
        else:
            query = f"{target_or_role} {role_arg}".strip() if role_arg else target_or_role
            role = resolve_role(ctx.guild, query)
            if not role:
                container = KyroContainer(accent_color=None)
                container.add_section(content="**Auto-Role Error**")
                container.add_separator(divider=True)
                container.add_text(f"> Could not find role `{query}` in this server.")
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container)
                return

            human_ids = await self._get_autorole_ids(ctx.guild.id, target="human")
            bot_ids = await self._get_autorole_ids(ctx.guild.id, target="bot")
            if role.id in human_ids:
                await self._handle_autorole_remove(ctx, "human", role)
            elif role.id in bot_ids:
                await self._handle_autorole_remove(ctx, "bot", role)
            else:
                container = KyroContainer(accent_color=None)
                container.add_section(content="**Auto-Role Error**")
                container.add_separator(divider=True)
                container.add_text(f"> {role.mention} is not configured as an auto-role.")
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container)

    # ─── Auto-Role Human Subgroup ────────────────────────────────────────────

    @autorole_group.group(
        name="human",
        aliases=["humans", "user", "users"],
        invoke_without_command=True,
        description="Configure automatic role assignment for real human members.",
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole_human(self, ctx: CustomContext, *, role_input: Optional[str] = None) -> None:
        """Set or view auto-role for human members."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "❤")

        if role_input is None:
            human_role_ids = await self._get_autorole_ids(ctx.guild.id, target="human")
            roles = [ctx.guild.get_role(r) for r in human_role_ids if ctx.guild.get_role(r)]
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Human Auto-Role Status**")
            container.add_separator(divider=True)
            if roles:
                role_str = ", ".join(f"@{r.name} `「{r.id}」`" for r in roles)
                container.add_text(
                    f"{dot} **Current Role:** {role_str}\n"
                    f"{dot} **To Add:** `{prefix}autorole human <role>`\n"
                    f"{dot} **To Disable:** `{prefix}autorole human remove`"
                )
            else:
                container.add_text(
                    f"{dot} **Status:** `Disabled`\n"
                    f"{dot} **To Enable:** `{prefix}autorole human <role>`"
                )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        clean_query = role_input.strip()
        if clean_query.lower().startswith("add "):
            clean_query = clean_query[4:].strip()
        elif clean_query.lower().startswith("set "):
            clean_query = clean_query[4:].strip()

        role = resolve_role(ctx.guild, clean_query)
        if not role:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Auto-Role Error**")
            container.add_separator(divider=True)
            container.add_text(f"> Could not find role `{clean_query}` in this server.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        await self._handle_autorole_add(ctx, "human", role)

    @autorole_human.command(
        name="add",
        description="Add an auto-role for human members.",
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole_human_add(self, ctx: CustomContext, *, role_input: str) -> None:
        """Add an auto-role for human members."""
        role = resolve_role(ctx.guild, role_input)
        if not role:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Auto-Role Error**")
            container.add_separator(divider=True)
            container.add_text(f"> Could not find role `{role_input}` in this server.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return
        await self._handle_autorole_add(ctx, "human", role)

    @autorole_human.command(
        name="remove",
        aliases=["disable", "reset", "del"],
        description="Disable auto-role for human members or remove a specific role.",
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole_human_remove(self, ctx: CustomContext, *, role_input: Optional[str] = None) -> None:
        """Disable human auto-role or remove a specific role."""
        role = resolve_role(ctx.guild, role_input) if role_input else None
        await self._handle_autorole_remove(ctx, "human", role)

    # ─── Auto-Role Bot Subgroup ──────────────────────────────────────────────

    @autorole_group.group(
        name="bot",
        aliases=["bots"],
        invoke_without_command=True,
        description="Configure automatic role assignment for invited bot accounts.",
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole_bot(self, ctx: CustomContext, *, role_input: Optional[str] = None) -> None:
        """Set or view auto-role for bot accounts."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "❤")

        if role_input is None:
            bot_role_ids = await self._get_autorole_ids(ctx.guild.id, target="bot")
            roles = [ctx.guild.get_role(r) for r in bot_role_ids if ctx.guild.get_role(r)]
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Bot Auto-Role Status**")
            container.add_separator(divider=True)
            if roles:
                role_str = ", ".join(f"@{r.name} `「{r.id}」`" for r in roles)
                container.add_text(
                    f"{dot} **Current Role:** {role_str}\n"
                    f"{dot} **To Add:** `{prefix}autorole bot <role>`\n"
                    f"{dot} **To Disable:** `{prefix}autorole bot remove`"
                )
            else:
                container.add_text(
                    f"{dot} **Status:** `Disabled`\n"
                    f"{dot} **To Enable:** `{prefix}autorole bot <role>`"
                )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        clean_query = role_input.strip()
        if clean_query.lower().startswith("add "):
            clean_query = clean_query[4:].strip()
        elif clean_query.lower().startswith("set "):
            clean_query = clean_query[4:].strip()

        role = resolve_role(ctx.guild, clean_query)
        if not role:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Auto-Role Error**")
            container.add_separator(divider=True)
            container.add_text(f"> Could not find role `{clean_query}` in this server.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        await self._handle_autorole_add(ctx, "bot", role)

    @autorole_bot.command(
        name="add",
        description="Add an auto-role for bot accounts.",
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole_bot_add(self, ctx: CustomContext, *, role_input: str) -> None:
        """Add an auto-role for bot accounts."""
        role = resolve_role(ctx.guild, role_input)
        if not role:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Auto-Role Error**")
            container.add_separator(divider=True)
            container.add_text(f"> Could not find role `{role_input}` in this server.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return
        await self._handle_autorole_add(ctx, "bot", role)

    @autorole_bot.command(
        name="remove",
        aliases=["disable", "reset", "del"],
        description="Disable auto-role for bot accounts or remove a specific role.",
    )
    @commands.has_permissions(manage_roles=True)
    async def autorole_bot_remove(self, ctx: CustomContext, *, role_input: Optional[str] = None) -> None:
        """Disable bot auto-role or remove a specific role."""
        role = resolve_role(ctx.guild, role_input) if role_input else None
        await self._handle_autorole_remove(ctx, "bot", role)

    # ─── Welcome Command Group ───────────────────────────────────────────────

    @commands.hybrid_group(
        name="welcome",
        aliases=["greet"],
        description="Configure automated server welcome container cards.",
        fallback="status",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_group(self, ctx: CustomContext) -> None:
        """View the current welcome configuration dashboard."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "welcome")

        ch_id = config.get("channel_id") if config else None
        channel = ctx.guild.get_channel(ch_id) if ch_id else None
        ch_str = channel.mention if channel else "`Not Configured`"
        emb_str = f"`{config.get('embed_name')}`" if (config and config.get("embed_name")) else "`Default Card`"
        msg_str = f"`{config.get('message_content')}`" if (config and config.get("message_content")) else "`None (Embed Only)`"
        status_str = "`Enabled`" if (config and config.get("is_enabled", True)) else "`Disabled`"
        dm_str = f"`{config.get('dm_embed_name')}`" if (config and config.get("dm_enabled")) else "`Disabled`"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Welcome Configuration**\n"
                f"> Manage automated welcome messages & container cards for **{ctx.guild.name}**."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"**Channel:** {ch_str} | **Status:** {status_str}\n"
            f"**Bound Embed:** {emb_str} | **DM Welcome:** {dm_str}\n"
            f"**Outer Ping Text:** {msg_str}"
        )
        container.add_separator(divider=True)
        container.add_text(
            f"`{prefix}welcome set #channel {{user}} <embed_name>`\n"
            f"`{prefix}welcome test` , `{prefix}welcome toggle` , `{prefix}welcome reset`\n"
            f"`{prefix}embed announce #channel <embed_name> [@everyone]`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @welcome_group.command(
        name="set",
        description="Bind channel, outer text, and custom embed for welcome messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_set(
        self,
        ctx: CustomContext,
        *,
        args: str = "",
    ) -> None:
        """Bind channel, message content, and named embed template."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        raw_text = args.strip()

        target_channel = None
        if ctx.message.channel_mentions:
            target_channel = ctx.message.channel_mentions[0]
            raw_text = re.sub(rf"<#{target_channel.id}>", "", raw_text).strip()
        else:
            words = raw_text.split()
            if words:
                first_w = words[0].lstrip("#")
                if first_w.isdigit():
                    ch = ctx.guild.get_channel(int(first_w))
                    if isinstance(ch, discord.TextChannel):
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()
                if not target_channel:
                    ch = discord.utils.get(ctx.guild.text_channels, name=first_w.lower())
                    if ch:
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()

        if not target_channel:
            target_channel = ctx.channel

        # Convert any accidental literal mentions of command invoker or bot into dynamic {user} placeholder
        if ctx.author:
            raw_text = re.sub(rf"<@!?{ctx.author.id}>", "{user}", raw_text)
        if self.bot.user:
            raw_text = re.sub(rf"<@!?{self.bot.user.id}>", "{user}", raw_text)

        words = raw_text.split()
        embed_name = None
        message_content = None

        if len(words) == 1:
            clean_word = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
            template = await self.bot.embed_mgr.get_template(ctx.guild.id, clean_word)
            if template:
                embed_name = clean_word
            else:
                message_content = raw_text
        elif len(words) > 1:
            last_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[-1].lower())
            template_last = await self.bot.embed_mgr.get_template(ctx.guild.id, last_clean)
            if template_last:
                embed_name = last_clean
                message_content = raw_text[:-len(words[-1])].strip() or None
            else:
                first_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
                template_first = await self.bot.embed_mgr.get_template(ctx.guild.id, first_clean)
                if template_first:
                    embed_name = first_clean
                    message_content = raw_text[len(words[0]):].strip() or None
                else:
                    message_content = raw_text

        success = await self.bot.event_mgr.save_event_config(
            guild_id=ctx.guild.id,
            event_type="welcome",
            channel_id=target_channel.id,
            embed_name=embed_name,
            message_content=message_content,
            is_enabled=True,
        )

        if not success:
            await ctx.send_error("Failed to save welcome configuration. Please try again.")
            return

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Welcome System Configured**\n"
                f"> New members will be greeted in {target_channel.mention}."
            )
        )
        container.add_separator(divider=True)
        emb_display = f"`{embed_name}`" if embed_name else "`Default Card`"
        msg_display = f"`{message_content}`" if message_content else "`None (Embed Only)`"
        container.add_text(
            f"**Channel:** {target_channel.mention}\n"
            f"**Bound Embed:** {emb_display}\n"
            f"**Outer Text:** {msg_display}\n\n"
            f"> Run `{prefix}welcome test` to preview the message live!"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @welcome_group.command(
        name="test",
        description="Test the current welcome message and embed live in channel.",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_test(self, ctx: CustomContext) -> None:
        """Send a test welcome card."""
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "welcome")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not config or not config.get("channel_id"):
            await ctx.send_warning(f"Welcome is not configured yet! Use `{prefix}welcome set #channel {{user}} <embed_name>`.")
            return

        ch_id = config["channel_id"]
        target_ch = ctx.guild.get_channel(ch_id) or self.bot.get_channel(ch_id)
        if not target_ch:
            try:
                target_ch = await self.bot.fetch_channel(ch_id)
            except Exception:
                target_ch = None

        if not target_ch or not isinstance(target_ch, (discord.TextChannel, discord.Thread)):
            await ctx.send_error(f"Configured welcome channel not found. Please set a new channel with `{prefix}welcome set`.")
            return

        success, err = await self._send_event_card("welcome", ctx.guild, ctx.author, test_channel=target_ch)
        if success:
            resp = KyroContainer(accent_color=0x00FF66)
            resp.add_section(
                content=(
                    f"**Welcome Test Card Dispatched**\n"
                    f"> Test welcome message was successfully sent to {target_ch.mention}."
                )
            )
            resp.add_separator(divider=True)
            resp.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, resp)
        else:
            resp = KyroContainer(accent_color=0xFF0033)
            resp.add_section(
                content=(
                    f"**Welcome Test Dispatch Failed**\n"
                    f"> {err}"
                )
            )
            resp.add_separator(divider=True)
            resp.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, resp)

    @welcome_group.command(
        name="toggle",
        description="Enable or disable the welcome message.",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_toggle(self, ctx: CustomContext) -> None:
        """Toggle welcome event on/off."""
        res = await self.bot.event_mgr.toggle_event(ctx.guild.id, "welcome")
        if res is None:
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            await ctx.send_warning(f"No welcome configuration found. Set it up using `{prefix}welcome set`.")
            return

        state = "Enabled" if res else "Disabled"
        await ctx.send_success(f"Welcome event has been **{state}**.", title="Welcome Status")

    @welcome_group.command(
        name="reset",
        aliases=["clear", "delete"],
        description="Reset and disable welcome messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def welcome_reset(self, ctx: CustomContext) -> None:
        """Clear welcome configuration."""
        await self.bot.event_mgr.delete_event_config(ctx.guild.id, "welcome")
        await ctx.send_success("Welcome event configuration has been reset.", title="Welcome Reset")

    @welcome_group.command(
        name="announce",
        description="Dispatch a saved embed card with an outer mention ping (@everyone, role, etc.).",
    )
    @commands.has_permissions(manage_messages=True)
    async def welcome_announce(self, ctx: CustomContext, *, args: str = "") -> None:
        """Dispatch a saved embed card with an outer mention ping."""
        await self._dispatch_announcement(ctx, args)

    @commands.hybrid_command(
        name="announce",
        aliases=["embedannounce"],
        description="Dispatch a saved embed card with an outer mention ping (@everyone, role, etc.).",
    )
    @commands.has_permissions(manage_messages=True)
    async def embed_announce_cmd(self, ctx: CustomContext, *, args: str = "") -> None:
        """Dispatch a saved embed card with an outer mention ping."""
        await self._dispatch_announcement(ctx, args)

    async def _dispatch_announcement(
        self,
        ctx: CustomContext,
        args: str = "",
    ) -> None:
        """Internal helper to dispatch an embed announcement card with mention ping."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        raw_text = args.strip()

        if not raw_text:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Embed Announce Guide**\n"
                    "> Post a saved embed card with an outer mention ping (@everyone, @here, or role).\n"
                    f"> **Usage:** `{prefix}embed announce [#channel] <embed_name> [ping_message]`\n"
                    f"> **Example:** `{prefix}embed announce #announcements my_note @everyone Important update!`\n"
                    f"> **Note:** If no ping message is specified, it defaults to `@everyone`."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        target_channel: discord.abc.Messageable = ctx.channel

        # parse target channel if provided
        if ctx.message.channel_mentions:
            target_channel = ctx.message.channel_mentions[0]
            raw_text = re.sub(rf"<#{target_channel.id}>", "", raw_text).strip()
        else:
            words = raw_text.split()
            if words:
                first_w = words[0].lstrip("#")
                if first_w.isdigit() and ctx.guild:
                    ch = ctx.guild.get_channel(int(first_w))
                    if isinstance(ch, (discord.TextChannel, discord.Thread)):
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()
                if (target_channel == ctx.channel) and ctx.guild:
                    ch = discord.utils.get(ctx.guild.text_channels, name=first_w.lower())
                    if ch:
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()

        # parse embed name and ping message
        words = raw_text.split()
        if not words:
            await ctx.send_warning(
                f"Please specify a saved embed template name!\n"
                f"Usage: `{prefix}embed announce [#channel] <embed_name> [ping_message]`",
                title="Missing Embed Name",
            )
            return

        embed_name = None
        ping_content = "@everyone"
        template = None

        # Check if first word is the template name
        first_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
        template = await self.bot.embed_mgr.get_template(ctx.guild.id, first_clean)
        if template:
            embed_name = first_clean
            if len(words) > 1:
                ping_content = " ".join(words[1:]).strip()
        elif len(words) > 1:
            # Check if last word is the template name
            last_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[-1].lower())
            template_last = await self.bot.embed_mgr.get_template(ctx.guild.id, last_clean)
            if template_last:
                embed_name = last_clean
                template = template_last
                ping_content = " ".join(words[:-1]).strip() or "@everyone"

        if not embed_name or not template:
            await ctx.send_error(
                f"Saved embed template was not found for `{first_clean}`.\n"
                f"Use `{prefix}embed list` to see all saved templates in this server.",
                title="Embed Not Found",
            )
            return

        # security / Permission check for mass mentions
        if ("@everyone" in ping_content or "@here" in ping_content) and not getattr(ctx.author.guild_permissions, "mention_everyone", False):
            await ctx.send_error(
                "You need the **Mention @everyone, @here, and All Roles** permission to send mass mention announcements.",
                title="Permission Denied",
            )
            return

        # bot Channel Permission Check
        if isinstance(target_channel, discord.TextChannel):
            bot_perms = target_channel.permissions_for(ctx.guild.me)
            if not bot_perms.send_messages:
                await ctx.send_error(f"Bot lacks `Send Messages` permission in {target_channel.mention}.")
                return
            if not bot_perms.embed_links:
                await ctx.send_error(f"Bot lacks `Embed Links` permission in {target_channel.mention}.")
                return
            if not bot_perms.manage_webhooks:
                await ctx.send_error(f"Bot requires `Manage Webhooks` permission in {target_channel.mention} to render Components V2 container cards.")
                return

        # resolve outer ping message placeholders
        resolved_ping = resolve_placeholders(ping_content, user=ctx.author, guild=ctx.guild)

        # build the container from saved template
        draft = ContainerDraft.from_dict(template)
        avatar_url = str(self.bot.user.display_avatar.url) if self.bot and self.bot.user else ""
        container = draft.to_container(
            user=ctx.author,
            guild=ctx.guild,
            channel=target_channel,
            bot=self.bot,
            default_avatar=avatar_url,
        )

        # dispatch container with outer ping and allowed mentions
        try:
            target_msg = await send_container_response(
                target_channel,
                container,
                content=resolved_ping,
                allowed_mentions=discord.AllowedMentions(everyone=True, roles=True, users=True),
            )

            # Record interactive card for dropdown/button handling if interactive
            msg_id = None
            if isinstance(target_msg, dict) and "id" in target_msg:
                msg_id = int(target_msg["id"])
            elif hasattr(target_msg, "id"):
                msg_id = int(target_msg.id)

            if msg_id:
                await self.bot.embed_mgr.record_interactive_card(
                    guild_id=ctx.guild.id,
                    message_id=msg_id,
                    template_name=embed_name,
                    payload=draft.to_dict(),
                )

            # Delete the trigger message if dispatched in the same channel to keep it clean
            if ctx.channel.id == target_channel.id and ctx.guild.me.guild_permissions.manage_messages:
                try:
                    await ctx.message.delete()
                except Exception:
                    pass

            # If sent to a different channel, send confirmation to invoker
            if ctx.channel.id != target_channel.id:
                ch_mention = getattr(target_channel, "mention", f"#{target_channel}")
                resp_container = KyroContainer(accent_color=None)
                resp_container.add_section(
                    content=(
                        "**Announcement Dispatched**\n"
                        f"> Saved embed `{embed_name}` successfully posted to {ch_mention}."
                    )
                )
                resp_container.add_separator(divider=True)
                resp_container.add_text(
                    f"• **Channel:** {ch_mention}\n"
                    f"• **Ping Message:** `{resolved_ping}`\n"
                    f"-# Dispatched by {ctx.author.display_name}"
                )
                await send_container_response(ctx, resp_container)

        except Exception as e:
            logger.error(f"Failed to post announcement for embed '{embed_name}': {e}", exc_info=e)
            await ctx.send_error(f"Failed to dispatch announcement: {e}")

    # ─── Leave / Goodbye Command Group ───────────────────────────────────────

    @commands.hybrid_group(
        name="leave",
        aliases=["goodbye", "farewell"],
        description="Configure automated server leave / goodbye container cards.",
        fallback="status",
    )
    @commands.has_permissions(manage_guild=True)
    async def leave_group(self, ctx: CustomContext) -> None:
        """View the current leave configuration dashboard."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "leave")

        ch_id = config.get("channel_id") if config else None
        channel = ctx.guild.get_channel(ch_id) if ch_id else None
        ch_str = channel.mention if channel else "`Not Configured`"
        emb_str = f"`{config.get('embed_name')}`" if (config and config.get("embed_name")) else "`Default Card`"
        msg_str = f"`{config.get('message_content')}`" if (config and config.get("message_content")) else "`None (Embed Only)`"
        status_str = "`Enabled`" if (config and config.get("is_enabled", True)) else "`Disabled`"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Leave / Goodbye Configuration**\n"
                f"> Manage automated departure cards for **{ctx.guild.name}**."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"**Channel:** {ch_str} | **Status:** {status_str}\n"
            f"**Bound Embed:** {emb_str}\n"
            f"**Outer Text:** {msg_str}"
        )
        container.add_separator(divider=True)
        container.add_text(
            f"`{prefix}leave set #channel {{user.name}} <embed_name>`\n"
            f"`{prefix}leave test` , `{prefix}leave toggle` , `{prefix}leave reset`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @leave_group.command(
        name="set",
        description="Bind channel, outer text, and custom embed for departure messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def leave_set(
        self,
        ctx: CustomContext,
        *,
        args: str = "",
    ) -> None:
        """Bind leave channel, message content, and named embed template."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        raw_text = args.strip()

        target_channel = None
        if ctx.message.channel_mentions:
            target_channel = ctx.message.channel_mentions[0]
            raw_text = re.sub(rf"<#{target_channel.id}>", "", raw_text).strip()
        else:
            words = raw_text.split()
            if words:
                first_w = words[0].lstrip("#")
                if first_w.isdigit():
                    ch = ctx.guild.get_channel(int(first_w))
                    if isinstance(ch, discord.TextChannel):
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()
                if not target_channel:
                    ch = discord.utils.get(ctx.guild.text_channels, name=first_w.lower())
                    if ch:
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()

        if not target_channel:
            target_channel = ctx.channel

        words = raw_text.split()
        embed_name = None
        message_content = None

        if len(words) == 1:
            clean_word = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
            template = await self.bot.embed_mgr.get_template(ctx.guild.id, clean_word)
            if template:
                embed_name = clean_word
            else:
                message_content = raw_text
        elif len(words) > 1:
            last_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[-1].lower())
            template_last = await self.bot.embed_mgr.get_template(ctx.guild.id, last_clean)
            if template_last:
                embed_name = last_clean
                message_content = raw_text[:-len(words[-1])].strip() or None
            else:
                first_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
                template_first = await self.bot.embed_mgr.get_template(ctx.guild.id, first_clean)
                if template_first:
                    embed_name = first_clean
                    message_content = raw_text[len(words[0]):].strip() or None
                else:
                    message_content = raw_text

        success = await self.bot.event_mgr.save_event_config(
            guild_id=ctx.guild.id,
            event_type="leave",
            channel_id=target_channel.id,
            embed_name=embed_name,
            message_content=message_content,
            is_enabled=True,
        )

        if not success:
            await ctx.send_error("Failed to save leave configuration.")
            return

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Leave System Configured**\n"
                f"> Departure messages will be posted in {target_channel.mention}."
            )
        )
        container.add_separator(divider=True)
        emb_display = f"`{embed_name}`" if embed_name else "`Default Card`"
        msg_display = f"`{message_content}`" if message_content else "`None (Embed Only)`"
        container.add_text(
            f"**Channel:** {target_channel.mention}\n"
            f"**Bound Embed:** {emb_display}\n"
            f"**Outer Text:** {msg_display}\n\n"
            f"> Run `{prefix}leave test` to preview the message live!"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @leave_group.command(
        name="test",
        description="Test the current leave message live in channel.",
    )
    @commands.has_permissions(manage_guild=True)
    async def leave_test(self, ctx: CustomContext) -> None:
        """Send a test leave card."""
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "leave")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not config or not config.get("channel_id"):
            await ctx.send_warning(f"Leave is not configured yet! Use `{prefix}leave set #channel {{user.name}} <embed_name>`.")
            return

        ch_id = config["channel_id"]
        target_ch = ctx.guild.get_channel(ch_id) or self.bot.get_channel(ch_id)
        if not target_ch:
            try:
                target_ch = await self.bot.fetch_channel(ch_id)
            except Exception:
                target_ch = None

        if not target_ch or not isinstance(target_ch, (discord.TextChannel, discord.Thread)):
            await ctx.send_error(f"Configured leave channel not found. Set a new channel with `{prefix}leave set`.")
            return

        success, err = await self._send_event_card("leave", ctx.guild, ctx.author, test_channel=target_ch)
        if success:
            resp = KyroContainer(accent_color=0x00FF66)
            resp.add_section(
                content=(
                    f"**Leave Test Card Dispatched**\n"
                    f"> Test departure message was successfully sent to {target_ch.mention}."
                )
            )
            resp.add_separator(divider=True)
            resp.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, resp)
        else:
            resp = KyroContainer(accent_color=0xFF0033)
            resp.add_section(
                content=(
                    f"**Leave Test Dispatch Failed**\n"
                    f"> {err}"
                )
            )
            resp.add_separator(divider=True)
            resp.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, resp)

    @leave_group.command(
        name="toggle",
        description="Enable or disable leave messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def leave_toggle(self, ctx: CustomContext) -> None:
        """Toggle leave event on/off."""
        res = await self.bot.event_mgr.toggle_event(ctx.guild.id, "leave")
        if res is None:
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            await ctx.send_warning(f"No leave configuration found. Set it up using `{prefix}leave set`.")
            return

        state = "Enabled" if res else "Disabled"
        await ctx.send_success(f"Leave event has been **{state}**.", title="Leave Status")

    @leave_group.command(
        name="reset",
        aliases=["clear", "delete"],
        description="Reset and disable leave messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def leave_reset(self, ctx: CustomContext) -> None:
        """Clear leave configuration."""
        await self.bot.event_mgr.delete_event_config(ctx.guild.id, "leave")
        await ctx.send_success("Leave event configuration has been reset.", title="Leave Reset")

    # ─── Boost Command Group ─────────────────────────────────────────────────

    @commands.hybrid_group(
        name="boost",
        description="Configure automated server boost celebration container cards.",
        fallback="status",
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_group(self, ctx: CustomContext) -> None:
        """View the current boost configuration dashboard."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "boost")

        ch_id = config.get("channel_id") if config else None
        channel = ctx.guild.get_channel(ch_id) if ch_id else None
        ch_str = channel.mention if channel else "`Not Configured`"
        emb_str = f"`{config.get('embed_name')}`" if (config and config.get("embed_name")) else "`Default Card`"
        msg_str = f"`{config.get('message_content')}`" if (config and config.get("message_content")) else "`None (Embed Only)`"
        status_str = "`Enabled`" if (config and config.get("is_enabled", True)) else "`Disabled`"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Server Boost Celebration Configuration**\n"
                f"> Manage automated boost announcements for **{ctx.guild.name}**."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"**Channel:** {ch_str} | **Status:** {status_str}\n"
            f"**Bound Embed:** {emb_str}\n"
            f"**Outer Text:** {msg_str}"
        )
        container.add_separator(divider=True)
        container.add_text(
            f"`{prefix}boost set #channel {{user}} <embed_name>`\n"
            f"`{prefix}boost test` , `{prefix}boost toggle` , `{prefix}boost reset`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @boost_group.command(
        name="set",
        description="Bind channel, outer text, and custom embed for boost announcements.",
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_set(
        self,
        ctx: CustomContext,
        *,
        args: str = "",
    ) -> None:
        """Bind boost channel, message content, and named embed template."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        raw_text = args.strip()

        target_channel = None
        if ctx.message.channel_mentions:
            target_channel = ctx.message.channel_mentions[0]
            raw_text = re.sub(rf"<#{target_channel.id}>", "", raw_text).strip()
        else:
            words = raw_text.split()
            if words:
                first_w = words[0].lstrip("#")
                if first_w.isdigit():
                    ch = ctx.guild.get_channel(int(first_w))
                    if isinstance(ch, discord.TextChannel):
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()
                if not target_channel:
                    ch = discord.utils.get(ctx.guild.text_channels, name=first_w.lower())
                    if ch:
                        target_channel = ch
                        raw_text = " ".join(words[1:]).strip()

        if not target_channel:
            target_channel = ctx.channel

        words = raw_text.split()
        embed_name = None
        message_content = None

        if len(words) == 1:
            clean_word = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
            template = await self.bot.embed_mgr.get_template(ctx.guild.id, clean_word)
            if template:
                embed_name = clean_word
            else:
                message_content = raw_text
        elif len(words) > 1:
            last_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[-1].lower())
            template_last = await self.bot.embed_mgr.get_template(ctx.guild.id, last_clean)
            if template_last:
                embed_name = last_clean
                message_content = raw_text[:-len(words[-1])].strip() or None
            else:
                first_clean = re.sub(r"[^a-zA-Z0-9_-]", "", words[0].lower())
                template_first = await self.bot.embed_mgr.get_template(ctx.guild.id, first_clean)
                if template_first:
                    embed_name = first_clean
                    message_content = raw_text[len(words[0]):].strip() or None
                else:
                    message_content = raw_text

        success = await self.bot.event_mgr.save_event_config(
            guild_id=ctx.guild.id,
            event_type="boost",
            channel_id=target_channel.id,
            embed_name=embed_name,
            message_content=message_content,
            is_enabled=True,
        )

        if not success:
            await ctx.send_error("Failed to save boost configuration.")
            return

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Boost Celebration System Configured**\n"
                f"> Boost announcements will be posted in {target_channel.mention}."
            )
        )
        container.add_separator(divider=True)
        emb_display = f"`{embed_name}`" if embed_name else "`Default Card`"
        msg_display = f"`{message_content}`" if message_content else "`None (Embed Only)`"
        container.add_text(
            f"**Channel:** {target_channel.mention}\n"
            f"**Bound Embed:** {emb_display}\n"
            f"**Outer Text:** {msg_display}\n\n"
            f"> Run `{prefix}boost test` to preview the message live!"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @boost_group.command(
        name="test",
        description="Test the boost celebration message live in channel.",
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_test(self, ctx: CustomContext) -> None:
        """Send a test boost celebration card."""
        config = await self.bot.event_mgr.get_event_config(ctx.guild.id, "boost")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        if not config or not config.get("channel_id"):
            await ctx.send_warning(f"Boost is not configured yet! Use `{prefix}boost set #channel {{user}} <embed_name>`.")
            return

        ch_id = config["channel_id"]
        target_ch = ctx.guild.get_channel(ch_id) or self.bot.get_channel(ch_id)
        if not target_ch:
            try:
                target_ch = await self.bot.fetch_channel(ch_id)
            except Exception:
                target_ch = None

        if not target_ch or not isinstance(target_ch, (discord.TextChannel, discord.Thread)):
            await ctx.send_error(f"Configured boost channel not found. Set a new channel with `{prefix}boost set`.")
            return

        extra = {
            "booster": ctx.author.mention,
            "boost_count": getattr(ctx.guild, "premium_subscription_count", 1),
            "boost_tier": f"Level {getattr(ctx.guild, 'premium_tier', 1)}",
        }
        success, err = await self._send_event_card("boost", ctx.guild, ctx.author, extra=extra, test_channel=target_ch)
        if success:
            resp = KyroContainer(accent_color=0x00FF66)
            resp.add_section(
                content=(
                    f"**Boost Test Card Dispatched**\n"
                    f"> Test boost celebration was successfully sent to {target_ch.mention}."
                )
            )
            resp.add_separator(divider=True)
            resp.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, resp)
        else:
            resp = KyroContainer(accent_color=0xFF0033)
            resp.add_section(
                content=(
                    f"**Boost Test Dispatch Failed**\n"
                    f"> {err}"
                )
            )
            resp.add_separator(divider=True)
            resp.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, resp)

    @boost_group.command(
        name="toggle",
        description="Enable or disable boost celebration messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_toggle(self, ctx: CustomContext) -> None:
        """Toggle boost event on/off."""
        res = await self.bot.event_mgr.toggle_event(ctx.guild.id, "boost")
        if res is None:
            prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
            await ctx.send_warning(f"No boost configuration found. Set it up using `{prefix}boost set`.")
            return

        state = "Enabled" if res else "Disabled"
        await ctx.send_success(f"Boost event has been **{state}**.", title="Boost Status")

    @boost_group.command(
        name="reset",
        aliases=["clear", "delete"],
        description="Reset and disable boost messages.",
    )
    @commands.has_permissions(manage_guild=True)
    async def boost_reset(self, ctx: CustomContext) -> None:
        """Clear boost configuration."""
        await self.bot.event_mgr.delete_event_config(ctx.guild.id, "boost")
        await ctx.send_success("Boost event configuration has been reset.", title="Boost Reset")


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(AutoEvents(bot))
