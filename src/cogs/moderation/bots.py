from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Moderation.Bots")


class BotsPaginationView(discord.ui.View):
    """Interactive pagination for bot accounts list."""

    def __init__(self, ctx: CustomContext, bots: list[discord.Member], per_page: int = 15) -> None:
        super().__init__(timeout=90)
        self.ctx = ctx
        self.bots = bots
        self.per_page = per_page
        self.page = 0
        self.max_page = max(0, math.ceil(len(bots) / per_page) - 1)
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
        current_slice = self.bots[start:end]

        lines = []
        for b in current_slice:
            role_str = f"`@{b.top_role.name}`" if b.top_role != self.ctx.guild.default_role else "No Role"
            lines.append(f"{b.name} (ID: `{b.id}`) — {role_str}")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Server Bot Accounts ({len(self.bots)})\n"
                f"> Page `{self.page + 1}` of `{self.max_page + 1}`\n\n"
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


class Bots(commands.Cog, name="Moderation-Bots"):
    """Server bot discovery."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="bots",
        aliases=["botlist"],
        description="Display all bot accounts integrated into this server.",
    )
    @commands.guild_only()
    async def bots(self, ctx: CustomContext) -> None:
        """List all bot accounts in the server."""
        if not ctx.guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        bot_members = [m for m in ctx.guild.members if m.bot]
        bot_members.sort(key=lambda b: b.top_role.position, reverse=True)

        if not bot_members:
            await ctx.send_warning("No bot accounts found in this server.")
            return

        view = BotsPaginationView(ctx, bot_members, per_page=15)
        container = view.render_container()
        if view.max_page > 0:
            await send_container_response(ctx, container, view=view)
        else:
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Bots(bot))
