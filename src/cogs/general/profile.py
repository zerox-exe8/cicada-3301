"""
Kyro Discord Bot - User Bot Identity & Profile Command
Displays concise, enterprise-grade Kyro network passport in Components V2 layout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class Profile(commands.Cog):
    """User bot passport and identity statistics."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="profile",
        aliases=["pr", "prof", "userprofile"],
        description="View your or another member's Kyro Bot Identity & Standing.",
    )
    async def profile(self, ctx: CustomContext, member: Optional[discord.Member | discord.User] = None) -> None:
        """Display clean, high-precision Bot Passport for the user."""
        target = member or ctx.author
        target_id = target.id

        # 1. Resolve Standing
        is_owner_user = await self.bot.perm_mgr.is_owner(target_id)
        is_dev_user = await self.bot.perm_mgr.is_developer(target_id)
        has_no_prefix = target_id in getattr(self.bot, "no_prefix_users", set()) or is_dev_user

        if is_owner_user:
            standing = "Owner"
        elif is_dev_user:
            standing = "Developer"
        elif has_no_prefix:
            standing = "Authorized Dispatcher"
        else:
            standing = "Standard Client"

        # 2. Resolve Access & Tier
        access_str = "No-Prefix Active" if has_no_prefix else "Standard"

        tier_str = "Standard"
        try:
            prem_row = await self.bot.db.fetch_one(
                "SELECT tier, expires_at FROM user_premium WHERE user_id = $1;",
                target_id,
            )
            if prem_row:
                tier_val = (prem_row["tier"] or "Pro").capitalize()
                tier_str = f"Prime {tier_val}"
            elif is_owner_user:
                tier_str = "Prime Lifetime"
        except Exception:
            pass

        # 3. Music Telemetry (Saved Playlists)
        playlist_count = 0
        try:
            pl_rows = await self.bot.db.fetch_all(
                "SELECT COUNT(*) as c FROM user_playlists WHERE user_id = $1;",
                target_id,
            )
            if pl_rows and len(pl_rows) > 0:
                playlist_count = pl_rows[0]["c"] or 0
        except Exception:
            pass

        # 4. Live Audio Detection
        live_audio_title: str | None = None
        live_audio_url: str | None = None
        live_audio_vc: str | None = None

        try:
            music_cog = self.bot.get_cog("Music")
            if music_cog and hasattr(music_cog, "controller"):
                # First check current guild player
                curr_player = music_cog.controller.get_player(ctx.guild.id) if ctx.guild else None
                if curr_player and curr_player.is_playing and curr_player.current:
                    target_member = ctx.guild.get_member(target_id) if ctx.guild else None
                    if (target_member and target_member.voice and target_member.voice.channel == curr_player.voice_channel) or (curr_player.current.requester_id == target_id):
                        live_audio_title = curr_player.current.title
                        live_audio_url = curr_player.current.uri
                        live_audio_vc = curr_player.voice_channel.name if curr_player.voice_channel else "Voice Channel"

                # If not found in current guild, search active players across all guilds
                if not live_audio_title:
                    for p in music_cog.controller.players.values():
                        if p and p.is_playing and p.current:
                            guild_member = p.guild.get_member(target_id)
                            if (guild_member and guild_member.voice and guild_member.voice.channel == p.voice_channel) or (p.current.requester_id == target_id):
                                live_audio_title = p.current.title
                                live_audio_url = p.current.uri
                                live_audio_vc = p.voice_channel.name if p.voice_channel else "Voice Channel"
                                break
        except Exception:
            pass

        avatar_url = target.display_avatar.url if target.display_avatar else None

        # Build Clean Components V2 Card
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### {target.name}\n"
                f"> **Standing** • `{standing}`\n"
                f"> **Access** • `{access_str}`\n"
                f"> **Tier** • `{tier_str}`"
            ),
            accessory={"type": 11, "media": {"url": avatar_url}} if avatar_url else None,
        )

        container.add_separator(divider=True)

        if live_audio_title:
            link_str = f"[{live_audio_title}]({live_audio_url})" if live_audio_url else f"`{live_audio_title}`"
            audio_lines = (
                f"> **Playlists** • `{playlist_count} Repositories`\n"
                f"> **Live Audio** • {link_str}\n"
                f"> **Channel** • `{live_audio_vc}` • `320kbps Studio Master`\n\n"
            )
        else:
            audio_lines = (
                f"> **Playlists** • `{playlist_count} Repositories`\n"
                f"> **Live Audio** • `Idle (Not Listening)`\n\n"
            )

        container.add_text(
            audio_lines + "-# Powered by Kyro Studio"
        )

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Profile(bot))
