"""
Kyro Discord Bot - Interactive Live Poll & Community Voting Suite
Presents dynamic, real-time interactive poll cards using Discord Components V2.
Features live vote progress bars, single-click vote toggling, and duplicate vote prevention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


def render_progress_bar(percentage: float, length: int = 12) -> str:
    """Render a clean Unicode block percentage bar."""
    filled_length = int(length * percentage / 100)
    empty_length = length - filled_length
    return "█" * filled_length + "░" * empty_length


class PollButton(discord.ui.Button):
    """Dynamic interactive vote button."""

    def __init__(self, option_index: int, label: str) -> None:
        super().__init__(
            label=label[:80],
            style=discord.ButtonStyle.secondary,
            custom_id=f"poll_opt_{option_index}",
        )
        self.option_index = option_index

    async def callback(self, interaction: discord.Interaction) -> None:
        view: PollView = self.view  # type: ignore
        user_id = interaction.user.id

        current_vote = view.votes.get(user_id)
        if current_vote == self.option_index:
            # User clicked the same option -> remove vote
            view.votes.pop(user_id, None)
            ack_msg = "Your vote has been removed."
        else:
            # Cast / switch vote
            view.votes[user_id] = self.option_index
            ack_msg = f"Voted for **{view.options[self.option_index]}**!"

        # Re-render container card
        updated_container = view.build_poll_container()
        await edit_container_response(interaction, updated_container, view=view)


class PollView(discord.ui.View):
    """Interactive Discord UI View managing live poll votes."""

    def __init__(self, question: str, options: list[str], author: discord.Member | discord.User) -> None:
        super().__init__(timeout=86400)  # Active for 24 hours
        self.question = question
        self.options = options
        self.author = author
        # In-memory votes: user_id -> option_index
        self.votes: dict[int, int] = {}

        # Add vote buttons
        for idx, opt in enumerate(options):
            self.add_item(PollButton(idx, f"{idx + 1}. {opt}"))

    def build_poll_container(self) -> KyroContainer:
        """Construct the live updated Components V2 poll card."""
        total_votes = len(self.votes)

        # Count votes per option
        counts = [0] * len(self.options)
        for opt_idx in self.votes.values():
            if 0 <= opt_idx < len(counts):
                counts[opt_idx] += 1

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Community Poll: {self.question}**\n"
                f"> Click a button below to cast or change your vote."
            )
        )
        container.add_separator(divider=True)

        # Build options with percentage bars
        option_lines = []
        for idx, (opt, count) in enumerate(zip(self.options, counts)):
            pct = (count / total_votes * 100) if total_votes > 0 else 0.0
            bar = render_progress_bar(pct, length=10)
            option_lines.append(
                f"**{idx + 1}. {opt}**\n"
                f"`[{bar}]` **{pct:.1f}%** ({count} vote{'s' if count != 1 else ''})"
            )

        container.add_text("\n\n".join(option_lines))
        container.add_separator(divider=True)
        container.add_text(
            f"**Total Votes:** `{total_votes}`\n"
            f"-# **Created by {self.author.display_name}** | Active for 24 hours"
        )
        return container


class PollCog(commands.Cog, name="Games-Poll"):
    """Community voting and live interactive polling suite."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.command(
        name="poll",
        aliases=["vote", "survey"],
        description="Create an interactive live poll with real-time percentage progress bars.",
    )
    @commands.guild_only()
    async def poll(self, ctx: CustomContext, question: str, *options: str) -> None:
        """Launch an interactive poll card."""
        clean_question = question.strip()
        if not clean_question:
            await ctx.send_error(f"Please provide a question. Usage: `{ctx.clean_prefix}poll \"Question\" \"Option 1\" \"Option 2\"`")
            return

        opts = [o.strip() for o in options if o.strip()]
        if not opts:
            # Default to Yes and No
            opts = ["Yes", "No"]
        elif len(opts) < 2:
            await ctx.send_error("A poll requires at least 2 options.")
            return
        elif len(opts) > 5:
            await ctx.send_error("A poll supports a maximum of 5 options.")
            return

        view = PollView(clean_question, opts, ctx.author)
        container = view.build_poll_container()

        # Delete command invocation if possible to keep chat clean
        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        await send_container_response(ctx.channel, container, view=view)


async def setup(bot: KyroBot) -> None:
    """Load the Poll cog into KyroBot."""
    await bot.add_cog(PollCog(bot))
