"""
Kyro Discord Bot - Universal Variable / Placeholder Engine
Resolves dynamic variables ({user}, {server}, {count}, {avatar}, etc.) for
Outer Ping Messages, Welcome/Leave/Boost events, and Embed Containers.
"""

from __future__ import annotations

import datetime
import re
import time
from typing import Any
import discord


def get_ordinal(n: int) -> str:
    """Return ordinal number string (e.g. 1st, 2nd, 3rd, 4th, 11th, 21st, 1,250th)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n:,}{suffix}"


def resolve_placeholders(
    text: str | None,
    user: discord.Member | discord.User | None = None,
    guild: discord.Guild | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Replace all standard Mimu/Kyro variables in a given string."""
    if not text:
        return ""

    extra = extra or {}
    now = datetime.datetime.now(datetime.timezone.utc)
    ts_now = int(time.time())

    # 1. User variables
    user_mention = user.mention if user else "@User"
    user_name = user.name if user else "User"
    user_display = user.display_name if user else user_name
    user_id = str(user.id) if user else "000000000000000000"
    user_tag = str(user) if user else "User#0000"
    avatar_url = str(user.display_avatar.url) if user else "https://cdn.discordapp.com/embed/avatars/0.png"
    created_ts = int(user.created_at.timestamp()) if (user and hasattr(user, "created_at") and user.created_at) else ts_now
    user_created = f"<t:{created_ts}:R>"

    user_joined = "<t:0:R>"
    if user and hasattr(user, "joined_at") and getattr(user, "joined_at"):
        joined_ts = int(user.joined_at.timestamp())
        user_joined = f"<t:{joined_ts}:R>"

    # 2. Guild / Server variables
    guild_name = guild.name if guild else "Server"
    guild_id = str(guild.id) if guild else "000000000000000000"
    guild_icon = str(guild.icon.url) if (guild and guild.icon) else avatar_url
    guild_banner = str(guild.banner.url) if (guild and guild.banner) else ""
    member_count = getattr(guild, "member_count", 1) if guild else 1
    count_formatted = f"{member_count:,}"
    count_ordinal = get_ordinal(member_count)
    boost_count = str(getattr(guild, "premium_subscription_count", 0)) if guild else "0"
    boost_tier = f"Level {getattr(guild, 'premium_tier', 0)}" if guild else "Level 0"
    owner_mention = guild.owner.mention if (guild and guild.owner) else "@Owner"

    # 3. Boost / Event Extra variables
    booster_mention = extra.get("booster", user_mention)
    extra_boost_count = extra.get("boost_count", boost_count)
    extra_boost_tier = extra.get("boost_tier", boost_tier)

    # 4. Replacements Mapping
    replacements = {
        # Comprehensive User mention variations (longer specific patterns first)
        "@{user.mention}": user_mention,
        "@{member.mention}": user_mention,
        "<@{user.mention}>": user_mention,
        "<@{member.mention}>": user_mention,
        "<@{user.id}>": user_mention,
        "<@{member.id}>": user_mention,
        "@{user.id}": user_mention,
        "@{member.id}": user_mention,
        "<@{user}>": user_mention,
        "<@{member}>": user_mention,
        "@{user}": user_mention,
        "@{member}": user_mention,
        "@{mention}": user_mention,
        "{user.mention}": user_mention,
        "{member.mention}": user_mention,
        "{user_mention}": user_mention,
        "{member_mention}": user_mention,
        "{user}": user_mention,
        "{member}": user_mention,
        "{mention}": user_mention,

        # Standard User placeholders
        "{user.name}": user_name,
        "{user.username}": user_name,
        "{username}": user_name,
        "{user.display_name}": user_display,
        "{display_name}": user_display,
        "{user.id}": user_id,
        "{user.tag}": user_tag,
        "{user.avatar}": avatar_url,
        "{user.avatar_url}": avatar_url,
        "{avatar}": avatar_url,
        "{user.created_at}": user_created,
        "{user.joined_at}": user_joined,

        # Server placeholders
        "{server}": guild_name,
        "{server.name}": guild_name,
        "{guild}": guild_name,
        "{guild.name}": guild_name,
        "{server.id}": guild_id,
        "{guild.id}": guild_id,
        "{server.icon}": guild_icon,
        "{guild.icon}": guild_icon,
        "{server.banner}": guild_banner,
        "{guild.banner}": guild_banner,
        "{server.owner}": owner_mention,
        "{count}": count_formatted,
        "{server.member_count}": count_formatted,
        "{member_count}": count_formatted,
        "{members}": count_formatted,
        "{count.ordinal}": count_ordinal,
        "{server.boost_count}": boost_count,
        "{boosts}": boost_count,
        "{server.boost_level}": boost_tier,
        "{boost_tier}": boost_tier,
        "{tier}": boost_tier,

        # Boost event variables
        "{booster}": booster_mention,
        "{boost.count}": str(extra_boost_count),
        "{boost.tier}": str(extra_boost_tier),

        # Time & Helper placeholders
        "{date}": now.strftime("%d %b %Y"),
        "{time}": now.strftime("%I:%M %p UTC"),
        "{timestamp}": f"<t:{ts_now}:f>",
        "{timestamp.relative}": f"<t:{ts_now}:R>",
        "{timestamp.r}": f"<t:{ts_now}:R>",
        "{newline}": "\n",
    }

    result = text
    for key, val in replacements.items():
        if key in result:
            result = result.replace(key, str(val))

    if user:
        # Replace standalone un-bracketed @user or @member (e.g. "@user welcome!")
        result = re.sub(r"(?i)(?<!<)@(?:user|member)\b", user_mention, result)
        # Fix any duplicate @ or nested bracket artifacts (e.g. @<@123> -> <@123>, <@<@123>> -> <@123>, <<@123>> -> <@123>)
        result = re.sub(r"@+<@!?(\d+)>", r"<@\1>", result)
        result = re.sub(r"<+@*<@!?(\d+)>*>", r"<@\1>", result)

    return result
