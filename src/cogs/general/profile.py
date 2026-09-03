"""
Kyro Discord Bot - User Bot Identity & Profile Command
Displays concise, enterprise-grade Kyro network passport in Components V2 layout.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.General.Profile")


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
        pl_display = "None"
        try:
            pl_rows = await self.bot.db.fetch_all(
                "SELECT playlist_name FROM user_playlists WHERE user_id = $1 ORDER BY id ASC;",
                target_id,
            )
            if pl_rows:
                names = [r["playlist_name"] for r in pl_rows if r.get("playlist_name")]
                if names:
                    pl_display = ", ".join(f"`{n}`" for n in names[:5])
                    if len(names) > 5:
                        pl_display += f" +{len(names) - 5} more"
        except Exception:
            pass

        # 4. Live Audio Detection
        live_audio_title: str | None = None
        live_audio_author: str | None = None
        live_audio_url: str | None = None
        live_audio_vc: str | None = None

        try:
            music_cog = self.bot.get_cog("Music")
            if music_cog and hasattr(music_cog, "controller"):
                # First check current guild player
                curr_player = music_cog.controller.get_player(ctx.guild.id) if ctx.guild else None
                if curr_player and curr_player.current and (curr_player.is_playing or curr_player.is_paused or curr_player.voice_client):
                    bot_vc = curr_player.voice_client.channel if curr_player.voice_client else None
                    target_member = target if isinstance(target, discord.Member) else (ctx.guild.get_member(target_id) if ctx.guild else None)

                    in_same_vc = bool(target_member and target_member.voice and bot_vc and target_member.voice.channel.id == bot_vc.id)
                    req_id_match = getattr(curr_player.current, "requester_id", None) == target_id
                    req_name_match = bool(curr_player.current.requester and curr_player.current.requester in (target.name, target.display_name, getattr(target, "global_name", "")))

                    if in_same_vc or req_id_match or req_name_match:
                        live_audio_title = curr_player.current.title
                        live_audio_author = curr_player.current.author or "Official Artist"
                        live_audio_url = getattr(curr_player.current, "uri", None) or curr_player.current.url
                        live_audio_vc = bot_vc.name if bot_vc else "Voice Channel"

                # If not found in current guild, search active players across all guilds
                if not live_audio_title:
                    for p in music_cog.controller.players.values():
                        if p and p.current and (p.is_playing or p.is_paused or p.voice_client):
                            p_vc = p.voice_client.channel if p.voice_client else None
                            g_member = p.guild.get_member(target_id)
                            in_same_vc = bool(g_member and g_member.voice and p_vc and g_member.voice.channel.id == p_vc.id)
                            req_id_match = getattr(p.current, "requester_id", None) == target_id
                            req_name_match = bool(p.current.requester and p.current.requester in (target.name, target.display_name, getattr(target, "global_name", "")))

                            if in_same_vc or req_id_match or req_name_match:
                                live_audio_title = p.current.title
                                live_audio_author = p.current.author or "Official Artist"
                                live_audio_url = getattr(p.current, "uri", None) or p.current.url
                                live_audio_vc = p_vc.name if p_vc else "Voice Channel"
                                break
        except Exception as e:
            logger.error(f"Failed to resolve live audio status in profile: {e}", exc_info=True)

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
            author_str = f" by `{live_audio_author}`" if live_audio_author else ""
            audio_lines = (
                f"> **Playlists** • {pl_display}\n"
                f"> **Live Audio** • {link_str}{author_str}\n"
                f"> **Channel** • `{live_audio_vc}` • `320kbps Studio Master`\n\n"
            )
        else:
            audio_lines = (
                f"> **Playlists** • {pl_display}\n"
                f"> **Live Audio** • `Idle (Not Listening)`\n\n"
            )

        container.add_text(
            audio_lines + "-# Powered by Kyro Studio"
        )

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Profile(bot))
