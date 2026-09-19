"""
Kyro Discord Bot - Dynamic Temp Voice Cog (/vc setup j2c)
Provides Join-to-Create voice infrastructure with automated channel generation and a permanent Master Interface Dashboard.
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


class TempVoiceLimitModal(discord.ui.Modal, title="Set Member Limit"):
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


# ─── SELECT MENUS FOR MEMBER MANAGEMENT ───────────────────────────────────────

class TrustMemberView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__(timeout=60)
        self.channel = channel

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select a friend to permit/trust in your room")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect) -> None:
        if not select.values:
            return
        target = select.values[0]
        try:
            await self.channel.set_permissions(target, connect=True, view_channel=True)
            await interaction.response.send_message(
                f"**Member Trusted**: {target.mention} can now join your room even when locked.",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to permit member: {e}", ephemeral=True)


class BlockMemberView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__(timeout=60)
        self.channel = channel

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select an unwanted member to kick and block")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect) -> None:
        if not select.values:
            return
        target = select.values[0]
        try:
            await self.channel.set_permissions(target, connect=False, view_channel=False)
            # If target is currently inside the channel, disconnect them
            if isinstance(target, discord.Member) and target.voice and target.voice.channel == self.channel:
                await target.move_to(None, reason="Blocked from room by host")
            await interaction.response.send_message(
                f"**Member Blocked**: {target.mention} has been disconnected and blocked from your room.",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to block member: {e}", ephemeral=True)


class TransferHostView(discord.ui.View):
    def __init__(self, bot: KyroBot, channel: discord.VoiceChannel) -> None:
        super().__init__(timeout=60)
        self.bot = bot
        self.channel = channel

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Select a member to transfer room ownership to")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect) -> None:
        if not select.values:
            return
        new_host = select.values[0]
        if new_host.bot:
            await interaction.response.send_message("You cannot transfer ownership to a bot.", ephemeral=True)
            return

        await self.bot.temp_voice_mgr.transfer_ownership(self.channel.id, new_host.id)
        try:
            await self.channel.set_permissions(
                new_host,
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
            f"**Host Transferred**: {new_host.mention} is now the host of **{self.channel.name}**!",
            ephemeral=False,
        )


class BitrateQualityView(discord.ui.View):
    def __init__(self, channel: discord.VoiceChannel) -> None:
        super().__init__(timeout=60)
        self.channel = channel

    @discord.ui.select(
        placeholder="Choose audio bitrate quality",
        options=[
            discord.SelectOption(label="Normal Voice (64 kbps)", value="64000", description="Clean bandwidth-efficient audio"),
            discord.SelectOption(label="High Fidelity (96 kbps)", value="96000", description="Crisp vocal clarity"),
            discord.SelectOption(label="Music / Studio (128 kbps)", value="128000", description="Lossless gaming and music streaming"),
            discord.SelectOption(label="Pro Audio (256 kbps)", value="256000", description="Requires Server Boost Level 2"),
            discord.SelectOption(label="Mastering Tier (384 kbps)", value="384000", description="Requires Server Boost Level 3"),
        ]
    )
    async def select_bitrate(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        val = int(select.values[0])
        max_bitrate = interaction.guild.bitrate_limit if interaction.guild else 96000
        target_bitrate = min(val, max_bitrate)

        try:
            await self.channel.edit(bitrate=target_bitrate, reason=f"Bitrate adjusted by {interaction.user}")
            kbps = target_bitrate // 1000
            await interaction.response.send_message(f"**Audio Bitrate Set**: Audio streaming quality is now **{kbps} kbps**.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to set bitrate: {e}", ephemeral=True)


# ─── MASTER INTERFACE & ROOM VIEW ─────────────────────────────────────────────

class PersistentVoiceMasterView(discord.ui.View):
    """
    Master Interface Dashboard View that controls the user's active temporary room.
    Functions dynamically whether clicked from #voice-control or inside the room's text chat.
    """

    def __init__(self, bot: KyroBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    async def _resolve_room_for_interaction(self, interaction: discord.Interaction) -> tuple[Optional[discord.VoiceChannel], Optional[dict]]:
        """Resolve which voice room the interacting user owns or is in."""
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return None, None

        # 1. Check if user owns an active room in this guild
        owned_cid = self.bot.temp_voice_mgr.get_active_room_for_user(guild.id, interaction.user.id)
        target_cid = owned_cid

        # 2. If not owned, check if they are currently inside an active temp room
        if not target_cid and isinstance(interaction.user, discord.Member) and interaction.user.voice and interaction.user.voice.channel:
            if self.bot.temp_voice_mgr.is_temp_channel(interaction.user.voice.channel.id):
                target_cid = interaction.user.voice.channel.id

        if not target_cid:
            master_id = None
            settings = self.bot.temp_voice_mgr.get_settings(guild.id)
            if settings:
                master_id = settings.get("master_channel_id")
            master_mention = f"<#{master_id}>" if master_id else "Join to Create"
            await interaction.response.send_message(
                f"You do not have an active temporary voice channel!\n"
                f"> Join {master_mention} to spawn your private room first.",
                ephemeral=True,
            )
            return None, None

        channel = guild.get_channel(target_cid)
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("Your voice channel could not be found.", ephemeral=True)
            return None, None

        data = self.bot.temp_voice_mgr.get_channel_data(target_cid)
        return channel, data

    async def _verify_owner(self, interaction: discord.Interaction, channel: discord.VoiceChannel, data: dict) -> bool:
        is_owner = interaction.user.id == data["owner_id"]
        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_channels

        if not is_owner and not is_admin:
            await interaction.response.send_message(
                f"Only the room host (<@{data['owner_id']}>) can perform this action.",
                ephemeral=True,
            )
            return False
        return True

    # ── ROW 0: PRIVACY & CAPACITY ──

    @discord.ui.button(label="Lock", style=discord.ButtonStyle.primary, custom_id="pvm_lock", emoji="🔒", row=0)
    async def btn_lock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return

        try:
            await channel.set_permissions(interaction.guild.default_role, connect=False)
            for m in channel.members:
                await channel.set_permissions(m, connect=True)
            await self.bot.temp_voice_mgr.update_channel_state(channel.id, is_locked=True)
            await interaction.response.send_message(f"**Room Locked**: **{channel.name}** is now private.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to lock room: {e}", ephemeral=True)

    @discord.ui.button(label="Unlock", style=discord.ButtonStyle.secondary, custom_id="pvm_unlock", emoji="🔓", row=0)
    async def btn_unlock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return

        try:
            await channel.set_permissions(interaction.guild.default_role, connect=None)
            await self.bot.temp_voice_mgr.update_channel_state(channel.id, is_locked=False)
            await interaction.response.send_message(f"**Room Unlocked**: **{channel.name}** is now open to everyone.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to unlock room: {e}", ephemeral=True)

    @discord.ui.button(label="Ghost", style=discord.ButtonStyle.secondary, custom_id="pvm_hide", emoji="👁️", row=0)
    async def btn_hide(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return

        try:
            await channel.set_permissions(interaction.guild.default_role, view_channel=False)
            for m in channel.members:
                await channel.set_permissions(m, view_channel=True)
            await self.bot.temp_voice_mgr.update_channel_state(channel.id, is_hidden=True)
            await interaction.response.send_message(f"**Room Hidden**: **{channel.name}** is now invisible on the channel list.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to hide room: {e}", ephemeral=True)

    @discord.ui.button(label="Unhide", style=discord.ButtonStyle.secondary, custom_id="pvm_unhide", emoji="👀", row=0)
    async def btn_unhide(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return

        try:
            await channel.set_permissions(interaction.guild.default_role, view_channel=None)
            await self.bot.temp_voice_mgr.update_channel_state(channel.id, is_hidden=False)
            await interaction.response.send_message(f"**Room Visible**: **{channel.name}** is now visible in the channel list.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to unhide room: {e}", ephemeral=True)

    @discord.ui.button(label="Limit", style=discord.ButtonStyle.secondary, custom_id="pvm_limit", emoji="👥", row=0)
    async def btn_limit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return
        await interaction.response.send_modal(TempVoiceLimitModal(channel))

    # ── ROW 1: PERSONALIZATION & MEMBERS ──

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.secondary, custom_id="pvm_rename", emoji="✏️", row=1)
    async def btn_rename(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return
        await interaction.response.send_modal(TempVoiceRenameModal(channel))

    @discord.ui.button(label="Permit", style=discord.ButtonStyle.success, custom_id="pvm_permit", emoji="⭐", row=1)
    async def btn_permit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return
        view = TrustMemberView(channel)
        await interaction.response.send_message("**Trust / Permit a Member:**", view=view, ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger, custom_id="pvm_block", emoji="🚫", row=1)
    async def btn_block(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return
        view = BlockMemberView(channel)
        await interaction.response.send_message("**Kick and Block a Member:**", view=view, ephemeral=True)

    @discord.ui.button(label="Transfer", style=discord.ButtonStyle.secondary, custom_id="pvm_transfer", emoji="👑", row=1)
    async def btn_transfer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return
        view = TransferHostView(self.bot, channel)
        await interaction.response.send_message("**Transfer Room Ownership:**", view=view, ephemeral=True)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, custom_id="pvm_claim", emoji="🏆", row=1)
    async def btn_claim(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data:
            return

        current_owner_id = data["owner_id"]
        # Check if current owner is still connected
        owner_connected = any(m.id == current_owner_id for m in channel.members)
        if owner_connected and interaction.user.id != current_owner_id:
            await interaction.response.send_message(
                f"The current host (<@{current_owner_id}>) is still connected in **{channel.name}**.",
                ephemeral=True,
            )
            return

        await self.bot.temp_voice_mgr.transfer_ownership(channel.id, interaction.user.id)
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
            f"**Room Claimed**: {interaction.user.mention} is now the host of **{channel.name}**!",
            ephemeral=False,
        )

    # ── ROW 2: QUALITY & SESSION ──

    @discord.ui.button(label="Bitrate Quality", style=discord.ButtonStyle.secondary, custom_id="pvm_bitrate", emoji="🎧", row=2)
    async def btn_bitrate(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return
        view = BitrateQualityView(channel)
        await interaction.response.send_message("**Adjust Audio Bitrate Quality:**", view=view, ephemeral=True)

    @discord.ui.button(label="Delete Room", style=discord.ButtonStyle.danger, custom_id="pvm_delete", emoji="🗑️", row=2)
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return

        await interaction.response.send_message(f"**Closing Room**: Deleting **{channel.name}**...", ephemeral=True)
        try:
            await channel.delete(reason=f"Temp voice deleted manually by host {interaction.user}")
        except Exception:
            pass
        await self.bot.temp_voice_mgr.unregister_temp_channel(channel.id)


# ─── COG IMPLEMENTATION ───────────────────────────────────────────────────────

class TempVoice(commands.Cog):
    """Dynamic Join-to-Create voice system (/vc setup j2c)."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # Register persistent view so buttons work across restarts
        self.bot.add_view(PersistentVoiceMasterView(self.bot))

    async def cog_load(self) -> None:
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
                await self.bot.temp_voice_mgr.unregister_temp_channel(cid)
                purged_count += 1
            elif len(channel.members) == 0:
                try:
                    await channel.delete(reason="Purging empty temp voice channel on startup")
                except Exception:
                    pass
                await self.bot.temp_voice_mgr.unregister_temp_channel(cid)
                purged_count += 1

        if purged_count > 0:
            logger.info(f"Audited and cleaned up {purged_count} empty temp voice channel(s).")

    # ─── VOICE STATE LISTENER ─────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Monitor voice joins and leaves for J2C generation and destruction."""
        if member.bot:
            return

        # Member joined master channel
        if after.channel is not None and (before.channel is None or before.channel.id != after.channel.id):
            guild_id = self.bot.temp_voice_mgr.get_guild_by_master(after.channel.id)
            if guild_id and guild_id == member.guild.id:
                await self._handle_join_to_create(member, after.channel)

        # Member left a temporary room
        if before.channel is not None and (after.channel is None or before.channel.id != after.channel.id):
            if self.bot.temp_voice_mgr.is_temp_channel(before.channel.id):
                await self._handle_temp_channel_leave(before.channel, member)

    async def _handle_join_to_create(self, member: discord.Member, master_channel: discord.VoiceChannel) -> None:
        """Create private room, move user, and post in-room panel."""
        guild = member.guild
        settings = self.bot.temp_voice_mgr.get_settings(guild.id)
        if not settings:
            return

        category = guild.get_channel(settings["category_id"])
        if not isinstance(category, discord.CategoryChannel):
            category = master_channel.category

        name_fmt = settings.get("default_name_format") or "{user}'s Room"
        channel_name = f"🔊 {name_fmt.replace('{user}', member.display_name)}"

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
            new_channel = await guild.create_voice_channel(
                name=channel_name,
                category=category,
                user_limit=settings.get("default_user_limit", 0),
                overwrites=overwrites,
                reason=f"Dynamic J2C room requested by {member}",
            )

            await member.move_to(new_channel, reason="Moved to newly created J2C room")
            await self.bot.temp_voice_mgr.register_temp_channel(new_channel.id, guild.id, member.id)

            # In-Room Control Card
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"### {channel_name}\n"
                    f"> Welcome {member.mention}! You are the host of this room.\n"
                    f"> Use the buttons below or the master interface channel to manage your room."
                )
            )
            container.add_separator(divider=True)
            container.add_field("Host", member.mention, inline=True)
            container.add_field("Status", "Unlocked", inline=True)
            container.add_field("Auto-Delete", "When Empty", inline=True)

            view = PersistentVoiceMasterView(self.bot)
            panel_msg = await new_channel.send(embed=container.to_embed(), view=view)
            await self.bot.temp_voice_mgr.update_control_message(new_channel.id, panel_msg.id)

        except discord.HTTPException as e:
            logger.error(f"Failed creating J2C room in guild {guild.id}: {e}", exc_info=e)

    async def _handle_temp_channel_leave(self, channel: discord.VoiceChannel, member: discord.Member) -> None:
        """Clean up empty room or alert if host leaves."""
        await asyncio.sleep(1.0)
        current_members = channel.members

        if len(current_members) == 0:
            try:
                await channel.delete(reason="J2C temporary room is empty")
            except Exception:
                pass
            await self.bot.temp_voice_mgr.unregister_temp_channel(channel.id)
        else:
            data = self.bot.temp_voice_mgr.get_channel_data(channel.id)
            if data and data.get("owner_id") == member.id:
                try:
                    await channel.send(
                        f"**Host Left**: {member.mention} has left. Any remaining member can click **Claim** on the control panel to become the new host!"
                    )
                except Exception:
                    pass

    # ─── SLASH COMMAND: /vc setup [type: j2c] ─────────────────────────────────

    vc_group = app_commands.Group(name="vc", description="Voice channel management and configuration")

    @vc_group.command(name="setup", description="Setup voice infrastructure (J2C Join-to-Create)")
    @app_commands.describe(
        type="Voice system type to configure",
        category_name="Optional custom category name (default: 🔊 Custom Voice)",
        voice_name="Optional custom master channel name (default: ➕ Join to Create)",
        interface_name="Optional custom control channel name (default: 🎛️・voice-control)",
    )
    @app_commands.choices(
        type=[
            app_commands.Choice(name="Join to Create (J2C)", value="j2c"),
        ]
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def vc_setup(
        self,
        interaction: discord.Interaction,
        type: Optional[app_commands.Choice[str]] = None,
        category_name: Optional[str] = "🔊 Custom Voice",
        voice_name: Optional[str] = "➕ Join to Create",
        interface_name: Optional[str] = "🎛️・voice-control",
    ) -> None:
        """Automated J2C infrastructure generator."""
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if not guild:
            return

        chosen_type = type.value if type else "j2c"
        if chosen_type != "j2c":
            await interaction.followup.send("Unsupported voice system type.", ephemeral=True)
            return

        cat_title = category_name.strip() if category_name else "🔊 Custom Voice"
        v_title = voice_name.strip() if voice_name else "➕ Join to Create"
        i_title = interface_name.strip() if interface_name else "🎛️・voice-control"

        try:
            # 1. Create Category
            category = await guild.create_category(name=cat_title, reason=f"J2C setup by {interaction.user}")

            # 2. Create Master Voice Channel
            master_channel = await guild.create_voice_channel(
                name=v_title,
                category=category,
                reason=f"J2C master channel by {interaction.user}",
            )

            # 3. Create Interface Text Channel (Read-only for @everyone, but button clicks allowed)
            interface_overwrites: dict[Any, discord.PermissionOverwrite] = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    read_message_history=True,
                    send_messages=False,
                    add_reactions=False,
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    embed_links=True,
                    manage_messages=True,
                ),
            }

            interface_channel = await guild.create_text_channel(
                name=i_title,
                category=category,
                overwrites=interface_overwrites,
                reason=f"J2C interface channel by {interaction.user}",
            )

            # 4. Post the Master Interface Dashboard
            dashboard_container = KyroContainer(accent_color=None)
            dashboard_container.add_section(
                content=(
                    f"### 🎛️ Voice Master Control Dashboard\n"
                    f"> Welcome to the server's central voice customization interface.\n"
                    f"> Click any button below to manage your active temporary voice room in real time.\n\n"
                    f"**Quick Instructions:**\n"
                    f"1. Join {master_channel.mention} to automatically spawn your personal room.\n"
                    f"2. Use the controls below to lock, hide, rename, limit, permit friends, or kick unwanted members.\n"
                    f"3. When all members disconnect, your room will automatically delete itself."
                )
            )
            dashboard_container.add_separator(divider=True)
            dashboard_container.add_field("Access Controls", "🔒 Lock • 🔓 Unlock • 👁️ Ghost • 👀 Unhide • 👥 Limit", inline=False)
            dashboard_container.add_field("Customization", "✏️ Rename • ⭐ Permit • 🚫 Block • 👑 Transfer • 🏆 Claim", inline=False)
            dashboard_container.add_field("Audio & Session", "🎧 Quality Bitrate • 🗑️ Delete Room", inline=False)

            view = PersistentVoiceMasterView(self.bot)
            master_msg = await interface_channel.send(embed=dashboard_container.to_embed(), view=view)

            # 5. Save Configuration to Database and Cache
            await self.bot.temp_voice_mgr.set_settings(
                guild_id=guild.id,
                category_id=category.id,
                master_channel_id=master_channel.id,
                interface_channel_id=interface_channel.id,
                interface_message_id=master_msg.id,
            )

            # 6. Respond with Success Card to Administrator
            resp_container = KyroContainer(accent_color=None)
            resp_container.add_section(
                content=(
                    f"### Join to Create (J2C) Configured Successfully!\n"
                    f"> The complete temporary voice infrastructure has been deployed."
                )
            )
            resp_container.add_separator(divider=True)
            resp_container.add_field("Category", category.name, inline=True)
            resp_container.add_field("Master Voice", master_channel.mention, inline=True)
            resp_container.add_field("Interface Channel", interface_channel.mention, inline=True)

            await interaction.followup.send(embed=resp_container.to_embed(), ephemeral=True)

        except discord.HTTPException as e:
            await interaction.followup.send(f"Failed to setup voice infrastructure: {e}", ephemeral=True)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(TempVoice(bot))
