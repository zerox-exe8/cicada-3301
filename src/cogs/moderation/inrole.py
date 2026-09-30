"""
Kyro Discord Bot - In-Role Members Explorer Module
Lists all members who possess a specific role with interactive pagination.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.InRole")


class InRolePaginationView(discord.ui.View):
    """Interactive pagination for members in a role."""

    def __init__(self, ctx: CustomContext, role: discord.Role, members: list[discord.Member], per_page: int = 15) -> None:
        super().__init__(timeout=90)
        self.ctx = ctx
        self.role = role
        self.members = members
        self.per_page = per_page
        self.page = 0
        self.max_page = max(0, math.ceil(len(members) / per_page) - 1)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.clear_items()
        if self.max_page > 0:
            prev_btn = discord.ui.Button(
                label="Previous",
                style=discord.ButtonStyle.secondary,
                disabled=self.page == 0,
            )
            prev_btn.callback = self._prev_callback
            self.add_item(prev_btn)

            next_btn = discord.ui.Button(
                label="Next",
                style=discord.ButtonStyle.secondary,
                disabled=self.page == self.max_page,
            )
            next_btn.callback = self._next_callback
            self.add_item(next_btn)

    async def _prev_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can flip pages.", ephemeral=True)
            return
        if self.page > 0:
            self.page -= 1
            self._update_buttons()
            container = self.render_container()
            await edit_container_response(interaction, container, view=self)

    async def _next_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can flip pages.", ephemeral=True)
            return
        if self.page < self.max_page:
            self.page += 1
            self._update_buttons()
            container = self.render_container()
            await edit_container_response(interaction, container, view=self)

    def render_container(self) -> KyroContainer:
        start = self.page * self.per_page
        end = start + self.per_page
        current_slice = self.members[start:end]

        lines = [f"• {m.mention} (`{m.name}`)" for m in current_slice]

        container = KyroContainer(accent_color=self.role.color.value if self.role.color.value else None)
        container.add_section(
            content=(
                f"### Members with {self.role.name} ({len(self.members)})\n"
                f"> Role: {self.role.mention} • Page `{self.page + 1}` of `{self.max_page + 1}`\n\n"
                + "\n".join(lines)
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {self.ctx.author.display_name}")
        return container

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class InRole(commands.Cog, name="Moderation-InRole"):
    """Role member roster viewer."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="inrole",
        aliases=["rolemembers"],
        description="Display all members who possess a specific role.",
    )
    @app_commands.describe(role="Role whose members you wish to view")
    @commands.guild_only()
    async def inrole(self, ctx: CustomContext, *, role: discord.Role) -> None:
        """List all members who have the specified role."""
        members = role.members
        if not members:
            await ctx.send_warning(f"No members currently have the {role.mention} role.")
            return

        view = InRolePaginationView(ctx, role, members, per_page=15)
        container = view.render_container()
        if view.max_page > 0:
            await send_container_response(ctx, container, view=view)
        else:
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(InRole(bot))
