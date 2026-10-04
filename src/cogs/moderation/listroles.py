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

logger = logging.getLogger("Kyro.Moderation.ListRoles")


class RoleListPaginationView(discord.ui.View):
    """Clean interactive pagination view for server roles list."""

    def __init__(self, ctx: CustomContext, roles: list[discord.Role], per_page: int = 15) -> None:
        super().__init__(timeout=90)
        self.ctx = ctx
        self.roles = roles
        self.per_page = per_page
        self.page = 0
        self.max_page = max(0, math.ceil(len(roles) / per_page) - 1)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.clear_items()
        if self.max_page > 0:
            if self.max_page > 2:
                first_btn = discord.ui.Button(
                    label="⏮",
                    style=discord.ButtonStyle.secondary,
                    disabled=self.page == 0,
                )
                first_btn.callback = self._first_callback
                self.add_item(first_btn)

                prev_btn = discord.ui.Button(
                    label="◀",
                    style=discord.ButtonStyle.secondary,
                    disabled=self.page == 0,
                )
                prev_btn.callback = self._prev_callback
                self.add_item(prev_btn)

                page_indicator = discord.ui.Button(
                    label=f"{self.page + 1} / {self.max_page + 1}",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                )
                self.add_item(page_indicator)

                next_btn = discord.ui.Button(
                    label="▶",
                    style=discord.ButtonStyle.secondary,
                    disabled=self.page == self.max_page,
                )
                next_btn.callback = self._next_callback
                self.add_item(next_btn)

                last_btn = discord.ui.Button(
                    label="⏭",
                    style=discord.ButtonStyle.secondary,
                    disabled=self.page == self.max_page,
                )
                last_btn.callback = self._last_callback
                self.add_item(last_btn)
            else:
                prev_btn = discord.ui.Button(
                    label="◀ Previous",
                    style=discord.ButtonStyle.secondary,
                    disabled=self.page == 0,
                )
                prev_btn.callback = self._prev_callback
                self.add_item(prev_btn)

                page_indicator = discord.ui.Button(
                    label=f"{self.page + 1} / {self.max_page + 1}",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                )
                self.add_item(page_indicator)

                next_btn = discord.ui.Button(
                    label="Next ▶",
                    style=discord.ButtonStyle.secondary,
                    disabled=self.page == self.max_page,
                )
                next_btn.callback = self._next_callback
                self.add_item(next_btn)

    async def _first_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can flip pages.", ephemeral=True)
            return
        if self.page > 0:
            self.page = 0
            self._update_buttons()
            container = self.render_container()
            await edit_container_response(interaction, container, view=self)

    async def _last_callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the command invoker can flip pages.", ephemeral=True)
            return
        if self.page < self.max_page:
            self.page = self.max_page
            self._update_buttons()
            container = self.render_container()
            await edit_container_response(interaction, container, view=self)

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
        current_slice = self.roles[start:end]

        lines = []
        for idx, r in enumerate(current_slice, start=start + 1):
            member_count = len(r.members)
            member_suffix = "member" if member_count == 1 else "members"
            lines.append(f"`#{idx:02d}` │ `@{r.name}` ➔ `{member_count:,} {member_suffix}`")

        container = KyroContainer(accent_color=0xF472B6)
        container.add_text(
            f"### {self.ctx.guild.name} — Roles\n"
            f"-# Total {len(self.roles)} roles in this server"
        )
        container.add_separator(divider=True)
        container.add_text("\n".join(lines))
        # Divider line above footer
        container.add_separator(divider=True)
        container.add_text(f"-# Page {self.page + 1} of {self.max_page + 1} • Requested by {self.ctx.author.name}")
        # Divider line above buttons
        if self.max_page > 0:
            container.add_separator(divider=True)
        return container

    async def on_timeout(self) -> None:
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class ListRoles(commands.Cog, name="Moderation-ListRoles"):
    """Server roles hierarchy explorer."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="listroles",
        aliases=["roles", "rolelist"],
        description="Display all roles in this server sorted by hierarchy with member counts.",
    )
    @commands.guild_only()
    async def listroles(self, ctx: CustomContext) -> None:
        """Display all roles in hierarchy order."""
        if not ctx.guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        # Sort descending by position, excluding @everyone
        roles = [r for r in ctx.guild.roles if not r.is_default()]
        roles.sort(key=lambda r: r.position, reverse=True)

        if not roles:
            await ctx.send_warning("This server has no custom roles created.")
            return

        view = RoleListPaginationView(ctx, roles, per_page=15)
        container = view.render_container()
        if view.max_page > 0:
            await send_container_response(ctx, container, view=view)
        else:
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(ListRoles(bot))
