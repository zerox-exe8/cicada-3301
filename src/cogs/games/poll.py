"""
Kyro Discord Bot - Interactive Live Poll & Community Voting Suite
Presents dynamic, real-time interactive poll cards using Discord Components V2.
Features interactive builder modals, smart multi-format CLI parsing,
Unicode percentage progress bars, single-click vote toggling, and zero raw text.
"""

from __future__ import annotations

import re
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


def parse_poll_input(raw: str) -> tuple[Optional[str], list[str]]:
    """Smart NLP & regex parser supporting quotes, pipes, commas, and question defaults."""
    text = raw.strip()
    if not text:
        return None, []

    # 1. Quoted options (handles standard ", ', and mobile smart quotes “, ”, ‘, ’)
    quoted = re.findall(r'["“](.+?)["”]|[\'‘](.+?)[\'’]', text)
    if quoted:
        items = [q[0] or q[1] for q in quoted if (q[0] or q[1]).strip()]
        if len(items) >= 2:
            question = items[0].strip()
            options = [it.strip() for it in items[1:] if it.strip()]
            return question, options

    # 2. Pipe separation: Question | Option 1 | Option 2 ...
    if "|" in text:
        parts = [p.strip() for p in text.split("|") if p.strip()]
        if len(parts) >= 2:
            return parts[0], parts[1:]

    # 3. Question mark followed by comma-separated options:
    # e.g. "Best food? Pizza, Burger, Pasta"
    if "?" in text:
        q_part, opts_part = text.split("?", 1)
        question = q_part.strip() + "?"
        if opts_part.strip():
            options = [o.strip() for o in opts_part.split(",") if o.strip()]
            return question, options
        else:
            # Just a question with no options -> default to Yes / No
            return question, ["Yes", "No"]

    # 4. Comma separation without question mark:
    # e.g. "Valorant or GTA, Valorant, GTA"
    if "," in text:
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if len(parts) >= 3:
            return parts[0], parts[1:]

    # 5. Single sentence/question without '?' or commas -> defaults to Yes / No
    return text, ["Yes", "No"]


class CreatePollModal(discord.ui.Modal, title="Create Community Poll"):
    """Interactive visual builder modal for creating community polls."""

    def __init__(self) -> None:
        super().__init__(timeout=300)
        self.question_input = discord.ui.TextInput(
            label="Poll Question",
            placeholder="e.g. Which map or game should we play?",
            style=discord.TextStyle.short,
            max_length=200,
            required=True,
        )
        self.opt1 = discord.ui.TextInput(
            label="Option 1",
            placeholder="First option (e.g. Valorant)",
            style=discord.TextStyle.short,
            max_length=80,
            required=True,
        )
        self.opt2 = discord.ui.TextInput(
            label="Option 2",
            placeholder="Second option (e.g. GTA V)",
            style=discord.TextStyle.short,
            max_length=80,
            required=True,
        )
        self.opt3 = discord.ui.TextInput(
            label="Option 3 (Optional)",
            placeholder="Third option (leave blank if not needed)",
            style=discord.TextStyle.short,
            max_length=80,
            required=False,
        )
        self.opt4 = discord.ui.TextInput(
            label="Option 4 (Optional)",
            placeholder="Fourth option (leave blank if not needed)",
            style=discord.TextStyle.short,
            max_length=80,
            required=False,
        )
        self.add_item(self.question_input)
        self.add_item(self.opt1)
        self.add_item(self.opt2)
        self.add_item(self.opt3)
        self.add_item(self.opt4)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        q = self.question_input.value.strip()
        opts = [self.opt1.value.strip(), self.opt2.value.strip()]
        if self.opt3.value and self.opt3.value.strip():
            opts.append(self.opt3.value.strip())
        if self.opt4.value and self.opt4.value.strip():
            opts.append(self.opt4.value.strip())

        opts = [o for o in opts if o]
        if len(opts) < 2:
            c = KyroContainer(accent_color=None)
            c.add_text("A poll requires at least 2 valid options.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        # Delete trigger console card if present
        if interaction.message:
            try:
                await interaction.message.delete()
            except (discord.HTTPException, AttributeError):
                pass

        view = PollView(q, opts, interaction.user)
        container = view.build_poll_container()

        # Publish poll card via Components V2
        await send_container_response(interaction, container, view=view)


class PollConsoleView(discord.ui.View):
    """Launchpad view offering one-click visual poll creation."""

    def __init__(self, author_id: int) -> None:
        super().__init__(timeout=180)
        self.author_id = author_id

    @discord.ui.button(label="Create Poll", style=discord.ButtonStyle.primary, custom_id="open_poll_builder")
    async def open_builder(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        if interaction.user.id != self.author_id:
            c = KyroContainer(accent_color=None)
            c.add_text("Only the user who initiated the poll console can launch the builder.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        modal = CreatePollModal()
        await interaction.response.send_modal(modal)


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
            # Clicked active option -> remove vote
            view.votes.pop(user_id, None)
        else:
            # Cast / switch vote
            view.votes[user_id] = self.option_index

        # Re-render live container card
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

        counts = [0] * len(self.options)
        for opt_idx in self.votes.values():
            if 0 <= opt_idx < len(counts):
                counts[opt_idx] += 1

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Community Poll: {self.question}**\n"
                "> Cast your vote using the buttons below. You can change or remove your vote anytime."
            )
        )
        container.add_separator(divider=True)

        # Build options with percentage bars
        option_lines = []
        for idx, (opt, count) in enumerate(zip(self.options, counts)):
            pct = (count / total_votes * 100) if total_votes > 0 else 0.0
            bar = render_progress_bar(pct, length=12)
            option_lines.append(
                f"**{idx + 1}. {opt}**\n"
                f"> `[{bar}]` **{pct:.1f}%** ({count} vote{'s' if count != 1 else ''})"
            )

        container.add_text("\n\n".join(option_lines))
        container.add_separator(divider=True)
        container.add_text(
            f"**Total Votes:** `{total_votes}`\n"
            f"-# **Created by {self.author.display_name}** | Real-time live updates"
        )
        return container


class PollCog(commands.Cog, name="Games-Poll"):
    """Community voting and live interactive polling suite."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    @commands.hybrid_command(
        name="poll",
        aliases=["vote", "survey"],
        description="Create an interactive live poll with real-time percentage progress bars.",
    )
    @commands.guild_only()
    @app_commands.describe(
        prompt="Poll question or Question? Opt1, Opt2 (leave blank to open visual builder modal)",
    )
    async def poll(self, ctx: CustomContext, *, prompt: Optional[str] = None) -> None:
        """Launch an interactive poll card or open the visual builder."""
        if not prompt or not prompt.strip():
            # If invoked as slash command without prompt, open modal directly!
            if ctx.interaction:
                modal = CreatePollModal()
                await ctx.interaction.response.send_modal(modal)
                return

            # Prefix command: display the Poll Studio launchpad card with button
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**{Config.BOT_NAME} Poll Studio**\n"
                    "> Create interactive community polls with live percentage bars and single-click voting."
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"**How to Create:**\n"
                f"• **Visual Builder:** Click the **Create Poll** button below to open the modal.\n"
                f"• **Inline Options:** `{ctx.clean_prefix}poll Question? Option 1, Option 2, Option 3`\n"
                f"• **Quick Yes/No:** `{ctx.clean_prefix}poll Should we host a tournament?`\n"
                f"• **Pipe Syntax:** `{ctx.clean_prefix}poll Match Winner | Team A | Team B`"
            )
            container.add_separator(divider=True)
            container.add_text("-# Click 'Create Poll' below to launch the interactive modal")

            view = PollConsoleView(ctx.author.id)
            await send_container_response(ctx, container, view=view)
            return

        # Parse inline arguments with smart multi-format parser
        question, options = parse_poll_input(prompt)

        if not question:
            await ctx.send_error("Could not determine the poll question. Please try using the visual builder.")
            return

        if len(options) < 2:
            await ctx.send_error(
                "A poll requires at least 2 options.\n"
                f"• Example: `{ctx.clean_prefix}poll Best movie? Interstellar, Inception`\n"
                f"• Or leave options blank for auto Yes/No: `{ctx.clean_prefix}poll Game khelna hai?`"
            )
            return

        if len(options) > 5:
            await ctx.send_error(
                "A poll supports a maximum of 5 options for optimal button layout."
            )
            return

        view = PollView(question, options, ctx.author)
        container = view.build_poll_container()

        # Delete user message if prefix was used
        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        await send_container_response(ctx, container, view=view)


async def setup(bot: KyroBot) -> None:
    """Load the Poll cog into KyroBot."""
    await bot.add_cog(PollCog(bot))
