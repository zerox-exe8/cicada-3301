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

        # 3. Economy & Capital Metrics
        level = 1
        xp = 0
        balance = 0
        try:
            econ_row = await self.bot.db.fetch_one(
                "SELECT balance, bank, level, xp FROM user_profiles WHERE user_id = $1;",
                target_id,
            )
            if econ_row:
                level = econ_row["level"] or 1
                xp = econ_row["xp"] or 0
                balance = (econ_row["balance"] or 0) + (econ_row["bank"] or 0)
        except Exception:
            pass

        # 4. Music Telemetry
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

        # 5. Registration timestamp
        created_str = target.created_at.strftime("%d %b %Y")
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

        container.add_text(
            f"> **Level** • `{level}` ({xp:,} XP)\n"
            f"> **Balance** • `{balance:,} Credits`\n"
            f"> **Playlists** • `{playlist_count} Repositories`\n"
            f"> **Joined Discord** • `{created_str}`\n\n"
            f"-# Kyro Network Identity Matrix"
        )

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Profile(bot))
