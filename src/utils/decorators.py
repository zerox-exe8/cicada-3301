"""
Kyro Discord Bot - Universal Custom Decorators & Feature Guards
Provides clean, reusable decorators for permission and premium feature gating.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


def require_guild_premium() -> Callable[[Any], Any]:
    """
    Decorator that restricts command usage to Kyro Pro Servers.
    Sends a sleek Components V2 notification card if not premium.
    """
    async def predicate(ctx: CustomContext) -> bool:
        bot: KyroBot = ctx.bot  # type: ignore
        guild_id = ctx.guild.id if ctx.guild else None

        if bot.premium_mgr.is_guild_premium(guild_id):
            return True

        # Check if developer override applies
        if await bot.perm_mgr.is_developer(ctx.author.id):
            return True

        # Send elegant Pro Upsell Card
        e_reg = bot.custom_emojis
        crown_icon = e_reg.get("icons_star", e_reg.get("icon_gift", ""))
        crown_prefix = f"{crown_icon} " if crown_icon else ""

        container = KyroContainer(accent_color=None)
        container.add_text(
            f"{crown_prefix}**Kyro Pro Required**\n\n"
            f"> This advanced module is exclusive to **Kyro Pro** servers.\n\n"
            f"• **How to Unlock:** Get a license key and run `{ctx.prefix}redeem <key>`\n"
            f"• **Check Plan:** Use `{ctx.prefix}premium` to view your current status."
        )
        container.add_separator(divider=True)
        container.add_text("-# Kyro Infrastructure • Pro Tier")

        await send_container_response(ctx, container, ephemeral=True)
        return False

    return commands.check(predicate)


def require_user_premium() -> Callable[[Any], Any]:
    """
    Decorator that restricts personal cosmetic perks to Kyro VIP Users.
    """
    async def predicate(ctx: CustomContext) -> bool:
        bot: KyroBot = ctx.bot  # type: ignore
        user_id = ctx.author.id

        if bot.premium_mgr.is_user_premium(user_id):
            return True

        if await bot.perm_mgr.is_developer(user_id):
            return True

        e_reg = bot.custom_emojis
        crown_icon = e_reg.get("icons_star", e_reg.get("icon_gift", ""))
        crown_prefix = f"{crown_icon} " if crown_icon else ""

        container = KyroContainer(accent_color=None)
        container.add_text(
            f"{crown_prefix}**Kyro VIP Pro Required**\n\n"
            f"> This cosmetic superpower is exclusive to **Kyro VIP** members.\n\n"
            f"• **How to Unlock:** Redeem your user license key with `{ctx.prefix}redeem <key>`"
        )
        container.add_separator(divider=True)
        container.add_text("-# Kyro Personal Superpowers • VIP Tier")

        await send_container_response(ctx, container, ephemeral=True)
        return False

    return commands.check(predicate)
