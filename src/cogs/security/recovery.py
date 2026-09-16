"""
Kyro Discord Bot - Post-Attack Disaster Recovery & Server Restoration Suite
Rapid response tools to purge rogue raid channels, wipe mass pings, lock down the server,
and restore server structure from snapshot after a nuke/raid attack.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import TYPE_CHECKING, Any, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Security.Recovery")


class ChannelPurgeConfirmView(discord.ui.View):
    """Components V2 interactive confirmation for deleting multiple rogue channels."""

    def __init__(self, author_id: int, channels: list[discord.abc.GuildChannel], delay: float = 0.8) -> None:
        super().__init__(timeout=60.0)
        self.author_id = author_id
        self.channels = channels
        self.delay = delay
        self.confirmed: bool = False

    @discord.ui.button(label="Confirm & Delete Channels", style=discord.ButtonStyle.danger, custom_id="recovery_confirm_purge")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the administrator who invoked the command can confirm this.", ephemeral=True)
            return

        self.confirmed = True
        self.stop()
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="recovery_cancel_purge")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the administrator who invoked the command can cancel this.", ephemeral=True)
            return

        self.confirmed = False
        self.stop()
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        await interaction.response.edit_message(view=self)


class DisasterRecovery(commands.Cog, name="Security-Recovery"):
    """Server disaster recovery, rogue channel cleanup, and snapshot rollback suite."""
    category: str = "Security"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # In-memory storage for saved permissions during lockdown: guild_id -> {channel_id: original_overwrites}
        self._lockdown_cache: dict[int, dict[int, discord.PermissionOverwrite]] = {}

    @commands.group(
        name="recovery",
        aliases=["nukeclean", "disaster", "cleanattack"],
        invoke_without_command=True,
        description="Emergency server cleanup and post-attack disaster recovery tools.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def recovery(self, ctx: CustomContext) -> None:
        """Display the Post-Attack Disaster Recovery console and available emergency commands."""
        prefix = ctx.clean_prefix
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{Config.BOT_NAME} Disaster Recovery Suite**\n"
                "> High-speed server restoration and rogue channel/threat cleanup engine.\n"
                "> Execute recovery subcommands below to restore server state after an attack."
            )
        )
        container.add_separator(divider=True)

        commands_guide = (
            f"**`{prefix}recovery purgechannels [minutes] [pattern]`**\n"
            f"-# Bulk delete rogue channels created during the raid (rate-limit safe).\n\n"
            f"**`{prefix}recovery ban <user_or_bot_id> [reason]`**\n"
            f"-# Instantly ban attacker & wipe all their messages/pings from last 24h.\n\n"
            f"**`{prefix}recovery lockdown`**\n"
            f"-# Freeze @everyone across all text channels during cleanup.\n\n"
            f"**`{prefix}recovery unlock`**\n"
            f"-# Restore normal chat permissions once server cleanup is complete.\n\n"
            f"**`{prefix}recovery snapshot create`**\n"
            f"-# Save current clean server channel layout as an emergency backup.\n\n"
            f"**`{prefix}recovery rollback`**\n"
            f"-# Compare live channels with saved snapshot and purge all foreign raid channels."
        )
        container.add_text(commands_guide)
        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {ctx.author.display_name}** | Requires Administrator")

        await send_container_response(ctx, container)

    @recovery.command(
        name="ban",
        aliases=["threatban", "raidban"],
        description="Ban an attacker/rogue bot and wipe all their messages/pings across the server (last 24h).",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(ban_members=True)
    async def recovery_ban(self, ctx: CustomContext, target_id: str, *, reason: str = "Disaster Recovery - Attacker Removal") -> None:
        """Ban the attacker and erase 24 hours of mass pings and messages across all channels."""
        # Resolve target ID
        clean_id_str = target_id.strip("<@!>")
        try:
            user_id = int(clean_id_str)
        except ValueError:
            await ctx.send_error("Please provide a valid user or bot ID / mention.")
            return

        guild = ctx.guild
        if not guild:
            return

        # Fetch user object
        try:
            target_user = await self.bot.fetch_user(user_id)
        except discord.NotFound:
            await ctx.send_error(f"User with ID `{user_id}` not found on Discord.")
            return
        except discord.HTTPException as e:
            await ctx.send_error(f"Failed to fetch user: {e}")
            return

        # Check hierarchy if member in guild
        member = guild.get_member(user_id)
        if member:
            if member.top_role >= guild.me.top_role:
                await ctx.send_error("Cannot ban this member: their role is higher than or equal to my highest role.")
                return
            if member == guild.owner:
                await ctx.send_error("Cannot ban the server owner.")
                return

        audit_reason = f"[Disaster Recovery] By {ctx.author} ({ctx.author.id}): {reason}"

        try:
            # delete_message_seconds=86400 purges all messages & pings from the attacker in the last 24h across all channels
            await guild.ban(target_user, reason=audit_reason, delete_message_seconds=86400)
        except discord.Forbidden:
            await ctx.send_error("I don't have permission to ban this user.")
            return
        except discord.HTTPException as err:
            await ctx.send_error(f"Discord API error while banning: {err}")
            return

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Threat Neutralized & Messages Purged**\n"
                f"> Successfully banned attacker **{target_user}** (`{target_user.id}`).\n"
                f"> All messages, pings, and invites from this user in the last **24 hours** have been erased server-wide."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"**Reason:** `{reason}`\n-# **Enforced by {ctx.author.display_name}**")
        await send_container_response(ctx, container)

    @recovery.command(
        name="purgechannels",
        aliases=["cleanrooms", "delchannels", "raidchannels"],
        description="Bulk delete rogue channels created during an attack within the specified time window.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def recovery_purgechannels(
        self, ctx: CustomContext, minutes: int = 30, *, pattern: Optional[str] = None
    ) -> None:
        """Find and bulk delete channels created within the last N minutes or matching a pattern."""
        guild = ctx.guild
        if not guild:
            return

        if minutes <= 0 or minutes > 1440:
            await ctx.send_error("Please specify a duration between `1` and `1440` minutes (up to 24 hours).")
            return

        now = discord.utils.utcnow()
        cutoff_time = now - datetime.timedelta(minutes=minutes)

        # Scan guild channels for creation time >= cutoff_time
        candidate_channels: list[discord.abc.GuildChannel] = []
        for ch in guild.channels:
            # Do not delete the channel where the admin is running the recovery command
            if ch.id == ctx.channel.id:
                continue

            # Check creation timestamp
            created_at = ch.created_at
            if created_at and created_at >= cutoff_time:
                if pattern:
                    if pattern.lower() in ch.name.lower():
                        candidate_channels.append(ch)
                else:
                    candidate_channels.append(ch)

        if not candidate_channels:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**No Rogue Channels Found**\n"
                    f"> Scanned all channels in **{guild.name}**.\n"
                    f"> No channels were created in the last **{minutes} minute(s)**"
                    + (f" matching pattern `{pattern}`." if pattern else ".")
                )
            )
            await send_container_response(ctx, container)
            return

        # Prepare Confirmation Card
        total_found = len(candidate_channels)
        sample_names = ", ".join([f"`#{c.name}`" for c in candidate_channels[:12]])
        if total_found > 12:
            sample_names += f" and **{total_found - 12} more...**"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Rogue Channel Purge Request**\n"
                f"> Detected **{total_found} channel(s)** created within the last **{minutes} minute(s)**.\n\n"
                f"**Channels to be deleted:**\n{sample_names}"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            "-# Deletion will execute with a rate-limit safe backoff (~0.8s/channel) to prevent Discord 429 block.\n"
            "-# Click **Confirm & Delete Channels** below to proceed."
        )

        view = ChannelPurgeConfirmView(ctx.author.id, candidate_channels)
        resp_msg = await send_container_response(ctx, container, view=view)

        await view.wait()
        if not view.confirmed:
            cancel_card = KyroContainer(accent_color=None)
            cancel_card.add_section(
                content=(
                    "**Channel Purge Cancelled**\n"
                    "> No channels were deleted. Operation safely aborted by administrator."
                )
            )
            await edit_container_response(resp_msg, cancel_card)
            return

        # Begin Rate-limit Safe Sequential Deletion
        progress_card = KyroContainer(accent_color=None)
        progress_card.add_section(
            content=(
                "**Purging Rogue Channels in Progress...**\n"
                f"> Deleting `{total_found}` channels with rate-limit protection. Please stand by."
            )
        )
        await edit_container_response(resp_msg, progress_card)

        deleted_count = 0
        failed_count = 0
        audit_reason = f"[Disaster Recovery] Purge by {ctx.author} ({ctx.author.id})"

        for ch in candidate_channels:
            try:
                await ch.delete(reason=audit_reason)
                deleted_count += 1
                await asyncio.sleep(0.8)  # Safe backoff against Discord API rate limits
            except (discord.NotFound, discord.HTTPException) as del_err:
                logger.warning(f"Could not delete channel {ch.id} ({ch.name}): {del_err}")
                failed_count += 1

        done_card = KyroContainer(accent_color=None)
        done_card.add_section(
            content=(
                "**Rogue Channel Purge Completed**\n"
                f"> Successfully deleted **{deleted_count} rogue channel(s)**.\n"
                + (f"> Encountered errors on `{failed_count}` channel(s).\n" if failed_count else "")
                + f"> Server channels restored to normal state."
            )
        )
        done_card.add_separator(divider=True)
        done_card.add_text(f"-# **Executed by {ctx.author.display_name}** | Duration window: {minutes}m")
        await edit_container_response(resp_msg, done_card)

    @recovery.command(
        name="lockdown",
        aliases=["emergencyfreeze", "freeze"],
        description="Emergency server lockdown: freezes @everyone across all channels during cleanup.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def recovery_lockdown(self, ctx: CustomContext) -> None:
        """Lock down all text channels by disabling Send Messages for @everyone."""
        guild = ctx.guild
        if not guild:
            return

        everyone_role = guild.default_role
        locked_channels = 0

        # Save previous permissions for rollback
        if guild.id not in self._lockdown_cache:
            self._lockdown_cache[guild.id] = {}

        for ch in guild.text_channels:
            overwrite = ch.overwrites_for(everyone_role)
            # Only change if send_messages is not already explicitly False
            if overwrite.send_messages is not False:
                # Save previous overwrite state
                self._lockdown_cache[guild.id][ch.id] = discord.PermissionOverwrite(
                    send_messages=overwrite.send_messages,
                    send_messages_in_threads=overwrite.send_messages_in_threads,
                    add_reactions=overwrite.add_reactions,
                )
                try:
                    overwrite.send_messages = False
                    overwrite.send_messages_in_threads = False
                    overwrite.add_reactions = False
                    await ch.set_permissions(everyone_role, overwrite=overwrite, reason=f"Emergency Lockdown by {ctx.author}")
                    locked_channels += 1
                except discord.HTTPException:
                    pass

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Emergency Server Lockdown Activated**\n"
                f"> Freezed `@everyone` chat permissions across **{locked_channels} text channel(s)**.\n"
                "> Regular members cannot send messages or add reactions while cleanup is underway."
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"-# Run `{ctx.clean_prefix}recovery unlock` when you are ready to restore chat permissions."
        )
        await send_container_response(ctx, container)

    @recovery.command(
        name="unlock",
        aliases=["unfreeze"],
        description="Restore normal chat permissions for @everyone after lockdown.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def recovery_unlock(self, ctx: CustomContext) -> None:
        """Unlock all text channels and restore @everyone permissions."""
        guild = ctx.guild
        if not guild:
            return

        everyone_role = guild.default_role
        unlocked_count = 0
        cached = self._lockdown_cache.get(guild.id, {})

        for ch in guild.text_channels:
            overwrite = ch.overwrites_for(everyone_role)
            if ch.id in cached:
                orig = cached[ch.id]
                overwrite.send_messages = orig.send_messages
                overwrite.send_messages_in_threads = orig.send_messages_in_threads
                overwrite.add_reactions = orig.add_reactions
            else:
                overwrite.send_messages = None
                overwrite.send_messages_in_threads = None
                overwrite.add_reactions = None

            try:
                await ch.set_permissions(everyone_role, overwrite=overwrite, reason=f"Emergency Lockdown Lifted by {ctx.author}")
                unlocked_count += 1
            except discord.HTTPException:
                pass

        self._lockdown_cache.pop(guild.id, None)

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Emergency Server Lockdown Lifted**\n"
                f"> Restored chat permissions across **{unlocked_count} text channel(s)**.\n"
                "> Members can now resume sending messages normally."
            )
        )
        await send_container_response(ctx, container)

    @recovery.group(
        name="snapshot",
        aliases=["backup"],
        invoke_without_command=True,
        description="Create or view server channel snapshots for disaster recovery.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def recovery_snapshot(self, ctx: CustomContext) -> None:
        """Display snapshot usage instructions."""
        prefix = ctx.clean_prefix
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{Config.BOT_NAME} Server Snapshot Engine**\n"
                f"> **`{prefix}recovery snapshot create`** - Save current legitimate channels and categories.\n"
                f"> **`{prefix}recovery snapshot view`** - Inspect last saved snapshot timestamp and channel count.\n"
                f"> **`{prefix}recovery rollback`** - Compare current server with snapshot and auto-purge foreign raid channels."
            )
        )
        await send_container_response(ctx, container)

    @recovery_snapshot.command(
        name="create",
        aliases=["save"],
        description="Create a full snapshot backup of all current legitimate channels and categories.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def snapshot_create(self, ctx: CustomContext) -> None:
        """Save clean server channel topology into the database."""
        guild = ctx.guild
        if not guild:
            return

        channels_payload = []
        for ch in guild.channels:
            channels_payload.append({
                "id": ch.id,
                "name": ch.name,
                "type": ch.type.name,
                "position": ch.position,
                "category_id": ch.category_id if hasattr(ch, "category_id") else None,
            })

        snapshot_dict = {
            "guild_id": guild.id,
            "guild_name": guild.name,
            "total_channels": len(channels_payload),
            "channels": channels_payload,
            "saved_at": discord.utils.utcnow().isoformat(),
        }

        # Store in database
        query = """
        INSERT INTO guild_server_snapshots (guild_id, snapshot_data, created_by, created_at)
        VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
        ON CONFLICT (guild_id)
        DO UPDATE SET snapshot_data = EXCLUDED.snapshot_data,
                      created_by = EXCLUDED.created_by,
                      created_at = CURRENT_TIMESTAMP;
        """
        try:
            await self.bot.db.execute(query, guild.id, json.dumps(snapshot_dict), ctx.author.id)
        except Exception as err:
            await ctx.send_error(f"Failed to save snapshot to database: {err}")
            return

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Server Snapshot Saved Successfully**\n"
                f"> Registered **{len(channels_payload)} channels and categories** into secure database backup.\n"
                f"> If your server is ever attacked or nuked, run `{ctx.clean_prefix}recovery rollback` to instantly purge rogue channels."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# **Saved by {ctx.author.display_name}** | {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        await send_container_response(ctx, container)

    @recovery_snapshot.command(
        name="view",
        aliases=["info"],
        description="View details of the saved server snapshot.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def snapshot_view(self, ctx: CustomContext) -> None:
        """Inspect the current server snapshot in database."""
        guild = ctx.guild
        if not guild:
            return

        row = await self.bot.db.fetch_one("SELECT snapshot_data, created_at, created_by FROM guild_server_snapshots WHERE guild_id = $1;", guild.id)
        if not row:
            await ctx.send_error(f"No snapshot found for this server. Use `{ctx.clean_prefix}recovery snapshot create` to take one.")
            return

        raw_data = row["snapshot_data"]
        snapshot_dict = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        total_channels = snapshot_dict.get("total_channels", 0)
        saved_at = row.get("created_at")
        saved_by_id = row.get("created_by")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**{guild.name} Snapshot Profile**\n"
                f"> **Archived Channels:** `{total_channels}`\n"
                f"> **Created By:** <@{saved_by_id}>\n"
                f"> **Timestamp:** `{saved_at}`"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Run `{ctx.clean_prefix}recovery rollback` to clean unauthorized channels against this snapshot.")
        await send_container_response(ctx, container)

    @recovery.command(
        name="rollback",
        aliases=["revertchannels", "cleannuke"],
        description="Compare server with snapshot and auto-purge all rogue foreign channels created during a raid.",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def recovery_rollback(self, ctx: CustomContext) -> None:
        """Compare current channels against snapshot and purge unauthorized foreign channels."""
        guild = ctx.guild
        if not guild:
            return

        row = await self.bot.db.fetch_one("SELECT snapshot_data FROM guild_server_snapshots WHERE guild_id = $1;", guild.id)
        if not row:
            await ctx.send_error(f"No snapshot found. You must create a snapshot with `{ctx.clean_prefix}recovery snapshot create` first.")
            return

        raw_data = row["snapshot_data"]
        snapshot_dict = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
        snapshot_channel_ids = {c["id"] for c in snapshot_dict.get("channels", [])}

        # Identify channels currently in the server that DO NOT exist in the snapshot
        foreign_channels: list[discord.abc.GuildChannel] = []
        for ch in guild.channels:
            if ch.id == ctx.channel.id:
                continue
            if ch.id not in snapshot_channel_ids:
                foreign_channels.append(ch)

        if not foreign_channels:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Server Integrity 100% Matches Snapshot**\n"
                    "> No rogue or foreign channels were found. All existing channels belong to your legitimate snapshot."
                )
            )
            await send_container_response(ctx, container)
            return

        # Prepare confirmation card for foreign channels
        total_foreign = len(foreign_channels)
        sample_names = ", ".join([f"`#{c.name}`" for c in foreign_channels[:12]])
        if total_foreign > 12:
            sample_names += f" and **{total_foreign - 12} more...**"

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Snapshot Rollback: {total_foreign} Rogue Channels Detected**\n"
                f"> Found **{total_foreign} foreign channel(s)** not present in your legitimate snapshot.\n\n"
                f"**Channels to be purged:**\n{sample_names}"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            "-# Deleting these channels will revert the server layout back to the clean snapshot.\n"
            "-# Click **Confirm & Delete Channels** below to execute."
        )

        view = ChannelPurgeConfirmView(ctx.author.id, foreign_channels)
        resp_msg = await send_container_response(ctx, container, view=view)

        await view.wait()
        if not view.confirmed:
            cancel_card = KyroContainer(accent_color=None)
            cancel_card.add_section(
                content=(
                    "**Snapshot Rollback Aborted**\n"
                    "> No channels were deleted."
                )
            )
            await edit_container_response(resp_msg, cancel_card)
            return

        # Execute Deletion
        progress_card = KyroContainer(accent_color=None)
        progress_card.add_section(
            content=(
                "**Purging Foreign Raid Channels...**\n"
                f"> Reverting server back to clean snapshot. Deleting `{total_foreign}` channel(s)..."
            )
        )
        await edit_container_response(resp_msg, progress_card)

        deleted_count = 0
        failed_count = 0
        audit_reason = f"[Snapshot Rollback] Revert by {ctx.author} ({ctx.author.id})"

        for ch in foreign_channels:
            try:
                await ch.delete(reason=audit_reason)
                deleted_count += 1
                await asyncio.sleep(0.8)
            except (discord.NotFound, discord.HTTPException):
                failed_count += 1

        done_card = KyroContainer(accent_color=None)
        done_card.add_section(
            content=(
                "**Snapshot Rollback Completed**\n"
                f"> Successfully purged **{deleted_count} foreign raid channel(s)**.\n"
                + (f"> Failed on `{failed_count}` channel(s).\n" if failed_count else "")
                + "> Your server channel layout has been successfully restored."
            )
        )
        await edit_container_response(resp_msg, done_card)


async def setup(bot: KyroBot) -> None:
    """Load the DisasterRecovery cog into KyroBot."""
    await bot.add_cog(DisasterRecovery(bot))
