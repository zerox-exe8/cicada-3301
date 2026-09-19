"""
Kyro Discord Bot - Dynamic Temp Voice Cog (/vc setup j2c)
Provides Join-to-Create voice infrastructure with automated channel generation and a permanent Master Interface Dashboard.
"""

from __future__ import annotations

import asyncio
import logging
import time
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

    def __init__(self, bot: KyroBot, channel: discord.VoiceChannel) -> None:
        super().__init__()
        self.bot = bot
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name = self.new_name.value.strip()
        cog = self.bot.get_cog("TempVoice")
        if cog and hasattr(cog, "is_rename_rate_limited") and cog.is_rename_rate_limited(self.channel.id):
            c = KyroContainer(accent_color=None)
            c.add_section(
                "### Rate Limit Protected\n"
                "> Discord allows renaming a voice room only twice every 10 minutes.\n"
                "> Please wait a few minutes before renaming again."
            )
            await send_container_response(interaction, c, ephemeral=True)
            return

        try:
            await self.channel.edit(name=name, reason=f"Temp voice renamed by {interaction.user}")
            if cog and hasattr(cog, "mark_custom_renamed"):
                cog.mark_custom_renamed(self.channel.id)
            c = KyroContainer(accent_color=None)
            c.add_section(f"**Room Renamed**\n> Voice channel updated to **{name}**.")
            await send_container_response(interaction, c, ephemeral=True)
        except discord.HTTPException as e:
            c = KyroContainer(accent_color=None)
            c.add_section(f"**Error**: Failed to rename channel: {e}")
            await send_container_response(interaction, c, ephemeral=True)


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
            c = KyroContainer(accent_color=None)
            c.add_section("**Invalid Input**: Please enter a valid number between 0 and 99.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        lim = int(raw_val)
        try:
            await self.channel.edit(user_limit=lim, reason=f"Temp voice limit changed by {interaction.user}")
            desc = "Unlimited" if lim == 0 else f"{lim} members"
            c = KyroContainer(accent_color=None)
            c.add_section(f"**Limit Updated**\n> Room capacity set to **{desc}**.")
            await send_container_response(interaction, c, ephemeral=True)
        except discord.HTTPException as e:
            c = KyroContainer(accent_color=None)
            c.add_section(f"**Error**: Failed to update limit: {e}")
            await send_container_response(interaction, c, ephemeral=True)


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
            c = KyroContainer(accent_color=None)
            c.add_section(f"**Member Permitted**\n> {target.mention} can now join your room even when locked.")
            await send_container_response(interaction, c, ephemeral=True)
        except discord.HTTPException as e:
            c = KyroContainer(accent_color=None)
            c.add_section(f"**Error**: Failed to permit member: {e}")
            await send_container_response(interaction, c, ephemeral=True)


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
            if isinstance(target, discord.Member) and target.voice and target.voice.channel == self.channel:
                await target.move_to(None, reason="Blocked from room by host")
            c = KyroContainer(accent_color=None)
            c.add_section(f"**Member Blocked**\n> {target.mention} has been disconnected and blocked from your room.")
            await send_container_response(interaction, c, ephemeral=True)
        except discord.HTTPException as e:
            c = KyroContainer(accent_color=None)
            c.add_section(f"**Error**: Failed to block member: {e}")
            await send_container_response(interaction, c, ephemeral=True)


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
            c = KyroContainer(accent_color=None)
            c.add_section("**Error**: You cannot transfer room ownership to a bot.")
            await send_container_response(interaction, c, ephemeral=True)
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

        c = KyroContainer(accent_color=None)
        c.add_section(f"**Host Transferred**\n> {new_host.mention} is now the host of **{self.channel.name}**!")
        await send_container_response(interaction, c, ephemeral=False)


# ─── MASTER INTERFACE & ROOM VIEW ─────────────────────────────────────────────

class PersistentVoiceMasterView(discord.ui.View):
    """
    Master Interface Dashboard View that controls the user's active temporary room.
    Functions dynamically whether clicked from #voice-control or inside the room's text chat.
    """

    def __init__(self, bot: KyroBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    async def _send_card(
        self,
        interaction: discord.Interaction,
        title: str,
        description: str,
        view: Optional[discord.ui.View] = None,
        ephemeral: bool = True,
    ) -> None:
        """Send a clean KyroContainer card for all button interactions."""
        container = KyroContainer(accent_color=None)
        container.add_section(f"**{title}**\n> {description}")
        await send_container_response(interaction, container, view=view, ephemeral=ephemeral)

    async def _resolve_room_for_interaction(self, interaction: discord.Interaction) -> tuple[Optional[discord.VoiceChannel], Optional[dict]]:
        """Resolve which voice room the interacting user owns or is in."""
        guild = interaction.guild
        if not guild:
            await self._send_card(interaction, "Server Only", "This command can only be used in a server.", ephemeral=True)
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
            await self._send_card(
                interaction,
                "No Active Room",
                f"You do not have an active temporary voice channel.\n> Join {master_mention} to spawn your private room first.",
                ephemeral=True,
            )
            return None, None

        channel = guild.get_channel(target_cid)
        if not isinstance(channel, discord.VoiceChannel):
            await self._send_card(interaction, "Room Not Found", "Your voice channel could not be found.", ephemeral=True)
            return None, None

        data = self.bot.temp_voice_mgr.get_channel_data(target_cid)
        return channel, data

    async def _verify_owner(self, interaction: discord.Interaction, channel: discord.VoiceChannel, data: dict) -> bool:
        is_owner = interaction.user.id == data["owner_id"]
        is_admin = False
        if isinstance(interaction.user, discord.Member):
            is_admin = interaction.user.guild_permissions.administrator or interaction.user.guild_permissions.manage_channels

        if not is_owner and not is_admin:
            await self._send_card(
                interaction,
                "Access Denied",
                f"Only the room host (<@{data['owner_id']}>) can perform this action.",
                ephemeral=True,
            )
            return False
        return True

    # ── ROW 0: PRIVACY & CAPACITY ──

    @discord.ui.button(label="Lock", style=discord.ButtonStyle.secondary, custom_id="pvm_lock", row=0)
    async def btn_lock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return

        try:
            await channel.set_permissions(interaction.guild.default_role, connect=False)
            for m in channel.members:
                await channel.set_permissions(m, connect=True)
            await self.bot.temp_voice_mgr.update_channel_state(channel.id, is_locked=True)
            await self._send_card(interaction, "Room Locked", f"**{channel.name}** is now private. Only permitted members can join.")
        except discord.HTTPException as e:
            await self._send_card(interaction, "Error", f"Failed to lock room: {e}")

    @discord.ui.button(label="Unlock", style=discord.ButtonStyle.secondary, custom_id="pvm_unlock", row=0)
    async def btn_unlock(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return

        try:
            await channel.set_permissions(interaction.guild.default_role, connect=None)
            await self.bot.temp_voice_mgr.update_channel_state(channel.id, is_locked=False)
            await self._send_card(interaction, "Room Unlocked", f"**{channel.name}** is now open to everyone.")
        except discord.HTTPException as e:
            await self._send_card(interaction, "Error", f"Failed to unlock room: {e}")

    @discord.ui.button(label="Hide", style=discord.ButtonStyle.secondary, custom_id="pvm_hide", row=0)
    async def btn_hide(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return

        try:
            await channel.set_permissions(interaction.guild.default_role, view_channel=False)
            for m in channel.members:
                await channel.set_permissions(m, view_channel=True)
            await self.bot.temp_voice_mgr.update_channel_state(channel.id, is_hidden=True)
            await self._send_card(interaction, "Room Hidden", f"**{channel.name}** is now invisible on the channel list.")
        except discord.HTTPException as e:
            await self._send_card(interaction, "Error", f"Failed to hide room: {e}")

    @discord.ui.button(label="Unhide", style=discord.ButtonStyle.secondary, custom_id="pvm_unhide", row=0)
    async def btn_unhide(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return

        try:
            await channel.set_permissions(interaction.guild.default_role, view_channel=None)
            await self.bot.temp_voice_mgr.update_channel_state(channel.id, is_hidden=False)
            await self._send_card(interaction, "Room Visible", f"**{channel.name}** is now visible in the channel list.")
        except discord.HTTPException as e:
            await self._send_card(interaction, "Error", f"Failed to unhide room: {e}")

    @discord.ui.button(label="Limit", style=discord.ButtonStyle.secondary, custom_id="pvm_limit", row=0)
    async def btn_limit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return
        await interaction.response.send_modal(TempVoiceLimitModal(channel))

    # ── ROW 1: CONTROLS & QUALITY ──

    @discord.ui.button(label="Rename", style=discord.ButtonStyle.secondary, custom_id="pvm_rename", row=1)
    async def btn_rename(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return
        await interaction.response.send_modal(TempVoiceRenameModal(self.bot, channel))

    @discord.ui.button(label="Permit", style=discord.ButtonStyle.secondary, custom_id="pvm_permit", row=1)
    async def btn_permit(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return
        view = TrustMemberView(channel)
        container = KyroContainer(accent_color=None)
        container.add_section(
            "### Permit Member\n"
            "> Select a friend from the menu below to grant room access even when locked."
        )
        await send_container_response(interaction, container, view=view, ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.secondary, custom_id="pvm_block", row=1)
    async def btn_block(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return
        view = BlockMemberView(channel)
        container = KyroContainer(accent_color=None)
        container.add_section(
            "### Reject Member\n"
            "> Select an unwanted user from the menu below to disconnect and block them."
        )
        await send_container_response(interaction, container, view=view, ephemeral=True)

    @discord.ui.button(label="Transfer", style=discord.ButtonStyle.secondary, custom_id="pvm_transfer", row=1)
    async def btn_transfer(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return
        view = TransferHostView(self.bot, channel)
        container = KyroContainer(accent_color=None)
        container.add_section(
            "### Transfer Host\n"
            "> Select a member from the menu below to transfer room ownership."
        )
        await send_container_response(interaction, container, view=view, ephemeral=True)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, custom_id="pvm_delete", row=1)
    async def btn_delete(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        channel, data = await self._resolve_room_for_interaction(interaction)
        if not channel or not data or not await self._verify_owner(interaction, channel, data):
            return

        await self._send_card(interaction, "Closing Room", f"Deleting **{channel.name}**...")
        try:
            await channel.delete(reason=f"Temp voice deleted manually by host {interaction.user}")
        except Exception:
            pass
        await self.bot.temp_voice_mgr.unregister_temp_channel(channel.id)


# ─── COG IMPLEMENTATION ───────────────────────────────────────────────────────

class TempVoice(commands.Cog):
    """Dynamic Join-to-Create voice system (/vc setup j2c)."""
    category: str = "Join to Create"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # Anti-spam cooldown and in-flight creation tracking
        self._creation_cooldowns: dict[int, float] = {}
        self._creating_users: set[int] = set()
        # Custom renamed rooms and rate-limit tracking for dynamic renames
        self._custom_renamed_rooms: set[int] = set()
        self._last_channel_renames: dict[int, float] = {}
        # Register persistent view so buttons work across restarts
        self.bot.add_view(PersistentVoiceMasterView(self.bot))

    def is_rename_rate_limited(self, channel_id: int) -> bool:
        """Check if channel rename is rate-limited (Discord allows 2 edits per 10 mins)."""
        last = self._last_channel_renames.get(channel_id, 0.0)
        return (time.time() - last) < 300.0

    def mark_custom_renamed(self, channel_id: int) -> None:
        """Track that the host gave a custom topic so automatic renames don't override it."""
        self._custom_renamed_rooms.add(channel_id)
        self._last_channel_renames[channel_id] = time.time()

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
        """Create private room, move user, and post in-room panel with anti-spam protection."""
        guild = member.guild
        settings = self.bot.temp_voice_mgr.get_settings(guild.id)
        if not settings:
            return

        # 1. Anti-Spam: In-flight creation lock (prevents duplicate triggers)
        if member.id in self._creating_users:
            return

        # 2. Existing Room Check: If user already owns an active room in this guild, move them there
        existing_cid = self.bot.temp_voice_mgr.get_active_room_for_user(guild.id, member.id)
        if existing_cid:
            existing_channel = guild.get_channel(existing_cid)
            if isinstance(existing_channel, discord.VoiceChannel):
                try:
                    await member.move_to(existing_channel, reason="User already owns an active J2C room")
                except discord.HTTPException:
                    pass
                return

        # 3. Anti-Spam Rate Limit: 5-second cooldown between creation attempts
        now = time.time()
        last_created = self._creation_cooldowns.get(member.id, 0.0)
        if now - last_created < 5.0:
            try:
                await member.move_to(None, reason="J2C rapid creation cooldown active")
            except discord.HTTPException:
                pass
            return

        self._creating_users.add(member.id)
        self._creation_cooldowns[member.id] = now

        category = guild.get_channel(settings["category_id"])
        if not isinstance(category, discord.CategoryChannel):
            category = master_channel.category

        name_fmt = settings.get("default_name_format") or "{user}'s Room"
        channel_name = name_fmt.replace("{user}", member.display_name.strip()).strip()

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

        except discord.HTTPException as e:
            logger.error(f"Failed creating J2C room in guild {guild.id}: {e}", exc_info=e)
        finally:
            self._creating_users.discard(member.id)

    async def _handle_temp_channel_leave(self, channel: discord.VoiceChannel, member: discord.Member) -> None:
        """Clean up empty room or transfer ownership and rename if host leaves."""
        await asyncio.sleep(1.5)

        # Re-fetch channel to verify it still exists in the guild
        guild = channel.guild
        current_channel = guild.get_channel(channel.id)
        if not current_channel or not isinstance(current_channel, discord.VoiceChannel):
            await self.bot.temp_voice_mgr.unregister_temp_channel(channel.id)
            self._custom_renamed_rooms.discard(channel.id)
            self._last_channel_renames.pop(channel.id, None)
            return

        current_members = [m for m in current_channel.members if not m.bot]

        # Scenario A: Room is completely empty
        if len(current_members) == 0:
            try:
                await current_channel.delete(reason="J2C temporary room is empty")
            except Exception:
                pass
            await self.bot.temp_voice_mgr.unregister_temp_channel(channel.id)
            self._custom_renamed_rooms.discard(channel.id)
            self._last_channel_renames.pop(channel.id, None)
            return

        # Scenario B: Host left, but members are still inside
        data = self.bot.temp_voice_mgr.get_channel_data(channel.id)
        if data and data.get("owner_id") == member.id:
            new_host = current_members[0]
            await self.bot.temp_voice_mgr.transfer_ownership(channel.id, new_host.id)

            # Assign elevated permissions to new host
            try:
                await current_channel.set_permissions(
                    new_host,
                    connect=True,
                    speak=True,
                    stream=True,
                    move_members=True,
                    mute_members=True,
                    deafen_members=True,
                    manage_channels=True,
                )
            except discord.HTTPException:
                pass

            # Smart Dynamic Rename: Only if channel was not custom-renamed by original host
            renamed = False
            new_name = None
            if channel.id not in self._custom_renamed_rooms:
                settings = self.bot.temp_voice_mgr.get_settings(guild.id)
                name_fmt = settings.get("default_name_format") or "{user}'s Room" if settings else "{user}'s Room"
                new_name = name_fmt.replace("{user}", new_host.display_name.strip()).strip()

                last_rename = self._last_channel_renames.get(channel.id, 0.0)
                if (time.time() - last_rename) >= 300.0:
                    try:
                        await current_channel.edit(name=new_name, reason=f"Host transferred to {new_host}")
                        self._last_channel_renames[channel.id] = time.time()
                        renamed = True
                    except discord.HTTPException as e:
                        logger.warning(f"Could not rename channel {channel.id} due to rate limit: {e}")

            # Notify in room text chat
            try:
                msg = f"**Host Transferred**: {member.mention} has left. {new_host.mention} is now the host of this room!"
                if renamed and new_name:
                    msg += f"\n> Room name updated to **{new_name}**."
                await current_channel.send(msg)
            except Exception:
                pass

    # ─── HYBRID COMMAND: /j2c ─────────────────────────────────────────────────
    @commands.hybrid_command(
        name="j2c",
        aliases=["jointocreate", "join-to-create"],
        description="Setup Join-to-Create voice infrastructure with automated channel generator and control dashboard.",
    )
    @app_commands.describe(
        category_name="Optional custom category name (default: Custom Voice)",
        voice_name="Optional custom master channel name (default: Join to Create)",
        interface_name="Optional custom control channel name (default: Interface)",
        reset="Reset and clean recreate existing J2C infrastructure if already configured (default: False)",
    )
    @commands.cooldown(1, 10, commands.BucketType.guild)
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def j2c(
        self,
        ctx: CustomContext,
        category_name: Optional[str] = "Custom Voice",
        voice_name: Optional[str] = "Join to Create",
        interface_name: Optional[str] = "Interface",
        reset: Optional[bool] = False,
    ) -> None:
        """Automated J2C infrastructure generator with duplicate prevention."""
        if ctx.interaction and not ctx.interaction.response.is_done():
            await ctx.defer(ephemeral=True)

        guild = ctx.guild
        if not guild:
            return

        # 1. Check existing configuration to prevent accidental spam / duplicates
        existing_settings = self.bot.temp_voice_mgr.get_settings(guild.id)
        if existing_settings and not reset:
            old_cat = guild.get_channel(existing_settings.get("category_id") or 0)
            old_master = guild.get_channel(existing_settings.get("master_channel_id") or 0)
            old_interface = guild.get_channel(existing_settings.get("interface_channel_id") or 0)

            # If existing channels are still alive on the server
            if old_cat or old_master or old_interface:
                alert_c = KyroContainer(accent_color=None)
                alert_c.add_section(
                    content=(
                        f"### Join to Create Already Configured\n"
                        f"> An active voice infrastructure already exists in this server."
                    )
                )
                alert_c.add_separator(divider=True)
                cat_desc = f"`{old_cat.name}`" if old_cat else "Not Found"
                v_desc = old_master.mention if old_master else "Not Found"
                i_desc = old_interface.mention if old_interface else "Not Found"
                alert_c.add_text(
                    f"• **Category:** {cat_desc}\n"
                    f"• **Master Voice:** {v_desc}\n"
                    f"• **Interface:** {i_desc}\n\n"
                    f"> To clean up and recreate fresh, run **/j2c reset:True**."
                )
                await send_container_response(ctx, alert_c, ephemeral=True)
                return

        # 2. If reset=True and old channels exist, clean them up safely
        if reset and existing_settings:
            old_cat = guild.get_channel(existing_settings.get("category_id") or 0)
            old_master = guild.get_channel(existing_settings.get("master_channel_id") or 0)
            old_interface = guild.get_channel(existing_settings.get("interface_channel_id") or 0)
            for ch in [old_interface, old_master, old_cat]:
                if ch:
                    try:
                        await ch.delete(reason=f"J2C reset initiated by {ctx.author}")
                    except discord.HTTPException:
                        pass

        cat_title = category_name.strip() if category_name else "Custom Voice"
        v_title = voice_name.strip() if voice_name else "Join to Create"
        i_title = interface_name.strip() if interface_name else "Interface"

        try:
            # 1. Create Category
            category = await guild.create_category(name=cat_title, reason=f"J2C setup by {ctx.author}")

            # 2. Create Master Voice Channel
            master_channel = await guild.create_voice_channel(
                name=v_title,
                category=category,
                reason=f"J2C master channel by {ctx.author}",
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
                reason=f"J2C interface channel by {ctx.author}",
            )

            # 4. Post the Master Interface Dashboard
            dashboard_container = KyroContainer(accent_color=None)
            dashboard_container.add_section(
                content=(
                    f"### Voice Interface\n"
                    f"> Join {master_channel.mention} to create your private voice room.\n"
                    f"> Manage room access and settings using the controls below."
                )
            )

            view = PersistentVoiceMasterView(self.bot)
            master_msg = await send_container_response(interface_channel, dashboard_container, view=view)
            msg_id = master_msg.id if isinstance(master_msg, discord.Message) else (int(master_msg["id"]) if isinstance(master_msg, dict) and "id" in master_msg else None)

            # 5. Save Configuration to Database and Cache
            await self.bot.temp_voice_mgr.set_settings(
                guild_id=guild.id,
                category_id=category.id,
                master_channel_id=master_channel.id,
                interface_channel_id=interface_channel.id,
                interface_message_id=msg_id,
            )

            # 6. Respond with Success Card to Administrator
            resp_container = KyroContainer(accent_color=None)
            resp_container.add_section(
                content=(
                    f"### Join to Create Configured\n"
                    f"> Voice infrastructure has been deployed successfully."
                )
            )
            resp_container.add_separator(divider=True)
            resp_container.add_text(
                f"• **Category:** `{category.name}`\n"
                f"• **Master Voice:** {master_channel.mention}\n"
                f"• **Interface:** {interface_channel.mention}"
            )

            await send_container_response(ctx, resp_container, ephemeral=True)

        except discord.HTTPException as e:
            err_c = KyroContainer(accent_color=None)
            err_c.add_section(f"**Error**: Failed to setup voice infrastructure: {e}")
            await send_container_response(ctx, err_c, ephemeral=True)

    @j2c.error
    async def j2c_error(self, ctx: CustomContext, error: Exception) -> None:
        if isinstance(error, commands.CommandOnCooldown):
            err_c = KyroContainer(accent_color=None)
            err_c.add_section(
                content=(
                    f"### Command Cooldown\n"
                    f"> Please wait {error.retry_after:.1f}s before running the setup command again."
                )
            )
            await send_container_response(ctx, err_c, ephemeral=True)
        elif isinstance(error, commands.MissingPermissions):
            err_c = KyroContainer(accent_color=None)
            err_c.add_section(
                content="**Access Denied**: You need **Manage Channels** permission to configure Join to Create."
            )
            await send_container_response(ctx, err_c, ephemeral=True)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(TempVoice(bot))
