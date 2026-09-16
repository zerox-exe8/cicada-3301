"""
Kyro Discord Bot - Anonymous Confessions Suite
Enables server members to submit anonymous community confessions and secret feedback
dispatched as official, high-trust Kyro Components V2 container cards without webhooks.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class ConfessSubmitModal(discord.ui.Modal):
    """Modal to submit an anonymous confession."""

    def __init__(self, cog: ConfessionsCog, guild_id: int) -> None:
        super().__init__(title="Anonymous Confession")
        self.cog = cog
        self.guild_id = guild_id

        self.confession_input = discord.ui.TextInput(
            label="Your Secret / Confession",
            style=discord.TextStyle.paragraph,
            placeholder="Type your confession here... 100% anonymous.",
            required=True,
            max_length=1000,
        )
        self.add_item(self.confession_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        text = self.confession_input.value.strip()
        if not text:
            await interaction.response.send_message("Confession cannot be empty.", ephemeral=True)
            return

        guild = interaction.guild
        if not guild:
            return

        settings = await self.cog._get_settings(guild.id)
        if not settings or not settings.get("channel_id"):
            await interaction.response.send_message(
                "Confessions channel is not yet configured. Please ask a server admin to run `?confess setchannel #channel`.",
                ephemeral=True,
            )
            return

        target_channel = guild.get_channel(settings["channel_id"])
        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            await interaction.response.send_message("Configured confessions channel was not found.", ephemeral=True)
            return

        clean_content = text.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
        new_counter = (settings.get("counter") or 0) + 1
        settings["counter"] = new_counter

        await self.cog.bot.db.execute(
            """
            INSERT INTO guild_confession_settings (guild_id, channel_id, counter, is_enabled)
            VALUES ($1, $2, $3, TRUE)
            ON CONFLICT (guild_id)
            DO UPDATE SET counter = $3;
            """,
            guild.id,
            settings["channel_id"],
            new_counter,
        )

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Kyro Confession #{new_counter}**\n"
                f"> {clean_content}"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"-# **100% Anonymous Submission** | {discord.utils.utcnow().strftime('%b %d, %Y')}"
        )

        try:
            await send_container_response(target_channel, container)
            await interaction.response.send_message(
                f"Your confession has been posted anonymously as **Confession #{new_counter}** in {target_channel.mention}!",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(f"Failed to post confession: {e}", ephemeral=True)


class ConfessDashboardView(discord.ui.View):
    """Interactive dashboard view with Submit Confession button."""

    def __init__(self, cog: ConfessionsCog, guild_id: int) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Submit a Confession", style=discord.ButtonStyle.primary, custom_id="confess_btn_submit")
    async def submit_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        modal = ConfessSubmitModal(self.cog, self.guild_id)
        await interaction.response.send_modal(modal)


class ConfessionsCog(commands.Cog, name="Games-Confessions"):
    """Anonymous confessions and community secrets suite."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # In-memory settings cache: guild_id -> (channel_id, counter, is_enabled)
        self._confess_cache: dict[int, dict] = {}

    async def _get_settings(self, guild_id: int) -> Optional[dict]:
        """Fetch and cache confession channel settings."""
        if guild_id in self._confess_cache:
            return self._confess_cache[guild_id]

        row = await self.bot.db.fetch_one(
            "SELECT channel_id, counter, is_enabled FROM guild_confession_settings WHERE guild_id = $1;",
            guild_id,
        )
        if row:
            data = {
                "channel_id": row["channel_id"],
                "counter": row["counter"] or 0,
                "is_enabled": row["is_enabled"] if row["is_enabled"] is not None else True,
            }
            self._confess_cache[guild_id] = data
            return data
        return None

    @commands.group(
        name="confess",
        aliases=["confession"],
        invoke_without_command=True,
        description="Submit an anonymous confession or view the confessions console.",
    )
    @commands.guild_only()
    async def confess(self, ctx: CustomContext, *, message: Optional[str] = None) -> None:
        """Submit an anonymous confession or open the interactive confession dashboard."""
        guild = ctx.guild
        if not guild:
            return

        settings = await self._get_settings(guild.id)

        # If user ran ?confess without arguments: show interactive dashboard!
        if not message or not message.strip():
            channel_mention = f"<#{settings['channel_id']}>" if settings and settings.get("channel_id") else "`Not Set`"
            total_posted = settings.get("counter", 0) if settings else 0

            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**{Config.BOT_NAME} Anonymous Confessions**\n"
                    "> Share your thoughts, secret crushes, and feedback 100% anonymously.\n"
                    f"> **Confessions Channel:** {channel_mention} | **Total Posted:** `{total_posted}`"
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"-# **How to confess:**\n"
                f"- Click the **Submit a Confession** button below, or type `{ctx.clean_prefix}confess <your message>`.\n"
                f"- Admins can bind target channel with `{ctx.clean_prefix}confess setchannel #channel`."
            )

            view = ConfessDashboardView(self, guild.id)
            await send_container_response(ctx, container, view=view)
            return

        # If user provided a message:
        # If no channel is set and author is administrator, auto-bind current channel
        if not settings or not settings.get("channel_id"):
            if ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator:
                await self.bot.db.execute(
                    """
                    INSERT INTO guild_confession_settings (guild_id, channel_id, counter, is_enabled)
                    VALUES ($1, $2, 0, TRUE)
                    ON CONFLICT (guild_id)
                    DO UPDATE SET channel_id = $2, is_enabled = TRUE;
                    """,
                    guild.id,
                    ctx.channel.id,
                )
                settings = {"channel_id": ctx.channel.id, "counter": 0, "is_enabled": True}
                self._confess_cache[guild.id] = settings
            else:
                await ctx.send_error(
                    f"Confessions channel is not yet configured. Please ask an admin to run `{ctx.clean_prefix}confess setchannel #channel`."
                )
                return

        if not settings.get("is_enabled"):
            await ctx.send_error("Confessions are currently disabled in this server.")
            return

        target_channel = guild.get_channel(settings["channel_id"])
        if not target_channel or not isinstance(target_channel, discord.TextChannel):
            await ctx.send_error("Configured confessions channel was not found or is invalid.")
            return

        clean_content = message.strip()
        clean_content = clean_content.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")

        # Delete user invocation message if prefix was used
        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        # Increment counter
        new_counter = (settings.get("counter") or 0) + 1
        settings["counter"] = new_counter

        await self.bot.db.execute(
            """
            INSERT INTO guild_confession_settings (guild_id, channel_id, counter, is_enabled)
            VALUES ($1, $2, $3, TRUE)
            ON CONFLICT (guild_id)
            DO UPDATE SET counter = $3;
            """,
            guild.id,
            settings["channel_id"],
            new_counter,
        )

        # Build official confession card
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Kyro Confession #{new_counter}**\n"
                f"> {clean_content}"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"-# **100% Anonymous Submission** | {discord.utils.utcnow().strftime('%b %d, %Y')}\n"
            f"-# Submit your own using `{ctx.clean_prefix}confess <message>`"
        )

        try:
            await send_container_response(target_channel, container)
        except Exception as err:
            await ctx.send_error(f"Failed to post confession to target channel: {err}")
            return

        # Acknowledge author
        if ctx.interaction:
            await ctx.interaction.response.send_message(
                f"Your confession has been posted anonymously as **Confession #{new_counter}** in {target_channel.mention}!",
                ephemeral=True,
            )
        else:
            try:
                await ctx.author.send(
                    f"Your confession was posted anonymously as **Confession #{new_counter}** in **{guild.name}** ({target_channel.mention})!"
                )
            except discord.HTTPException:
                pass

    @confess.command(
        name="setchannel",
        aliases=["channel", "bind"],
        description="Bind the channel where anonymous confessions are automatically posted.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def confess_setchannel(self, ctx: CustomContext, channel: discord.TextChannel) -> None:
        """Bind target text channel for confessions."""
        guild = ctx.guild
        if not guild:
            return

        me = guild.me
        if not channel.permissions_for(me).send_messages:
            await ctx.send_error(f"I do not have permission to send messages in {channel.mention}.")
            return

        await self.bot.db.execute(
            """
            INSERT INTO guild_confession_settings (guild_id, channel_id, counter, is_enabled)
            VALUES ($1, $2, 0, TRUE)
            ON CONFLICT (guild_id)
            DO UPDATE SET channel_id = $2, is_enabled = TRUE;
            """,
            guild.id,
            channel.id,
        )

        # Update cache
        if guild.id in self._confess_cache:
            self._confess_cache[guild.id]["channel_id"] = channel.id
            self._confess_cache[guild.id]["is_enabled"] = True
        else:
            self._confess_cache[guild.id] = {"channel_id": channel.id, "counter": 0, "is_enabled": True}

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Confessions Channel Configured**\n"
                f"> Successfully bound anonymous confessions to {channel.mention}.\n"
                f"> Members can now type `{ctx.clean_prefix}confess <message>` or click **Submit a Confession**."
            )
        )
        await send_container_response(ctx, container)

    @confess.command(
        name="toggle",
        description="Enable or disable anonymous confessions in this server.",
    )
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def confess_toggle(self, ctx: CustomContext) -> None:
        """Toggle confessions ON or OFF."""
        guild = ctx.guild
        if not guild:
            return

        settings = await self._get_settings(guild.id)
        if not settings or not settings.get("channel_id"):
            await ctx.send_error(f"Please set a confessions channel first with `{ctx.clean_prefix}confess setchannel #channel`.")
            return

        new_status = not settings.get("is_enabled", True)
        settings["is_enabled"] = new_status

        await self.bot.db.execute(
            "UPDATE guild_confession_settings SET is_enabled = $1 WHERE guild_id = $2;",
            new_status,
            guild.id,
        )

        status_text = "Enabled" if new_status else "Disabled"
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Confessions System {status_text}**\n"
                f"> Anonymous confessions are now **{status_text.lower()}** in this server."
            )
        )
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load the Confessions cog into KyroBot."""
    await bot.add_cog(ConfessionsCog(bot))
