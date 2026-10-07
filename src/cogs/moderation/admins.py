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

logger = logging.getLogger("Kyro.Moderation.Admins")


class AdminListPaginationView(discord.ui.View):
    """Clean interactive pagination view for server administrators list."""

    def __init__(self, ctx: CustomContext, members: list[discord.Member], per_page: int = 10) -> None:
        super().__init__(timeout=90)
        self.ctx = ctx
        self.members = members
        self.per_page = per_page
        self.page = 0
        self.max_page = max(0, math.ceil(len(members) / per_page) - 1)
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.clear_items()
        if self.max_page > 0:
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

        e_reg = self.ctx.bot.custom_emojis
        dot = e_reg.get("heart_dot", "❥")

        lines = []
        for m in current_slice:
            if m.id == self.ctx.guild.owner_id:
                badge = "Owner"
            elif m.bot:
                badge = f"Bot • @{m.top_role.name}" if m.top_role != self.ctx.guild.default_role else "Bot"
            else:
                badge = f"@{m.top_role.name}" if m.top_role != self.ctx.guild.default_role else "Admin"
            lines.append(f"{dot} `@{m.name}` **—** `「{badge}」`\n  └ `「{m.id}」`")

        container = KyroContainer(accent_color=None)
        container.add_text(
            f"### {self.ctx.guild.name} — Administrators\n"
            f"-# Total {len(self.members)} administrators in this server"
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


class Admins(commands.Cog, name="Moderation-Admins"):
    """Server administrator audit module."""
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="admins",
        aliases=["adminroles", "listadmins", "adminlist"],
        description="Audit and list all members holding Administrator permissions.",
    )
    @commands.guild_only()
    async def admins(self, ctx: CustomContext) -> None:
        """List all administrator members in hierarchy order."""
        guild = ctx.guild
        if not guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        admin_members = [m for m in guild.members if m.guild_permissions.administrator]
        # Sort descending: Server Owner first, then by top role position, humans before bots
        admin_members.sort(
            key=lambda m: (
                m.id == guild.owner_id,
                not m.bot,
                m.top_role.position,
            ),
            reverse=True,
        )

        if not admin_members:
            await ctx.send_warning("No administrators found in this server.")
            return

        view = AdminListPaginationView(ctx, admin_members, per_page=10)
        container = view.render_container()
        if view.max_page > 0:
            await send_container_response(ctx, container, view=view)
        else:
            await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Admins(bot))
