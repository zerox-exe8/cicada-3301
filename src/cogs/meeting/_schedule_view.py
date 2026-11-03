from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Any
import discord
from discord import ui

from src.utils.containers import KyroContainer, edit_container_response, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot
    from src.repositories.meeting_repo import MeetingRepository

logger = logging.getLogger("Kyro.Meeting.ScheduleView")

# 24 Hourly Time Slots for Start / End selection
HOURLY_SLOTS = [f"{h:02d}:00" for h in range(24)]


def format_hour_label(time_str: str) -> str:
    """Format '09:00' -> '09:00 AM'."""
    try:
        h = int(time_str.split(":")[0])
        period = "AM" if h < 12 else "PM"
        display_h = 12 if (h == 0 or h == 12) else (h % 12)
        return f"{time_str} ({display_h:02d}:00 {period})"
    except Exception:
        return time_str


class MeetingScheduleWizard(ui.View):
    """
    Two-step interactive slider wizard for scheduling automated voice meetings.
    Step 1: Voice Channel selection.
    Step 2: Start & End time dropdowns with instant clean preview.
    """

    def __init__(
        self,
        bot: KyroBot,
        guild: discord.Guild,
        author: discord.Member,
        repo: MeetingRepository,
    ) -> None:
        super().__init__(timeout=300.0)
        self.bot = bot
        self.guild = guild
        self.author = author
        self.repo = repo

        self.current_step: int = 1
        self.selected_vc: Optional[discord.VoiceChannel] = None
        self.start_time: str = "09:00"
        self.end_time: str = "11:00"

        self._build_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            c = KyroContainer(accent_color=None)
            c.add_section(content=f"**Access Denied**\n> Only {self.author.mention} can configure this schedule.")
            await send_container_response(interaction, c, ephemeral=True)
            return False
        return True

    def get_container(self) -> KyroContainer:
        """Construct the KyroContainer for the current step."""
        container = KyroContainer(accent_color=None)
        container.add_text("## Meeting Schedule")
        container.add_separator(divider=True)

        if self.current_step == 1:
            container.add_text("> Select the voice channel for automated meeting recording.")
            container.add_separator(divider=True)
            container.add_text("-# Step 1 of 2 • Voice Channel Selection")
        else:
            vc_mention = self.selected_vc.mention if self.selected_vc else "`#unknown`"
            lines = [
                f"> • **Voice Channel:** {vc_mention}",
                f"> • **Start Time:** `{self.start_time}` (IST)",
                f"> • **End Time:** `{self.end_time}` (IST)",
            ]
            container.add_section(content="\n".join(lines))
            container.add_separator(divider=True)
            container.add_text("-# Step 2 of 2 • Time Window Selection (Auto-join active when user joins)")

        return container

    def _build_components(self) -> None:
        """Assemble components according to step 1 or step 2."""
        self.clear_items()

        if self.current_step == 1:
            # Step 1: Voice Channel Select
            select = ui.ChannelSelect(
                channel_types=[discord.ChannelType.voice],
                placeholder="Select Voice Channel...",
                custom_id="schedule_select_vc",
                row=0,
            )
            select.callback = self._on_vc_selected
            self.add_item(select)

            btn_cancel = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, row=1)
            btn_cancel.callback = self._on_cancel
            self.add_item(btn_cancel)

        else:
            # Step 2: Start Time & End Time Dropdowns
            start_opts: list[discord.SelectOption] = []
            end_opts: list[discord.SelectOption] = []

            for slot in HOURLY_SLOTS:
                lbl = format_hour_label(slot)
                start_opts.append(discord.SelectOption(label=lbl, value=slot, default=(slot == self.start_time)))
                end_opts.append(discord.SelectOption(label=lbl, value=slot, default=(slot == self.end_time)))

            select_start = ui.Select(
                placeholder=f"Start Time (Current: {self.start_time})",
                options=start_opts,
                custom_id="schedule_select_start",
                row=0,
            )
            select_start.callback = self._on_start_selected
            self.add_item(select_start)

            select_end = ui.Select(
                placeholder=f"End Time (Current: {self.end_time})",
                options=end_opts,
                custom_id="schedule_select_end",
                row=1,
            )
            select_end.callback = self._on_end_selected
            self.add_item(select_end)

            btn_save = ui.Button(label="Save Schedule", style=discord.ButtonStyle.secondary, row=2)
            btn_save.callback = self._on_save
            self.add_item(btn_save)

            btn_back = ui.Button(label="Back", style=discord.ButtonStyle.secondary, row=2)
            btn_back.callback = self._on_back
            self.add_item(btn_back)

            btn_cancel = ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, row=2)
            btn_cancel.callback = self._on_cancel
            self.add_item(btn_cancel)

    async def _on_vc_selected(self, interaction: discord.Interaction) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        select: ui.ChannelSelect = interaction.data.get("values", [])  # type: ignore
        if select and len(interaction.data["values"]) > 0:
            ch_id = int(interaction.data["values"][0])
            ch = self.guild.get_channel(ch_id)
            if isinstance(ch, discord.VoiceChannel):
                self.selected_vc = ch
                self.current_step = 2
                self._build_components()
                await edit_container_response(interaction.message, self.get_container(), view=self)

    async def _on_start_selected(self, interaction: discord.Interaction) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        values = interaction.data.get("values", [])
        if values:
            self.start_time = values[0]
            self._build_components()
            await edit_container_response(interaction.message, self.get_container(), view=self)

    async def _on_end_selected(self, interaction: discord.Interaction) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        values = interaction.data.get("values", [])
        if values:
            self.end_time = values[0]
            self._build_components()
            await edit_container_response(interaction.message, self.get_container(), view=self)

    async def _on_back(self, interaction: discord.Interaction) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        self.current_step = 1
        self._build_components()
        await edit_container_response(interaction.message, self.get_container(), view=self)

    async def _on_cancel(self, interaction: discord.Interaction) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        self.clear_items()
        c = KyroContainer(accent_color=None)
        c.add_text("## Meeting Schedule")
        c.add_separator(divider=True)
        c.add_text("> Scheduling setup was cancelled.")
        await edit_container_response(interaction.message, c, view=None)

    async def _on_save(self, interaction: discord.Interaction) -> None:
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        if not self.selected_vc:
            c = KyroContainer(accent_color=None)
            c.add_text("**Please select a voice channel first.**")
            await send_container_response(interaction, c, ephemeral=True)
            return

        if self.start_time == self.end_time:
            c = KyroContainer(accent_color=None)
            c.add_text("**Start time and end time cannot be identical.**")
            await send_container_response(interaction, c, ephemeral=True)
            return

        # Save to database
        try:
            sched_id = await self.repo.add_schedule(
                guild_id=self.guild.id,
                voice_channel_id=self.selected_vc.id,
                start_time=self.start_time,
                end_time=self.end_time,
                created_by=self.author.id,
            )
        except Exception as e:
            logger.error(f"Failed to add schedule in guild {self.guild.id}: {e}")
            c = KyroContainer(accent_color=None)
            c.add_text(f"**Failed to save schedule:** `{e}`")
            await send_container_response(interaction, c, ephemeral=True)
            return

        # Render clean confirmation
        self.clear_items()
        c = KyroContainer(accent_color=None)
        c.add_text("## Meeting Scheduled")
        c.add_separator(divider=True)
        lines = [
            f"> • **Voice Channel:** {self.selected_vc.mention}",
            f"> • **Schedule Window:** `{self.start_time}` – `{self.end_time}` (IST)",
            f"> • **Schedule ID:** `#{sched_id}`",
            "> • **Auto-Join:** `Active when members connect`",
        ]
        c.add_section(content="\n".join(lines))
        c.add_separator(divider=True)
        c.add_text("-# Meeting Intelligence will auto-join and record when users connect during this time.")
        await edit_container_response(interaction.message, c, view=None)

