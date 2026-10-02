from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    KyroContainer,
    send_container_response,
    edit_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.General.Avatar")


class AvatarView(discord.ui.View):
    """View handling server/global avatar toggle if member has a separate server avatar."""

    def __init__(
        self,
        ctx: CustomContext,
        target: discord.Member | discord.User,
        global_url: str,
        guild_url: str | None = None,
        initial_mode: str = "guild",
    ) -> None:
        super().__init__(timeout=120)
        self.ctx = ctx
        self.target = target
        self.global_url = global_url
        self.guild_url = guild_url
        self.current_mode = initial_mode if guild_url else "global"
        self._build_components()

    def _build_components(self) -> None:
        self.clear_items()
        # Only display toggle button if server avatar is distinct from global avatar
        if self.guild_url and self.guild_url != self.global_url:
            label = "Global Avatar" if self.current_mode == "guild" else "Server Avatar"
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                custom_id="toggle_avatar",
            )
            btn.callback = self._toggle_callback
            self.add_item(btn)

    async def _toggle_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can toggle this view.", ephemeral=True)
            return

        self.current_mode = "global" if self.current_mode == "guild" else "guild"
        self._build_components()

        container = self.render_container()
        await edit_container_response(interaction, container, view=self if len(self.children) > 0 else None)

    def render_container(self) -> KyroContainer:
        active_url = self.guild_url if self.current_mode == "guild" and self.guild_url else self.global_url
        hd_url = f"{active_url}?size=4096" if "?" not in active_url else f"{active_url}&size=4096"
        dl_str = self.ctx.bot.custom_emojis.get("icons_download", "📥")

        container = KyroContainer(accent_color=None)
        # Clean title with direct download link at the top, no mentions, no dots
        container.add_section(content=f"**{self.target.name}** • {dl_str} [Download HD]({hd_url})")
        container.add_separator(divider=True)
        container.add_media(f"{active_url}?size=1024" if "?" not in active_url else active_url)
        return container

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class Avatar(commands.Cog, name="General-Avatar"):
    """User Avatar Suite."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="avatar",
        aliases=["av"],
        description="Display a user's high-resolution avatar.",
    )
    @app_commands.describe(member="Member or user whose avatar you wish to view")
    async def avatar(
        self,
        ctx: CustomContext,
        member: Optional[discord.Member | discord.User] = None,
    ) -> None:
        """View user avatar with top download link."""
        target = member or ctx.author

        full_user = target
        try:
            full_user = await self.bot.fetch_user(target.id)
        except Exception:
            pass

        global_url = str(full_user.avatar.url if full_user.avatar else full_user.default_avatar.url)
        guild_url = None
        if isinstance(target, discord.Member) and target.guild_avatar:
            guild_url = str(target.guild_avatar.url)

        initial_mode = "guild" if guild_url else "global"
        view = AvatarView(
            ctx=ctx,
            target=target,
            global_url=global_url,
            guild_url=guild_url,
            initial_mode=initial_mode,
        )
        container = view.render_container()

        # Only attach view if toggle button exists
        if len(view.children) > 0:
            await send_container_response(ctx, container, view=view)
        else:
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Avatar(bot))
