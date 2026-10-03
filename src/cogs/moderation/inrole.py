"""
Kyro Discord Bot - Role Members Viewer (inrole) Module
Lists members holding a specific role with Discord Components V2 pagination and flexible resolution.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.cogs.moderation._helpers import resolve_role
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

        e_reg = self.ctx.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        lines: list[str] = []
        for m in current_slice:
            tag = " `[BOT]`" if m.bot else ""
            lines.append(f"{dot} **{m.display_name}**{tag} (`{m.id}`)")

        accent = self.role.color.value if self.role.color.value else None
        container = KyroContainer(accent_color=accent)

        count = len(self.members)
        count_str = f"{count:,} member" if count == 1 else f"{count:,} members"

        # Header Section
        container.add_section(
            content=(
                f"**Role Members**\n"
                f"> Showing {count_str} with {self.role.mention}."
            )
        )
        container.add_separator(divider=True)

        # Members list
        container.add_text("\n".join(lines) if lines else f"{dot} No members found on this page.")
        container.add_separator(divider=True)

        # Unified single footer
        page_info = f"Page {self.page + 1} of {self.max_page + 1} • " if self.max_page > 0 else ""
        container.add_text(f"-# {page_info}Requested by {self.ctx.author.display_name}")
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

    def _build_usage_card(self, ctx: CustomContext) -> KyroContainer:
        """Construct the Components V2 usage guide for inrole."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Inrole Usage**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} `{prefix}inrole <@role>`\n"
            f"{dot} `{prefix}inrole <role-id>`\n"
            f"{dot} `{prefix}inrole <role-name>`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    @commands.hybrid_command(
        name="inrole",
        aliases=["rolemembers"],
        description="Display all members who possess a specific role.",
    )
    @app_commands.describe(role="Role mention, ID, or name to inspect")
    @commands.guild_only()
    async def inrole(self, ctx: CustomContext, *, role: Optional[str] = None) -> None:
        """List all members who have the specified role."""
        guild = ctx.guild
        if not guild:
            await ctx.send_warning("This command can only be used in a server.")
            return

        # Case 1: No role passed -> Show clean usage card
        if not role or not role.strip():
            container = self._build_usage_card(ctx)
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        # Case 2: Resolve role by mention, ID, or name
        target_role = resolve_role(guild, role)
        if not target_role:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Role Not Found**\n"
                    f"> Could not find any role matching `{role}` in this server."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        # Protection: @everyone cannot be enumerated
        if target_role.is_default():
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    "**Invalid Target**\n"
                    "> Cannot list members for `@everyone`. Please use the `membercount` command instead."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        # Ensure all members are cached for large guilds
        if not guild.chunked:
            try:
                await guild.chunk(cache=True)
            except Exception as e:
                logger.debug(f"Guild chunking skipped/failed: {e}")

        members = target_role.members
        if not members:
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**Role Members**\n"
                    f"> No members currently have the {target_role.mention} role."
                )
            )
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())
            return

        view = InRolePaginationView(ctx, target_role, members, per_page=15)
        container = view.render_container()
        if view.max_page > 0:
            await send_container_response(ctx, container, view=view, allowed_mentions=discord.AllowedMentions.none())
        else:
            await send_container_response(ctx, container, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: KyroBot) -> None:
    """Load the InRole cog into KyroBot."""
    await bot.add_cog(InRole(bot))
