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
    """User profile and passport commands."""
    category: str = "Moderation"

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

        # Resolve user bio / About Me
        bio = "No bio set."
        try:
            fetched = await self.bot.fetch_user(target_id)
            if fetched and getattr(fetched, "bio", None) and fetched.bio.strip():
                clean_bio = fetched.bio.strip().replace("\r\n", " ").replace("\n", " ")
                bio = clean_bio[:120] + ("..." if len(clean_bio) > 120 else "")
        except Exception:
            pass

        # Resolve Badge (Clean, simple text, no emojis)
        is_owner_user = await self.bot.perm_mgr.is_owner(target_id)
        is_dev_user = await self.bot.perm_mgr.is_developer(target_id)
        has_no_prefix = target_id in getattr(self.bot, "no_prefix_users", set()) or is_dev_user

        if is_owner_user:
            badge_str = "Owner"
        elif is_dev_user:
            badge_str = "Developer"
        elif has_no_prefix:
            badge_str = "VIP Dispatcher"
        else:
            badge_str = "Member"

        # Resolve Premium Plan
        tier_str = "Free Tier"
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

        # Resolve No-Prefix
        no_prefix_str = "Active" if has_no_prefix else "Disabled"

        # Resolve Playlist library
        pl_display = "`None`"
        try:
            pl_rows = await self.bot.db.fetch_all(
                "SELECT playlist_name FROM user_playlists WHERE user_id = $1 ORDER BY id ASC;",
                target_id,
            )
            if pl_rows:
                names = [r["playlist_name"] for r in pl_rows if r.get("playlist_name")]
                if names:
                    joined_names = ", ".join(f"`{n}`" for n in names[:3])
                    extra = f" +{len(names) - 3} more" if len(names) > 3 else ""
                    pl_display = f"{len(names)} Saved ({joined_names}{extra})"
        except Exception:
            pass

        # Resolve Live Audio Detection
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

        if live_audio_title:
            link_str = f"[{live_audio_title}]({live_audio_url})" if live_audio_url else f"`{live_audio_title}`"
            author_str = f" by `{live_audio_author}`" if live_audio_author else ""
            vc_str = f" in `{live_audio_vc}`" if live_audio_vc else ""
            listening_str = f"{link_str}{author_str}{vc_str}"
        else:
            listening_str = "`Nothing Playing`"

        avatar_url = target.display_avatar.url if target.display_avatar else None

        # Build Clean Components V2 Card
        container = KyroContainer(accent_color=None)
        e_reg = getattr(self.bot, "custom_emojis", None)
        heart = e_reg.get("heart_dot", "❤") if e_reg else "❤"

        # Header: Large username title with bio tagline below it + avatar thumbnail
        container.add_section(
            content=(
                f"# {target.display_name}\n"
                f"*{bio}*"
            ),
            accessory={"type": 11, "media": {"url": avatar_url}} if avatar_url else None,
        )

        # Line separator directly below title & tagline
        container.add_separator(divider=True)

        # Blockquote details with heart bullet: Badge, Premium, No-Prefix, Playlist, Listening to
        fields_text = (
            f"> {heart} **Badge:** `{badge_str}`\n"
            f"> {heart} **Premium:** `{tier_str}`\n"
            f"> {heart} **No-Prefix:** `{no_prefix_str}`\n"
            f"> {heart} **Playlist:** {pl_display}\n"
            f"> {heart} **Listening to:** {listening_str}\n\n"
            f"-# Powered by Kyro Studio"
        )
        container.add_text(fields_text)

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Profile(bot))
