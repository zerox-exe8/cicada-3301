"""
Kyro Discord Bot - Native Music Controller Interactive Views
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord

from src.utils.containers import KyroContainer, send_container_response

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
            c = KyroContainer()
            c.add_section(content="**Voice Error**\n> Player is not connected to a voice channel.")
            await send_container_response(interaction, c, ephemeral=True)
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
            c = KyroContainer()
            c.add_section(content="**Voice Error**\n> Player is not connected.")
            await send_container_response(interaction, c, ephemeral=True)
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
            c = KyroContainer()
            c.add_section(content="**Player Notice**\n> Player not active.")
            await send_container_response(interaction, c, ephemeral=True)
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
            c = KyroContainer()
            c.add_section(content="**Player Notice**\n> Player not active.")
            await send_container_response(interaction, c, ephemeral=True)
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
            c = KyroContainer()
            c.add_section(content="**Player Notice**\n> Player not active.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        player._disconnect_announced = True
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
            c = KyroContainer()
            c.add_section(content="**Favorites Notice**\n> No track is currently playing to add to Favorites.")
            await send_container_response(interaction, c, ephemeral=True)
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
            c = KyroContainer()
            c.add_section(content="**Database Error**\n> Failed to access your Favorites playlist.")
            await send_container_response(interaction, c, ephemeral=True)
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
            c = KyroContainer()
            c.add_section(content=f"**Favorites Notice**\n> `{save_title}` is already in your **Favorites**.")
            await send_container_response(interaction, c, ephemeral=True)
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
        c = KyroContainer()
        c.add_section(content=f"**Favorites Added**\n> Saved **[{save_title}]({track_web_url})** to your **Favorites** playlist!")
        await send_container_response(interaction, c, ephemeral=True)

    @discord.ui.button(
        label="Loop",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:loop",
        row=1,
    )
    async def btn_loop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player:
            c = KyroContainer()
            c.add_section(content="**Player Notice**\n> Player not active.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        modes = ["off", "track", "queue"]
        cur_mode = getattr(player, "loop_mode", "off")
        next_idx = (modes.index(cur_mode) + 1) % len(modes) if cur_mode in modes else 0
        player.loop_mode = modes[next_idx]
        c = KyroContainer()
        c.add_section(content=f"**Loop Mode**\n> Loop mode set to **{player.loop_mode.upper()}**.")
        await send_container_response(interaction, c, ephemeral=True)

    @discord.ui.button(
        label="Autoplay",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:autoplay",
        row=1,
    )
    async def btn_autoplay(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player:
            c = KyroContainer()
            c.add_section(content="**Player Notice**\n> Player not active.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        player.smart_autoplay = not player.smart_autoplay
        state = "Enabled" if player.smart_autoplay else "Disabled"
        c = KyroContainer()
        c.add_section(content=f"**Smart Autoplay**\n> Smart Autoplay **{state}**.")
        await send_container_response(interaction, c, ephemeral=True)

    @discord.ui.button(
        label="Queue",
        style=discord.ButtonStyle.secondary,
        custom_id="kyro:music:queue",
        row=1,
    )
    async def btn_queue(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        player = self._get_player(interaction)
        if not player or not player.queue:
            c = KyroContainer()
            c.add_section(content="**Queue Empty**\n> The playback queue is currently empty.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        q_lines = []
        for i, t in enumerate(player.queue[:10], 1):
            q_lines.append(f"`{i}.` **{t.title}** (`{t.formatted_duration}`) • {t.author}")

        remaining = len(player.queue) - 10
        rem_text = f"\n*...and {remaining} more in queue*" if remaining > 0 else ""
        c = KyroContainer()
        c.add_section(
            content=f"**Upcoming Queue ({len(player.queue)} tracks)**\n" + "\n".join(q_lines) + rem_text
        )
        await send_container_response(interaction, c, ephemeral=True)
