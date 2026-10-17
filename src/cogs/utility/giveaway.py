from __future__ import annotations

import asyncio
import datetime
import logging
import re
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.core.context import CustomContext
from src.cogs.moderation._helpers import resolve_role
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Utility.Giveaway")


def parse_giveaway_duration(duration_str: str) -> Optional[datetime.timedelta]:
    """
    Parse duration strings like '10s', '5m', '2h', '1d', '2w', '1d12h'.
    Returns timedelta or None if invalid.
    """
    clean = duration_str.strip().lower()
    matches = re.findall(r"(\d+)\s*([smhdw])", clean)
    if not matches:
        return None

    total_seconds = 0
    unit_multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }

    for val_str, unit in matches:
        total_seconds += int(val_str) * unit_multipliers[unit]

    if total_seconds < 5:  # Minimum 5 seconds
        return None
    if total_seconds > 2592000:  # Maximum 30 days
        return None

    return datetime.timedelta(seconds=total_seconds)


def get_giveaway_thumbnail(
    bot: KyroBot,
    guild: Optional[discord.Guild] = None,
    host_id: Optional[int] = None,
) -> Optional[str]:
    """Retrieve optimal thumbnail asset for giveaway card (custom emoji CDN, host avatar, or guild icon)."""
    gw_obj = bot.custom_emojis.get_emoji_obj("discord_giveaway") or bot.custom_emojis.get_emoji_obj("giveaway")
    if gw_obj and hasattr(gw_obj, "url") and gw_obj.url:
        return str(gw_obj.url)
    if guild and host_id:
        member = guild.get_member(host_id)
        if member and member.display_avatar:
            return member.display_avatar.url
    if guild and guild.icon:
        return guild.icon.url
    return "https://cdn.discordapp.com/emojis/1049282218008399872.png"


def build_giveaway_container(
    prize: str,
    host_id: int,
    winner_count: int,
    ends_at: datetime.datetime,
    entries_count: int = 0,
    required_role_id: Optional[int] = None,
    is_ended: bool = False,
    winners: Optional[list[int]] = None,
    gw_emoji: str = "🎉",
    thumbnail_url: Optional[str] = None,
) -> KyroContainer:
    """Build rich and engaging Components V2 container card for active or ended giveaways."""
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=datetime.timezone.utc)
    ts = int(ends_at.timestamp())
    title_prize = prize.title() if prize.islower() else prize

    if not is_ended:
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### {gw_emoji} New Giveaway {gw_emoji}\n"
                f"**{title_prize}**\n"
                f"> Click the **Enter** button below to participate!"
            )
        )
        if thumbnail_url:
            container.add_thumbnail(thumbnail_url)

        container.add_separator(divider=True)

        req_text = f"\n> 🔒 **Required Role:** <@&{required_role_id}>" if required_role_id else ""
        winner_label = "Winner" if winner_count == 1 else "Winners"
        container.add_text(
            f"> 🎁 **Prize:** **{title_prize}**\n"
            f"> 👑 **Hosted By:** <@{host_id}>\n"
            f"> 🏆 **{winner_label}:** `{winner_count}`\n"
            f"> 👥 **Entries:** `{entries_count}`{req_text}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Ends: <t:{ts}:R>")
        return container

    # Ended giveaway
    container = KyroContainer(accent_color=None)
    container.add_section(
        content=(
            f"### {gw_emoji} Giveaway Ended {gw_emoji}\n"
            f"**{title_prize}**\n"
            f"> Thank you to everyone who joined!"
        )
    )
    if thumbnail_url:
        container.add_thumbnail(thumbnail_url)

    container.add_separator(divider=True)

    if winners:
        winner_str = ", ".join(f"<@{w}>" for w in winners)
        winner_label = "Winner" if len(winners) == 1 else "Winners"
    else:
        winner_str = "*No one entered*"
        winner_label = "Winner" if winner_count == 1 else "Winners"

    req_text = f"\n> 🔒 **Required Role:** <@&{required_role_id}>" if required_role_id else ""
    container.add_text(
        f"> 🎁 **Prize:** **{title_prize}**\n"
        f"> 🏆 **{winner_label}:** {winner_str}\n"
        f"> 👑 **Hosted By:** <@{host_id}>\n"
        f"> 👥 **Total Entries:** `{entries_count}`{req_text}"
    )
    container.add_separator(divider=True)
    container.add_text(f"-# Ended: <t:{ts}:R>")
    return container


class PersistentGiveawayView(discord.ui.View):
    """Global persistent view for ongoing giveaways surviving bot restarts."""

    def __init__(self, bot: KyroBot) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        gw_emoji_obj = self.bot.custom_emojis.get_emoji_obj("discord_giveaway") or self.bot.custom_emojis.get_emoji_obj("giveaway")
        if gw_emoji_obj:
            self.enter_giveaway.emoji = gw_emoji_obj

    @discord.ui.button(
        label="Enter",
        style=discord.ButtonStyle.primary,
        custom_id="kyro:giveaway:enter",
    )
    async def enter_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Handle dynamic entry and withdrawal on click."""
        if not interaction.guild:
            return

        msg_id = interaction.message.id
        gw = self.bot.giveaway_mgr.get_giveaway_by_message_id(msg_id)

        # Fallback check from DB if not in active memory
        if not gw:
            gw_row = await self.bot.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", msg_id)
            if not gw_row or gw_row.get("is_ended"):
                container = KyroContainer(accent_color=None)
                container.add_section(content="**Giveaway Ended**")
                container.add_separator(divider=True)
                container.add_text("> This giveaway has already ended.")
                await send_container_response(interaction, container, ephemeral=True)
                return
            gw = dict(gw_row)

        giveaway_id = gw["id"]

        # Check required role requirement if set
        if gw.get("required_role_id") and isinstance(interaction.user, discord.Member):
            req_role = interaction.guild.get_role(int(gw["required_role_id"]))
            if req_role and req_role not in interaction.user.roles:
                container = KyroContainer(accent_color=None)
                container.add_section(content="**Role Required**")
                container.add_separator(divider=True)
                container.add_text(f"{dot} You need the {req_role.mention} role to enter this giveaway.")
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {interaction.user.display_name}")
                await send_container_response(interaction, container, ephemeral=True)
                return

        # Atomically toggle participant
        success, action, count = await self.bot.giveaway_mgr.toggle_participant(giveaway_id, interaction.user.id)
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        gw_emoji = self.bot.custom_emojis.get("discord_giveaway", self.bot.custom_emojis.get("giveaway", "🎉"))

        resp_container = KyroContainer(accent_color=None)
        if action == "entered":
            resp_container.add_section(content="**You're In!**")
            resp_container.add_separator(divider=True)
            resp_container.add_text(
                f"{dot} You joined the giveaway for **{gw['prize']}**!\n"
                f"> Total entries: `{count}`. Click again anytime to leave."
            )
        else:
            resp_container.add_section(content="**You Left**")
            resp_container.add_separator(divider=True)
            resp_container.add_text(
                f"{dot} You left the giveaway for **{gw['prize']}**.\n"
                f"> Total entries: `{count}`."
            )
        resp_container.add_separator(divider=True)
        resp_container.add_text(f"-# Requested by {interaction.user.display_name}")

        # Send ephemeral confirmation
        await send_container_response(interaction, resp_container, ephemeral=True)

        # Update message card
        try:
            gw_emoji_obj = self.bot.custom_emojis.get_emoji_obj("discord_giveaway") or self.bot.custom_emojis.get_emoji_obj("giveaway")
            if gw_emoji_obj:
                button.emoji = gw_emoji_obj
            button.label = "Enter"
            thumb_url = get_giveaway_thumbnail(self.bot, interaction.guild, host_id=gw.get("host_id"))
            updated_card = build_giveaway_container(
                prize=gw["prize"],
                host_id=gw["host_id"],
                winner_count=gw["winner_count"],
                ends_at=gw["ends_at"],
                entries_count=count,
                required_role_id=gw.get("required_role_id"),
                gw_emoji=gw_emoji,
                thumbnail_url=thumb_url,
            )
            await edit_container_response(interaction.message, updated_card, view=self)
        except Exception as e:
            logger.debug(f"Notice updating giveaway button counter on message {msg_id}: {e}")


class ConcludedGiveawayView(discord.ui.View):
    """View with a disabled button marking giveaway conclusion."""

    def __init__(self, bot: KyroBot, count: int = 0) -> None:
        super().__init__(timeout=None)
        gw_emoji_obj = bot.custom_emojis.get_emoji_obj("discord_giveaway") or bot.custom_emojis.get_emoji_obj("giveaway")
        self.add_item(
            discord.ui.Button(
                label="Giveaway Ended",
                style=discord.ButtonStyle.secondary,
                disabled=True,
                custom_id="kyro:giveaway:concluded",
                emoji=gw_emoji_obj if gw_emoji_obj else "🎉",
            )
        )


class Giveaways(commands.Cog):
    """Enterprise Giveaway Management system with live countdowns and fair winner draws."""
    category: str = "Utility"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.bot.add_view(PersistentGiveawayView(self.bot))

    async def cog_load(self) -> None:
        """Start autonomous background ticker."""
        self.giveaway_ticker.start()

    async def cog_unload(self) -> None:
        """Cancel background loop cleanly on unload."""
        self.giveaway_ticker.cancel()

    def _build_usage_card(self, ctx: CustomContext) -> KyroContainer:
        """Construct the Components V2 usage guide matching role command layout."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Giveaway Commands**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} `{prefix}gstart <time> [winners] <prize>`\n"
            f"{dot} `{prefix}gend [message_id]`\n"
            f"{dot} `{prefix}greroll [message_id] [winners]`\n"
            f"{dot} `{prefix}glist`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    # ─── AUTONOMOUS TICKER TASK ──────────────────────────────────────────────

    @tasks.loop(seconds=10.0)
    async def giveaway_ticker(self) -> None:
        """Periodic loop monitoring active giveaways and triggering conclusion upon expiry."""
        try:
            due = self.bot.giveaway_mgr.get_due_giveaways()
            for gw in due:
                try:
                    await self.conclude_giveaway(gw["message_id"])
                except Exception as e:
                    logger.error(f"Error concluding giveaway message {gw.get('message_id')}: {e}", exc_info=e)
        except Exception as e:
            logger.debug(f"Giveaway loop notice: {e}")

    @giveaway_ticker.before_loop
    async def before_ticker(self) -> None:
        await self.bot.wait_until_ready()

    async def conclude_giveaway(self, message_id: int) -> Optional[dict]:
        """Finalize giveaway, edit card, disable button, and announce winners."""
        res = await self.bot.giveaway_mgr.end_giveaway(message_id)
        if not res:
            return None

        channel = self.bot.get_channel(res["channel_id"])
        if not channel:
            try:
                channel = await self.bot.fetch_channel(res["channel_id"])
            except Exception:
                return res

        msg = None
        try:
            msg = await channel.fetch_message(message_id)
        except Exception:
            pass

        dot = self.bot.custom_emojis.get("heart_dot", "•")
        gw_emoji = self.bot.custom_emojis.get("discord_giveaway", self.bot.custom_emojis.get("giveaway", "🎉"))
        winners = res.get("winners", [])
        total_entries = res.get("total_entries", 0)

        guild = channel.guild if hasattr(channel, "guild") else None
        thumb_url = get_giveaway_thumbnail(self.bot, guild, host_id=res.get("host_id"))

        # Build concluded card & disabled view
        concluded_card = build_giveaway_container(
            prize=res["prize"],
            host_id=res["host_id"],
            winner_count=res["winner_count"],
            ends_at=res["ends_at"],
            entries_count=total_entries,
            required_role_id=res.get("required_role_id"),
            is_ended=True,
            winners=winners,
            gw_emoji=gw_emoji,
            thumbnail_url=thumb_url,
        )
        ended_view = ConcludedGiveawayView(self.bot, count=total_entries)

        if msg:
            try:
                await edit_container_response(msg, concluded_card, view=ended_view)
            except Exception as e:
                logger.debug(f"Failed to edit giveaway message {message_id}: {e}")

        # Send celebration announcement
        if winners:
            winner_mentions = ", ".join(f"<@{w}>" for w in winners)
            winner_label = "Winner" if len(winners) == 1 else "Winners"
            win_container = KyroContainer(accent_color=None)
            win_container.add_section(
                content=(
                    f"### {gw_emoji} Giveaway Winners {gw_emoji}\n"
                    f"**{res['prize'].title() if res['prize'].islower() else res['prize']}**"
                )
            )
            if thumb_url:
                win_container.add_thumbnail(thumb_url)
            win_container.add_separator(divider=True)
            win_container.add_text(
                f"> 🏆 **{winner_label}:** {winner_mentions}\n"
                f"> 🎁 **Prize:** **{res['prize']}**\n"
                f"> 👑 **Hosted By:** <@{res['host_id']}>\n"
                f"> 👥 **Total Entries:** `{total_entries}`\n\n"
                f"> Congratulations! Contact <@{res['host_id']}> to claim your prize."
            )
            win_container.add_separator(divider=True)
            win_container.add_text("-# Drawn by Kyro • Congratulations!")
            try:
                await send_container_response(
                    channel,
                    win_container,
                    content=winner_mentions,
                )
            except Exception as e:
                logger.debug(f"Failed to announce giveaway winners: {e}")
        else:
            no_win_container = KyroContainer(accent_color=None)
            no_win_container.add_section(content="**Giveaway Ended**")
            no_win_container.add_separator(divider=True)
            no_win_container.add_text(
                f"{dot} The giveaway for **{res['prize']}** has ended, but no one entered."
            )
            no_win_container.add_separator(divider=True)
            no_win_container.add_text("-# Kyro Giveaway")
            try:
                await send_container_response(channel, no_win_container)
            except Exception as e:
                logger.debug(f"Failed to announce empty giveaway: {e}")

        return res

    # ─── COMMANDS ────────────────────────────────────────────────────────────

    @commands.hybrid_group(
        name="giveaway",
        aliases=["g"],
        invoke_without_command=True,
        description="Enterprise giveaway system with interactive Components V2 cards.",
    )
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def giveaway(self, ctx: CustomContext) -> None:
        """Display giveaway commands usage guide if invoked without subcommand."""
        if ctx.invoked_subcommand is not None:
            return
        container = self._build_usage_card(ctx)
        await send_container_response(ctx, container)

    @giveaway.command(
        name="start",
        description="Start a new interactive giveaway.",
    )
    @app_commands.describe(
        duration="How long the giveaway runs (e.g. 10m, 2h, 1d)",
        prize="The prize to give away (append '--role @Role' for role requirements)",
        winners="Number of winners to draw (defaults to 1)",
        required_role="Optional role required to enter",
    )
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def giveaway_start(
        self,
        ctx: CustomContext,
        duration: str,
        *,
        prize: str,
        winners: int = 1,
        required_role: Optional[discord.Role] = None,
    ) -> None:
        """Start a new giveaway."""
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)

        # Smart deduction if user passes winner count in prize string (e.g. .giveaway start 10m 2 Nitro)
        if winners == 1 and prize:
            parts = prize.split(maxsplit=1)
            if parts[0].isdigit() and len(parts) > 1:
                winners = int(parts[0])
                prize = parts[1]

        # Validate winners count
        if winners < 1:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Invalid Winners**")
            container.add_separator(divider=True)
            container.add_text(f"{dot} Number of winners must be at least 1.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, ephemeral=True)
            return

        if winners > 50:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Too Many Winners**")
            container.add_separator(divider=True)
            container.add_text(f"{dot} Maximum winner count is 50.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, ephemeral=True)
            return

        # Check role flag in prize if using prefix command
        req_role = required_role
        if not req_role and "--role" in prize:
            match = re.search(r"--role\s+(.+)$", prize, re.IGNORECASE)
            if match:
                role_query = match.group(1).strip()
                prize = prize[:match.start()].strip()
                req_role = resolve_role(ctx.guild, role_query)

        clean_prize = prize.strip()
        if not clean_prize:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Prize Required**")
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} Please enter what you want to give away.\n"
                f"> Example: `{prefix}gstart 10m Discord Nitro`"
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, ephemeral=True)
            return

        # Parse duration
        delta = parse_giveaway_duration(duration)
        if not delta:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Invalid Time**")
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} Please enter a valid time like `10m`, `2h`, or `1d`.\n"
                f"> `10m` = 10 minutes\n"
                f"> `2h` = 2 hours\n"
                f"> `1d` = 1 day"
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, ephemeral=True)
            return

        ends_at = datetime.datetime.now(datetime.timezone.utc) + delta
        gw_emoji = self.bot.custom_emojis.get("discord_giveaway", self.bot.custom_emojis.get("giveaway", "🎉"))
        thumb_url = get_giveaway_thumbnail(self.bot, ctx.guild, host_id=ctx.author.id)

        # Build initial Components V2 Card
        card = build_giveaway_container(
            prize=clean_prize,
            host_id=ctx.author.id,
            winner_count=winners,
            ends_at=ends_at,
            entries_count=0,
            required_role_id=req_role.id if req_role else None,
            gw_emoji=gw_emoji,
            thumbnail_url=thumb_url,
        )

        view = PersistentGiveawayView(self.bot)
        # Send into target channel
        giveaway_msg = await send_container_response(ctx.channel, card, view=view)

        # Store in database and memory cache
        await self.bot.giveaway_mgr.create_giveaway(
            guild_id=ctx.guild.id,
            channel_id=ctx.channel.id,
            message_id=giveaway_msg.id,
            host_id=ctx.author.id,
            prize=clean_prize,
            winner_count=winners,
            ends_at=ends_at,
            required_role_id=req_role.id if req_role else None,
        )

        # If slash command, acknowledge ephemeral confirmation
        if ctx.interaction and not ctx.interaction.response.is_done():
            ack = KyroContainer(accent_color=None)
            ack.add_section(content="**Giveaway Started**")
            ack.add_separator(divider=True)
            ack.add_text(f"{dot} Giveaway started in {ctx.channel.mention}!")
            ack.add_separator(divider=True)
            ack.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, ack, ephemeral=True)

    @giveaway.command(
        name="end",
        description="End an active giveaway now and pick winners.",
    )
    @app_commands.describe(message_id="The message ID of the giveaway (optional if in same channel)")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def giveaway_end(self, ctx: CustomContext, message_id: Optional[str] = None) -> None:
        """End a giveaway immediately (supports message ID, reply, or channel auto-detection)."""
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)

        # 1. Check if user replied to a message
        if not message_id and ctx.message and ctx.message.reference and ctx.message.reference.message_id:
            message_id = str(ctx.message.reference.message_id)

        # 2. Check if there's an active giveaway in this channel
        if not message_id:
            active_in_channel = [
                g for g in self.bot.giveaway_mgr._active_giveaways.values()
                if g["channel_id"] == ctx.channel.id
            ]
            if len(active_in_channel) == 1:
                message_id = str(active_in_channel[0]["message_id"])

        if not message_id or not message_id.isdigit():
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Giveaway Not Found**")
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} Please reply to the giveaway message or provide its message ID.\n"
                f"> Example: `{prefix}gend 123456789`"
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, ephemeral=True)
            return

        mid = int(message_id)
        gw = self.bot.giveaway_mgr.get_giveaway_by_message_id(mid)
        if not gw:
            gw_row = await self.bot.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", mid)
            if not gw_row:
                container = KyroContainer(accent_color=None)
                container.add_section(content="**Not Found**")
                container.add_separator(divider=True)
                container.add_text(f"{dot} No giveaway found with that message ID.")
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container, ephemeral=True)
                return
            if gw_row.get("is_ended"):
                container = KyroContainer(accent_color=None)
                container.add_section(content="**Already Ended**")
                container.add_separator(divider=True)
                container.add_text(f"{dot} This giveaway has already ended.")
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container, ephemeral=True)
                return

        res = await self.conclude_giveaway(mid)
        container = KyroContainer(accent_color=None)
        container.add_section(content="**Giveaway Ended**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} **Prize:** **{res['prize']}**\n"
            f"{dot} **Total Entries:** `{res.get('total_entries', 0)}`\n"
            f"{dot} **Ended By:** {ctx.author.mention}"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)

    @giveaway.command(
        name="reroll",
        description="Pick new random winners from an ended giveaway.",
    )
    @app_commands.describe(
        message_id="The message ID of the giveaway to reroll",
        winners="Number of new winners to select (defaults to 1)",
    )
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def giveaway_reroll(self, ctx: CustomContext, message_id: Optional[str] = None, winners: int = 1) -> None:
        """Reroll winners for an ended giveaway (supports message ID or reply)."""
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)

        if not message_id and ctx.message and ctx.message.reference and ctx.message.reference.message_id:
            message_id = str(ctx.message.reference.message_id)

        if not message_id or not message_id.isdigit():
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Giveaway Not Found**")
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} Please reply to the giveaway message or specify its message ID.\n"
                f"> Example: `{prefix}greroll 123456789`"
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, ephemeral=True)
            return

        mid = int(message_id)
        gw_row = await self.bot.db.fetch_one("SELECT * FROM giveaways WHERE message_id = $1;", mid)
        if not gw_row:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Not Found**")
            container.add_separator(divider=True)
            container.add_text(f"{dot} No giveaway found with that message ID.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, ephemeral=True)
            return

        if not gw_row.get("is_ended"):
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Giveaway Still Active**")
            container.add_separator(divider=True)
            container.add_text(f"{dot} This giveaway is still running. End it first using `.gend`.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, ephemeral=True)
            return

        count = max(1, min(winners, 50))
        reroll_res = await self.bot.giveaway_mgr.reroll_giveaway(mid, count=count)
        if not reroll_res:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**Error**")
            container.add_separator(divider=True)
            container.add_text(f"{dot} Failed to read giveaway participants.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, ephemeral=True)
            return

        data, new_winners = reroll_res
        gw_emoji = self.bot.custom_emojis.get("discord_giveaway", self.bot.custom_emojis.get("giveaway", "🎉"))
        thumb_url = get_giveaway_thumbnail(self.bot, ctx.guild, host_id=data.get("host_id"))

        if not new_winners:
            container = KyroContainer(accent_color=None)
            container.add_section(content="**No Participants**")
            container.add_separator(divider=True)
            container.add_text(
                f"{dot} No one entered the giveaway for **{data['prize']}**."
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        winner_mentions = ", ".join(f"<@{w}>" for w in new_winners)
        winner_label = "Winner" if len(new_winners) == 1 else "Winners"
        win_container = KyroContainer(accent_color=None)
        win_container.add_section(content=f"### {gw_emoji} New Winner Drawn {gw_emoji}")
        if thumb_url:
            win_container.add_thumbnail(thumb_url)
        win_container.add_separator(divider=True)
        win_container.add_text(
            f"> 🏆 **New {winner_label}:** {winner_mentions}\n"
            f"> 🎁 **Prize:** **{data['prize']}**\n"
            f"> 👑 **Rerolled By:** {ctx.author.mention}\n\n"
            f"> Congratulations! Contact the host to claim your prize."
        )
        win_container.add_separator(divider=True)
        win_container.add_text("-# Rerolled by Kyro")

        await send_container_response(ctx, win_container, content=winner_mentions)

    @giveaway.command(
        name="list",
        description="List all active giveaways currently running in this server.",
    )
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def giveaway_list(self, ctx: CustomContext) -> None:
        """List active server giveaways."""
        active_list = self.bot.giveaway_mgr.get_active_giveaways_for_guild(ctx.guild.id)
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        container = KyroContainer(accent_color=None)

        if not active_list:
            container.add_section(content="**Active Giveaways**")
            container.add_separator(divider=True)
            container.add_text(f"{dot} No giveaways are currently running in this server.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        lines = []
        for idx, g in enumerate(active_list, start=1):
            end_t = g["ends_at"]
            if end_t.tzinfo is None:
                end_t = end_t.replace(tzinfo=datetime.timezone.utc)
            ts = int(end_t.timestamp())
            msg_link = f"https://discord.com/channels/{ctx.guild.id}/{g['channel_id']}/{g['message_id']}"
            lines.append(
                f"{dot} **[{g['prize']}]({msg_link})**\n"
                f"  `•` Channel: <#{g['channel_id']}> | Winners: `{g['winner_count']}` | Ends: <t:{ts}:R>"
            )

        container.add_section(content=f"**Active Giveaways: {len(active_list)}**")
        container.add_separator(divider=True)
        container.add_text("\n".join(lines))
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")

        await send_container_response(ctx, container)

    # ─── CONVENIENCE PREFIX SHORTCUTS ────────────────────────────────────────

    @commands.command(name="gstart")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def shortcut_gstart(
        self,
        ctx: CustomContext,
        duration: Optional[str] = None,
        arg2: Optional[str] = None,
        *,
        rest: Optional[str] = None,
    ) -> None:
        """Shortcut command for .giveaway start with smart arguments deduction."""
        if not duration:
            container = self._build_usage_card(ctx)
            await send_container_response(ctx, container)
            return

        # Case 1: arg2 is a number (e.g. .gstart 10m 2 Discord Nitro)
        if arg2 and arg2.isdigit():
            winners = int(arg2)
            prize = rest or ""
        # Case 2: arg2 is text (e.g. .gstart 10m Discord Nitro) -> winners defaults to 1
        elif arg2:
            winners = 1
            prize = f"{arg2} {rest}" if rest else arg2
        else:
            container = self._build_usage_card(ctx)
            await send_container_response(ctx, container)
            return

        await self.giveaway_start(ctx, duration=duration, winners=winners, prize=prize)

    @commands.command(name="gend")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def shortcut_gend(self, ctx: CustomContext, message_id: Optional[str] = None) -> None:
        """Shortcut command for .giveaway end with reply & auto-channel detection."""
        await self.giveaway_end(ctx, message_id=message_id)

    @commands.command(name="greroll")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def shortcut_greroll(
        self,
        ctx: CustomContext,
        message_id: Optional[str] = None,
        winners: int = 1,
    ) -> None:
        """Shortcut command for .giveaway reroll with reply support."""
        await self.giveaway_reroll(ctx, message_id=message_id, winners=winners)

    @commands.command(name="glist")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def shortcut_glist(self, ctx: CustomContext) -> None:
        """Shortcut command for .giveaway list."""
        await self.giveaway_list(ctx)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Giveaways(bot))
