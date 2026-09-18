"""
Kyro Discord Bot - Dynamic Temp Voice Cog
Provides Join-to-Create temporary voice channels with interactive text-in-voice control panel and automated cleanup.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.bot import KyroBot
from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

logger = logging.getLogger("Kyro.Cogs.TempVoice")


# ─── MODALS ───────────────────────────────────────────────────────────────────

class TempVoiceRenameModal(discord.ui.Modal, title="Rename Voice Room"):
    new_name = discord.ui.TextInput(
        label="New Room Name",
        placeholder="e.g. Squad Call / Late Night Chill",
        min_length=2,
        max_length=40,
        required=True,
    )

    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.new_name.value.strip()
        try:
            await self.channel.edit(name=f"🔊 {name}", reason=f"Temp voice renamed by {interaction.user}")
            await interaction.response.send_message(
                f"**Room Renamed**: Voice channel updated to **🔊 {name}**.",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to rename channel: {e}", ephemeral=True)


class TempVoiceLimitModal(discord.ui.Modal, title="Set User Limit"):
    limit_input = discord.ui.TextInput(
        label="Member Limit (0 for Unlimited)",
        placeholder="Enter a number between 0 and 99",
        min_length=1,
        max_length=2,
        required=True,
    )

    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw_val = self.limit_input.value.strip()
        if not raw_val.isdigit() or not (0 <= int(raw_val) <= 99):
            await interaction.response.send_message("Please enter a valid number between 0 and 99.", ephemeral=True)
            return

        lim = int(raw_val)
        try:
            await self.channel.edit(user_limit=lim, reason=f"Temp voice limit changed by {interaction.user}")
            desc = "Unlimited" if lim == 0 else f"{lim} members"
            await interaction.response.send_message(f"**Limit Updated**: Room capacity set to **{desc}**.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to update limit: {e}", ephemeral=True)


# ─── INTERACTIVE CONTROL PANEL VIEW ──────────────────────────────────────────

class TempVoiceControlView(discord.ui.View):
    """Persistent interactive control panel inside text-in-voice."""

    def __init__(self, bot: KyroBot, channel_id: int) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.channel_id = channel_id

    async def _verify_owner_or_admin(self, interaction: discord.Interaction) -> tuple[bool, Optional[dict]]:
        data = self.bot.temp_voice_mgr.get_channel_data(self.channel_id)
        if not data:
            await interaction.response.send_message("This channel is no longer recognized as a temporary room.", ephemeral=True)
            return False, None

        is_owner = interaction.user.id == data["owner_id"]
        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_channels

        if not is_owner and not is_admin:
            await interaction.response.send_message(
                f"Only the room owner (<@{data['owner_id']}>) or a server administrator can modify this voice channel.",
                ephemeral=True,
            )
            return False, data
        return True, data

    @discord.ui.button(label="Lock / Unlock", style=discord.ButtonStyle.primary, custom_id="temp_vc_lock", emoji="🔒")
    async def toggle_lock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ok, data = await self._verify_owner_or_admin(interaction)
        if not ok or not data:
            return

        channel = interaction.guild.get_channel(self.channel_id) if interaction.guild else None
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Voice channel not found.", ephemeral=True)
            return

        is_currently_locked = data.get("is_locked", False)
        new_locked_state = not is_currently_locked

        try:
            everyone_role = interaction.guild.default_role
            # If locking, deny connect for everyone; if unlocking, allow connect
            await channel.set_permissions(
                everyone_role,
                connect=False if new_locked_state else None,
                reason=f"Temp voice lock toggled by {interaction.user}",
            )
            # Ensure current members inside the room retain connect permissions
            if new_locked_state:
                for member in channel.members:
                    await channel.set_permissions(member, connect=True)

            await self.bot.temp_voice_mgr.update_channel_state(self.channel_id, is_locked=new_locked_state)
            status_text = "Locked (Only invited members can join)" if new_locked_state else "Unlocked (Publicly accessible)"
            await interaction.response.send_message(f"**Room Status**: Voice room is now **{status_text}**.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to update room permissions: {e}", ephemeral=True)

    @discord.ui.button(label="Hide / Unhide", style=discord.ButtonStyle.secondary, custom_id="temp_vc_hide", emoji="👁️")
    async def toggle_hide(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ok, data = await self._verify_owner_or_admin(interaction)
        if not ok or not data:
            return

        channel = interaction.guild.get_channel(self.channel_id) if interaction.guild else None
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Voice channel not found.", ephemeral=True)
            return

        is_currently_hidden = data.get("is_hidden", False)
        new_hidden_state = not is_currently_hidden

        try:
            everyone_role = interaction.guild.default_role
            await channel.set_permissions(
                everyone_role,
                view_channel=False if new_hidden_state else None,
                reason=f"Temp voice hide toggled by {interaction.user}",
            )
            # Ensure current members can always view
            if new_hidden_state:
                for member in channel.members:
                    await channel.set_permissions(member, view_channel=True)

            await self.bot.temp_voice_mgr.update_channel_state(self.channel_id, is_hidden=new_hidden_state)
            status_text = "Hidden from channel list" if new_hidden_state else "Visible in channel list"
            await interaction.response.send_message(f"**Room Visibility**: Voice room is now **{status_text}**.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to update channel visibility: {e}", ephemeral=True)

    @discord.ui.button(label="Set Limit", style=discord.ButtonStyle.secondary, custom_id="temp_vc_limit", emoji="👥")
    async def set_limit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ok, _ = await self._verify_owner_or_admin(interaction)
        if not ok:
            return

        channel = interaction.guild.get_channel(self.channel_id) if interaction.guild else None
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Voice channel not found.", ephemeral=True)
            return

        await interaction.response.send_modal(TempVoiceLimitModal(channel))

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.secondary, custom_id="temp_vc_rename", emoji="✏️")
    async def rename_room(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        ok, _ = await self._verify_owner_or_admin(interaction)
        if not ok:
            return

        channel = interaction.guild.get_channel(self.channel_id) if interaction.guild else None
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Voice channel not found.", ephemeral=True)
            return

        await interaction.response.send_modal(TempVoiceRenameModal(channel))

    @discord.ui.button(label="Claim Room", style=discord.ButtonStyle.success, custom_id="temp_vc_claim", emoji="👑")
    async def claim_ownership(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        data = self.bot.temp_voice_mgr.get_channel_data(self.channel_id)
        if not data:
            await interaction.response.send_message("Room not recognized.", ephemeral=True)
            return

        channel = interaction.guild.get_channel(self.channel_id) if interaction.guild else None
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Voice channel not found.", ephemeral=True)
            return

        current_owner_id = data["owner_id"]
        # Check if current owner is still inside the voice channel
        owner_in_channel = any(m.id == current_owner_id for m in channel.members)

        if owner_in_channel and interaction.user.id != current_owner_id:
            await interaction.response.send_message(
                f"The current room owner (<@{current_owner_id}>) is still connected in this voice channel.",
                ephemeral=True,
            )
            return

        # Transfer ownership
        await self.bot.temp_voice_mgr.transfer_ownership(self.channel_id, interaction.user.id)
        # Grant room permissions to new owner
        try:
            await channel.set_permissions(
                interaction.user,
                connect=True,
                speak=True,
                stream=True,
                move_members=True,
                mute_members=True,
                deafen_members=True,
                manage_channels=True,
            )
        except Exception:
            pass

        await interaction.response.send_message(
            f"**Ownership Transferred**: {interaction.user.mention} is now the host of this voice channel!",
            ephemeral=False,
        )


# ─── COG IMPLEMENTATION ───────────────────────────────────────────────────────

class TempVoice(commands.Cog):
    """Dynamic Join-to-Create temporary voice channel system."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        """Startup cleanup: audit all active temp channels and purge dead rooms."""
        asyncio.create_task(self._audit_temp_channels_on_startup())

    async def _audit_temp_channels_on_startup(self) -> None:
        await self.bot.wait_until_ready()
        await asyncio.sleep(4.0)

        active_rooms = self.bot.temp_voice_mgr.get_all_active_channels()
        purged_count = 0

        for cid, data in active_rooms:
            guild = self.bot.get_guild(data["guild_id"])
            if not guild:
                await self.bot.temp_voice_mgr.unregister_temp_channel(cid)
                purged_count += 1
                continue

            channel = guild.get_channel(cid)
            if not channel:
                # Channel was deleted while bot was offline
                await self.bot.temp_voice_mgr.unregister_temp_channel(cid)
                purged_count += 1
            elif len(channel.members) == 0:
                # Channel is empty
                try:
                    await channel.delete(reason="Purging empty temp voice channel on bot startup")
                except Exception:
                    pass
                await self.bot.temp_voice_mgr.unregister_temp_channel(cid)
                purged_count += 1

        if purged_count > 0:
            logger.info(f"Audited and cleaned up {purged_count} empty/stale temp voice channel(s).")

    # ─── VOICE STATE LISTENER ─────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Core listener handling voice channel creation and empty room destruction."""
        if member.bot:
            return

        # 1. Check if member joined a Master Join-to-Create channel
        if after.channel is not None and (before.channel is None or before.channel.id != after.channel.id):
            guild_id = self.bot.temp_voice_mgr.get_guild_by_master(after.channel.id)
            if guild_id and guild_id == member.guild.id:
                await self._handle_join_to_create(member, after.channel)

        # 2. Check if member left an active temporary channel
        if before.channel is not None and (after.channel is None or before.channel.id != after.channel.id):
            if self.bot.temp_voice_mgr.is_temp_channel(before.channel.id):
                await self._handle_temp_channel_leave(before.channel, member)

    async def _handle_join_to_create(self, member: discord.Member, master_channel: discord.VoiceChannel) -> None:
        """Create a fresh private room and move the user immediately."""
        guild = member.guild
        settings = self.bot.temp_voice_mgr.get_settings(guild.id)
        if not settings:
            return

        category = guild.get_channel(settings["category_id"])
        if not isinstance(category, discord.CategoryChannel):
            category = master_channel.category

        # Format channel name
        name_fmt = settings.get("default_name_format") or "{user}'s Room"
        clean_name = name_fmt.replace("{user}", member.display_name)
        channel_name = f"🔊 {clean_name}"

        # Default permissions
        overwrites: dict[Any, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                stream=True,
            ),
            member: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                stream=True,
                move_members=True,
                mute_members=True,
                deafen_members=True,
                manage_channels=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                manage_channels=True,
                move_members=True,
            ),
        }

        try:
            # Create voice channel
            new_channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                user_limit=settings.get("default_user_limit", 0),
                overwrites=overwrites,
                reason=f"Dynamic Temp Voice requested by {member}",
            )

            # Move user into their new channel
            await member.move_to(new_channel, reason="Moved to newly created temporary voice channel")

            # Register in database & memory
            await self.bot.temp_voice_mgr.register_temp_channel(new_channel.id, guild.id, member.id)

            # Send Control Panel in text-in-voice
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"### {channel_name}\n"
                    f"> Welcome {member.mention}! You are the host of this temporary voice channel.\n"
                    f"> Use the buttons below to lock, hide, adjust limits, or rename your room. "
                    f"When everyone leaves, this channel will auto-delete."
                )
            )
            container.add_separator(divider=True)
            container.add_field("Host", member.mention, inline=True)
            container.add_field("Status", "Unlocked • Public", inline=True)
            container.add_field("Capacity", "Unlimited" if settings.get("default_user_limit", 0) == 0 else f"{settings.get('default_user_limit')} members", inline=True)

            view = TempVoiceControlView(self.bot, new_channel.id)
            panel_msg = await new_channel.send(embed=container.to_embed(), view=view)
            await self.bot.temp_voice_mgr.update_control_message(new_channel.id, panel_msg.id)

        except discord.HTTPException as e:
            logger.error(f"Failed to create temp voice channel in guild {guild.id}: {e}", exc_info=e)

    async def _handle_temp_channel_leave(self, channel: discord.VoiceChannel, member: discord.Member) -> None:
        """Auto-delete channel when empty or notify if host leaves."""
        # Wait a split second to ensure Discord Gateway state stabilizes
        await asyncio.sleep(1.0)

        # Re-fetch members in the channel
        current_members = channel.members

        if len(current_members) == 0:
            # Channel is completely empty -> delete immediately
            try:
                await channel.delete(reason="Temporary voice channel is empty")
            except discord.NotFound:
                pass
            except Exception as e:
                logger.debug(f"Notice deleting temp channel {channel.id}: {e}")

            await self.bot.temp_voice_mgr.unregister_temp_channel(channel.id)
        else:
            # Channel still has members, check if leaving member was the host
            data = self.bot.temp_voice_mgr.get_channel_data(channel.id)
            if data and data.get("owner_id") == member.id:
                try:
                    await channel.send(
                        f"**Host Left**: {member.mention} has disconnected. Any connected member can click **Claim Room** on the control panel to become the new host!"
                    )
                except Exception:
                    pass

    # ─── SLASH COMMANDS ───────────────────────────────────────────────────────

    tempvoice_group = app_commands.Group(name="tempvoice", description="Manage dynamic Join-to-Create temporary voice channels")

    @tempvoice_group.command(name="setup", description="Initialize Join-to-Create master channel in this server")
    @app_commands.describe(
        category="Category where temporary rooms should be created",
        name_format="Template for room names (e.g. {user}'s Room)",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def tempvoice_setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        name_format: Optional[str] = "{user}'s Room",
    ) -> None:
        """Create master Join-to-Create channel and persist configuration."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        try:
            # Create the master channel inside the selected category
            master = await guild.create_voice_channel(
                name="➕ Join to Create",
                category=category,
                reason=f"Master temp voice channel configured by {interaction.user}",
            )

            await self.bot.temp_voice_mgr.set_settings(
                guild_id=guild.id,
                category_id=category.id,
                master_channel_id=master.id,
                default_name_format=name_format or "{user}'s Room",
            )

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"### Dynamic Temp Voice Configured\n"
                    f"> Members can now join {master.mention} to instantly spawn their own private voice room."
                )
            )
            container.add_separator(divider=True)
            container.add_field("Category", category.name, inline=True)
            container.add_field("Master Channel", master.name, inline=True)
            container.add_field("Naming Format", name_format or "{user}'s Room", inline=True)

            await interaction.followup.send(embed=container.to_embed(), ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"Failed to setup temp voice system: {e}", ephemeral=True)

    @tempvoice_group.command(name="panel", description="Resend the interactive control panel in your current temp room")
    async def tempvoice_panel(self, interaction: discord.Interaction) -> None:
        """Resend control panel if it got lost in chat."""
        if not isinstance(interaction.user, discord.Member) or not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("You must be connected to a temporary voice room to use this command.", ephemeral=True)
            return

        channel = interaction.user.voice.channel
        if not self.bot.temp_voice_mgr.is_temp_channel(channel.id):
            await interaction.response.send_message("Your current voice channel is not an active temporary room.", ephemeral=True)
            return

        data = self.bot.temp_voice_mgr.get_channel_data(channel.id)
        if not data:
            return

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### {channel.name} Control Panel\n"
                f"> Use the buttons below to manage your room."
            )
        )
        container.add_separator(divider=True)
        container.add_field("Host", f"<@{data['owner_id']}>", inline=True)
        container.add_field("Status", "Locked" if data.get("is_locked") else "Unlocked", inline=True)
        container.add_field("Visibility", "Hidden" if data.get("is_hidden") else "Visible", inline=True)

        view = TempVoiceControlView(self.bot, channel.id)
        await interaction.response.send_message(embed=container.to_embed(), view=view)

    @tempvoice_group.command(name="disable", description="Disable Join-to-Create temporary voice system")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def tempvoice_disable(self, interaction: discord.Interaction) -> None:
        """Deactivate temp voice system for guild."""
        if not interaction.guild:
            return

        await self.bot.temp_voice_mgr.disable_settings(interaction.guild.id)
        await interaction.response.send_message(
            "**Temp Voice Disabled**: Dynamic voice channel generation has been turned off for this server.",
            ephemeral=True,
        )


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(TempVoice(bot))
