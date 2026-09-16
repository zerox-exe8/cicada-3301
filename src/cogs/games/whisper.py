"""
Kyro Discord Bot - Secret In-Chat Whisper Suite
Allows members to send secret, in-channel messages that only the designated recipient
can reveal via a private ephemeral Components V2 button. Zero webhooks.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class WhisperRevealView(discord.ui.View):
    """Interactive button allowing only the recipient or author to reveal the whisper."""

    def __init__(self, cog: WhisperCog, token: str, recipient_id: int, author_id: int) -> None:
        super().__init__(timeout=86400)  # Active for 24 hours
        self.cog = cog
        self.token = token
        self.recipient_id = recipient_id
        self.author_id = author_id

    @discord.ui.button(
        label="Reveal Whisper",
        style=discord.ButtonStyle.secondary,
        custom_id="whisper_reveal_btn",
    )
    async def reveal_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        user_id = interaction.user.id
        if user_id not in (self.recipient_id, self.author_id):
            await interaction.response.send_message(
                "This secret whisper was not sent to you.",
                ephemeral=True,
            )
            return

        secret_content = self.cog.get_whisper(self.token)
        if not secret_content:
            await interaction.response.send_message(
                "This whisper has expired or is no longer available.",
                ephemeral=True,
            )
            return

        role_label = "Recipient" if user_id == self.recipient_id else "Sender"
        await interaction.response.send_message(
            f"**Secret Whisper ({role_label})**\n> {secret_content}",
            ephemeral=True,
        )


class WhisperCog(commands.Cog, name="Games-Whisper"):
    """Secret in-chat whisper communication suite."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # In-memory storage: token -> (secret_text, timestamp)
        self._whisper_store: dict[str, tuple[str, float]] = {}

    def store_whisper(self, content: str) -> str:
        """Store secret text and prune expired whispers."""
        now = time.time()
        # Clean items older than 24 hours
        expired = [k for k, (_, ts) in self._whisper_store.items() if now - ts > 86400]
        for k in expired:
            self._whisper_store.pop(k, None)

        token = str(uuid.uuid4())[:8]
        self._whisper_store[token] = (content, now)
        return token

    def get_whisper(self, token: str) -> Optional[str]:
        """Fetch whisper text by token."""
        item = self._whisper_store.get(token)
        return item[0] if item else None

    @commands.hybrid_command(
        name="whisper",
        aliases=["secret", "w"],
        description="Send a secret whisper to another user in the channel that only they can reveal.",
    )
    @commands.guild_only()
    @app_commands.describe(
        member="The server member to send the secret whisper to",
        message="The private message content",
    )
    async def whisper(self, ctx: CustomContext, member: discord.Member, *, message: str) -> None:
        """Dispatch a secret in-channel whisper card."""
        if member.id == ctx.author.id:
            await ctx.send_error("You cannot send a secret whisper to yourself.")
            return

        if member.bot:
            await ctx.send_error("You cannot send a secret whisper to a bot.")
            return

        clean_message = message.strip()
        if not clean_message:
            await ctx.send_error("Whisper message cannot be empty.")
            return

        # Delete the trigger message if invoked via prefix so nobody sees the text
        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        # Save secret in memory
        token = self.store_whisper(clean_message)

        # Build public card
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Secret In-Chat Whisper**\n"
                f"> A private whisper has been delivered for {member.mention}.\n"
                f"> Only {member.mention} and the sender can click below to reveal its contents."
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"-# **Sent by {ctx.author.display_name}** | Expires in 24 hours")

        view = WhisperRevealView(self, token, member.id, ctx.author.id)

        # Handle interaction response vs prefix response
        if ctx.interaction:
            # Ephemeral acknowledgment for the author in slash command
            await ctx.interaction.response.send_message("Whisper dispatched privately.", ephemeral=True)
            await send_container_response(ctx.channel, container, view=view)
        else:
            await send_container_response(ctx.channel, container, view=view)


async def setup(bot: KyroBot) -> None:
    """Load the Whisper cog into KyroBot."""
    await bot.add_cog(WhisperCog(bot))
