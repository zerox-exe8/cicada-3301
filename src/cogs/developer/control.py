"""
Kyro Discord Bot - Secret Developer Remote Control Suite
Owner-only hidden tools: Server Portal invite generator, Anonymous DM, Dynamic Status & Profile modifiers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional
import aiohttp
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.managers.permission_manager import is_developer, is_owner
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class ControlCog(commands.Cog, name="Developer-Control"):
    """Secret remote administrative suite for bot owner."""
    category: str = "Developer"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(name="portal", aliases=["ginv", "guildinvite"], hidden=True)
    @is_developer()
    async def server_portal(self, ctx: CustomContext, *, guild_query: str) -> None:
        """
        Generate an instant 1-hour access invite link to any server the bot is joined in.
        Usage:
          ?portal <guild_id>
          ?portal <guild_name>
        """
        target_guild: Optional[discord.Guild] = None

        if guild_query.isdigit():
            target_guild = self.bot.get_guild(int(guild_query))

        if not target_guild:
            target_guild = discord.utils.find(
                lambda g: guild_query.lower() in g.name.lower(), self.bot.guilds
            )

        if not target_guild:
            await ctx.send_error(f"Could not locate connected server matching `{guild_query}`.")
            return

        # Locate a valid text channel with invite creation capability
        invite_url: Optional[str] = None
        for channel in target_guild.text_channels:
            perms = channel.permissions_for(target_guild.me)
            if perms.create_instant_invite:
                try:
                    invite = await channel.create_invite(
                        max_age=3600,
                        max_uses=1,
                        reason=f"Portal request by Bot Developer: {ctx.author}",
                    )
                    invite_url = invite.url
                    break
                except discord.HTTPException:
                    continue

        if not invite_url:
            await ctx.send_error(f"No text channels in `{target_guild.name}` allow invite creation.")
            return

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Server Portal Established**\n"
                f"> **Server:** `{target_guild.name}` (`{target_guild.id}`)\n"
                f"> **Owner:** `{target_guild.owner}` (`{target_guild.owner_id}`)\n"
                f"> **Members:** `{target_guild.member_count:,}`\n"
                f"> **Portal Link:** [Click to Join Server]({invite_url})"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Single-use link valid for 1 hour • Stealth Developer Access")
        await send_container_response(ctx, container)

    @commands.command(name="dm", aliases=["whisper", "secretmsg"], hidden=True)
    @is_developer()
    async def secret_dm(self, ctx: CustomContext, user: discord.User, *, message: str) -> None:
        """
        Anonymously send an official Kyro embed DM to any Discord user.
        Usage:
          ?dm @user Message text
          ?dm <user_id> Message text
        """
        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Incoming Official Message**\n"
                f"> {message}"
            )
        )
        container.add_separator(divider=True)
        container.add_text("-# Sent via Kyro Core Network")

        try:
            await user.send(embed=container.to_embed())
            confirm = KyroContainer(accent_color=None)
            confirm.add_section(
                content=f"Secret DM successfully delivered to `{user}` (`{user.id}`)."
            )
            await send_container_response(ctx, confirm)
        except discord.Forbidden:
            await ctx.send_error(f"Cannot deliver DM: User `{user}` has Direct Messages disabled.")
        except discord.HTTPException as err:
            await ctx.send_error(f"Failed to deliver DM: {err}")

    @commands.command(name="setstatus", aliases=["activity", "changestatus"], hidden=True)
    @is_owner()
    async def change_status(self, ctx: CustomContext, activity_type: str, *, status_text: str) -> None:
        """
        Live update bot presence activity from chat.
        Usage:
          ?setstatus playing <text>
          ?setstatus listening <text>
          ?setstatus watching <text>
          ?setstatus competing <text>
          ?setstatus streaming <text>
        """
        act_lower = activity_type.lower()
        activity: discord.BaseActivity

        if act_lower in ("playing", "play"):
            activity = discord.Game(name=status_text)
        elif act_lower in ("streaming", "stream"):
            activity = discord.Streaming(name=status_text, url="https://twitch.tv/discord")
        elif act_lower in ("listening", "listen"):
            activity = discord.Activity(type=discord.ActivityType.listening, name=status_text)
        elif act_lower in ("watching", "watch"):
            activity = discord.Activity(type=discord.ActivityType.watching, name=status_text)
        elif act_lower in ("competing", "compete"):
            activity = discord.Activity(type=discord.ActivityType.competing, name=status_text)
        else:
            activity = discord.CustomActivity(name=f"{activity_type} {status_text}")

        await self.bot.change_presence(status=discord.Status.dnd, activity=activity)

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Presence Activity Updated**\n"
                f"> **Type:** `{act_lower.title()}`\n"
                f"> **Activity:** `{status_text}`\n"
                f"> **Status:** `Live Across All Shards`"
            )
        )
        await send_container_response(ctx, container)

    @commands.command(name="setavatar", aliases=["changeavatar"], hidden=True)
    @is_owner()
    async def change_avatar(self, ctx: CustomContext, url: Optional[str] = None) -> None:
        """
        Live update bot profile avatar image.
        Usage:
          ?setavatar <image_url>
          ?setavatar (with image attachment)
        """
        image_url = url
        if not image_url and ctx.message.attachments:
            image_url = ctx.message.attachments[0].url

        if not image_url:
            await ctx.send_error("Please supply an image URL or attach an image to change avatar.")
            return

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(image_url) as resp:
                    if resp.status != 200:
                        await ctx.send_error(f"Failed to fetch image: HTTP {resp.status}")
                        return
                    img_data = await resp.read()
            except Exception as e:
                await ctx.send_error(f"Error downloading image: {e}")
                return

        try:
            await self.bot.user.edit(avatar=img_data)
            container = KyroContainer(accent_color=None)
            container.add_section(
                content="**Bot Avatar Updated Successfully**\n> New profile photo is now live."
            )
            await send_container_response(ctx, container)
        except discord.HTTPException as err:
            await ctx.send_error(f"Failed to update avatar: {err}")

    @commands.command(name="setname", aliases=["changename", "botname"], hidden=True)
    @is_owner()
    async def change_bot_name(self, ctx: CustomContext, *, new_name: str) -> None:
        """
        Live update bot username.
        Usage:
          ?setname NewBotName
        """
        try:
            await self.bot.user.edit(username=new_name.strip())
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=f"**Bot Name Updated**\n> Username changed to `{new_name.strip()}`."
            )
            await send_container_response(ctx, container)
        except discord.HTTPException as err:
            await ctx.send_error(f"Failed to update bot name: {err}")


async def setup(bot: KyroBot) -> None:
    """Load ControlCog into KyroBot."""
    await bot.add_cog(ControlCog(bot))
