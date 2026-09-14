"""
Kyro Discord Bot - Native Music Controller Interactive Views
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord

if TYPE_CHECKING:
    from src.core.bot import KyroBot
    from src.cogs.music._player import GuildPlayer

logger = logging.getLogger("Kyro.Music.Views")


class MusicControlView(discord.ui.View):
    """Interactive media control row with zero unicode emojis (uses custom application emojis)."""

    def __init__(self, bot: KyroBot, player: Optional[GuildPlayer] = None, guild_id: Optional[int] = None) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        self.player = player
        self.guild_id = guild_id or (player.guild.id if player else 0)

        # Apply custom emojis from assets if available
        self._apply_custom_emojis()

    def _apply_custom_emojis(self) -> None:
        e_reg = getattr(self.bot, "custom_emojis", None)
        if not e_reg:
            return

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                cid = child.custom_id or ""
                if "playpause" in cid:
                    child.emoji = e_reg.get_emoji_obj("paused")
                elif "skip" in cid:
                    child.emoji = e_reg.get_emoji_obj("skip")
                elif "voldown" in cid:
                    child.emoji = e_reg.get_emoji_obj("volume_down")
                elif "volup" in cid:
                    child.emoji = e_reg.get_emoji_obj("volume_up")
                elif "stop" in cid:
                    child.emoji = e_reg.get_emoji_obj("icons_stop_button")

    def _get_player(self, interaction: discord.Interaction) -> Optional[GuildPlayer]:
        if self.player:
            return self.player
        music_cog = self.bot.get_cog("Music")
        if music_cog and hasattr(music_cog, "controller"):
            return music_cog.controller.get_player(interaction.guild_id)
        return None

    @discord.ui.button(
        label="Pause",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:playpause",
    )
    async def btn_pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player or not player.is_connected:
            await interaction.response.send_message("Player is not connected to a voice channel.", ephemeral=True)
            return

        if player.is_paused:
            player.resume()
            button.label = "Pause"
        elif player.is_playing:
            player.pause()
            button.label = "Resume"

        await player.update_controller_message(force=True)
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(
        label="Skip",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:skip",
    )
    async def btn_skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player or not player.is_connected:
            await interaction.response.send_message("Player is not connected.", ephemeral=True)
            return

        await player.skip()
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(
        label="Vol -",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:voldown",
    )
    async def btn_vol_down(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("Player not active.", ephemeral=True)
            return

        cur_vol = int(player.volume * 100)
        player.set_volume(cur_vol - 10)
        await player.update_controller_message(force=True)
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(
        label="Vol +",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:volup",
    )
    async def btn_vol_up(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("Player not active.", ephemeral=True)
            return

        cur_vol = int(player.volume * 100)
        player.set_volume(cur_vol + 10)
        await player.update_controller_message(force=True)
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(
        label="Stop",
        style=discord.ButtonStyle.danger,
        custom_id="kyro:music:stop",
    )
    async def btn_stop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("Player not active.", ephemeral=True)
            return

        await player.stop()
        if not interaction.response.is_done():
            await interaction.response.defer()

    @discord.ui.button(
        label="Like",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:like",
        row=1,
    )
    async def btn_like(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player or not player.current:
            await interaction.response.send_message("No track is currently playing to add to Favorites.", ephemeral=True)
            return

        current = player.current
        db = self.bot.db
        user_id = interaction.user.id

        pl_row = await db.fetch_one(
            "SELECT id FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = 'favorites';",
            user_id,
        )
        if not pl_row:
            await db.execute(
                "INSERT INTO user_playlists (user_id, playlist_name) VALUES ($1, 'Favorites') ON CONFLICT DO NOTHING;",
                user_id,
            )
            pl_row = await db.fetch_one(
                "SELECT id FROM user_playlists WHERE user_id = $1 AND LOWER(playlist_name) = 'favorites';",
                user_id,
            )

        if not pl_row:
            await interaction.response.send_message("Failed to access your Favorites playlist.", ephemeral=True)
            return

        playlist_id = pl_row["id"]
        save_title = (current.title or "Unknown Track")[:250]
        save_author = (current.author or "Official Artist")[:250]

        existing = await db.fetch_one(
            "SELECT id FROM user_playlist_tracks WHERE playlist_id = $1 AND LOWER(title) = LOWER($2);",
            playlist_id,
            save_title,
        )
        if existing:
            await interaction.response.send_message(f"`{save_title}` is already in your **Favorites**.", ephemeral=True)
            return

        track_web_url = getattr(current, "url", None) or getattr(current, "stream_url", "")
        await db.execute(
            "INSERT INTO user_playlist_tracks (playlist_id, title, author, duration, url) VALUES ($1, $2, $3, $4, $5);",
            playlist_id,
            save_title,
            save_author,
            current.duration,
            track_web_url,
        )
        await interaction.response.send_message(f"Saved **[{save_title}]({track_web_url})** to your **Favorites** playlist!", ephemeral=True)

    @discord.ui.button(
        label="Loop",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:loop",
        row=1,
    )
    async def btn_loop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("Player not active.", ephemeral=True)
            return

        modes = ["off", "track", "queue"]
        cur_mode = getattr(player, "loop_mode", "off")
        next_idx = (modes.index(cur_mode) + 1) % len(modes) if cur_mode in modes else 0
        player.loop_mode = modes[next_idx]
        await interaction.response.send_message(f"Loop mode set to **{player.loop_mode.upper()}**.", ephemeral=True)

    @discord.ui.button(
        label="Autoplay",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:autoplay",
        row=1,
    )
    async def btn_autoplay(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player:
            await interaction.response.send_message("Player not active.", ephemeral=True)
            return

        player.smart_autoplay = not player.smart_autoplay
        state = "Enabled" if player.smart_autoplay else "Disabled"
        await interaction.response.send_message(f"Smart Autoplay **{state}**.", ephemeral=True)

    @discord.ui.button(
        label="Queue",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:queue",
        row=1,
    )
    async def btn_queue(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player or not player.queue:
            await interaction.response.send_message("The playback queue is currently empty.", ephemeral=True)
            return

        q_lines = []
        for i, t in enumerate(player.queue[:10], 1):
            q_lines.append(f"`{i}.` **{t.title}** (`{t.formatted_duration}`) • {t.author}")

        remaining = len(player.queue) - 10
        rem_text = f"\n*...and {remaining} more in queue*" if remaining > 0 else ""
        await interaction.response.send_message(
            f"**Upcoming Queue ({len(player.queue)} tracks):**\n" + "\n".join(q_lines) + rem_text,
            ephemeral=True,
        )
