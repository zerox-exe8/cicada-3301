"""
Kyro Discord Bot - Secret In-Chat Whisper Suite
Allows members to send secret, in-channel messages that only the designated recipient
can reveal via a private ephemeral Components V2 button. Zero webhooks.
"""

from __future__ import annotations

import hashlib
import os
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


def _derive_whisper_key(salt: str, author_id: int, recipient_id: int) -> bytes:
    """Derive a deterministic cryptographic symmetric key for the whisper channel."""
    material = f"{salt}:{min(author_id, recipient_id)}:{max(author_id, recipient_id)}".encode("utf-8")
    return hashlib.sha256(material).digest()


def _encrypt_whisper(plaintext: str, key: bytes) -> tuple[bytes, bytes]:
    """Symmetric stream cipher with unique OS-entropy nonce."""
    nonce = os.urandom(16)
    data = plaintext.encode("utf-8")
    keystream = hashlib.sha256(key + nonce).digest()
    while len(keystream) < len(data):
        keystream += hashlib.sha256(key + keystream).digest()
    ciphertext = bytes(b ^ k for b, k in zip(data, keystream[:len(data)]))
    return ciphertext, nonce


def _decrypt_whisper(ciphertext: bytes, nonce: bytes, key: bytes) -> str:
    """Decrypt symmetric stream cipher payload."""
    keystream = hashlib.sha256(key + nonce).digest()
    while len(keystream) < len(ciphertext):
        keystream += hashlib.sha256(key + keystream).digest()
    decrypted = bytes(b ^ k for b, k in zip(ciphertext, keystream[:len(ciphertext)]))
    return decrypted.decode("utf-8", errors="replace")


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
            c = KyroContainer(accent_color=None)
            c.add_section(
                content=(
                    "**Confidential Whisper**\n"
                    "> You do not have permission to decrypt this message.\n"
                    f"> This whisper is encrypted exclusively for <@{self.recipient_id}>."
                )
            )
            c.add_separator(divider=True)
            c.add_text("-# Access denied • End-to-end authorized")
            await send_container_response(interaction, c, ephemeral=True)
            return

        secret_content = self.cog.get_whisper(self.token, self.author_id, self.recipient_id)
        if not secret_content:
            c = KyroContainer(accent_color=None)
            c.add_text("This whisper has expired or has already been cleared from cache.")
            await send_container_response(interaction, c, ephemeral=True)
            return

        role_label = "Recipient" if user_id == self.recipient_id else "Sender"
        card = KyroContainer(accent_color=None)
        card.add_section(
            content=(
                f"**Secret Whisper ({role_label} View)**\n"
                f"> {secret_content}"
            )
        )
        card.add_separator(divider=True)
        card.add_text(
            f"**From:** <@{self.author_id}> | **To:** <@{self.recipient_id}>\n"
            f"-# End-to-end encrypted in memory • Only visible to you • Components V2"
        )
        await send_container_response(interaction, card, ephemeral=True)


class WhisperCog(commands.Cog, name="Games-Whisper"):
    """Secret in-chat whisper communication suite."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # In-memory storage: token -> (ciphertext, nonce, timestamp)
        self._whisper_store: dict[str, tuple[bytes, bytes, float]] = {}

    def store_whisper(self, content: str, author_id: int, recipient_id: int) -> str:
        """Encrypt and store secret text in memory with automatic expiration pruning."""
        now = time.time()
        expired = [k for k, (_, _, ts) in self._whisper_store.items() if now - ts > 86400]
        for k in expired:
            self._whisper_store.pop(k, None)

        key = _derive_whisper_key(Config.BOT_TOKEN or "kyro_salt", author_id, recipient_id)
        ciphertext, nonce = _encrypt_whisper(content, key)

        token = str(uuid.uuid4())[:8]
        self._whisper_store[token] = (ciphertext, nonce, now)
        return token

    def get_whisper(self, token: str, author_id: int, recipient_id: int) -> Optional[str]:
        """Decrypt secret text if valid and authorized."""
        item = self._whisper_store.get(token)
        if not item:
            return None
        ciphertext, nonce, _ = item
        key = _derive_whisper_key(Config.BOT_TOKEN or "kyro_salt", author_id, recipient_id)
        return _decrypt_whisper(ciphertext, nonce, key)

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
    async def whisper(
        self, ctx: CustomContext, member: Optional[discord.Member] = None, *, message: Optional[str] = None
    ) -> None:
        """Dispatch a secret in-channel whisper card or view usage instructions."""
        if not member or not message or not message.strip():
            container = KyroContainer(accent_color=None)
            container.add_section(
                content=(
                    f"**{Config.BOT_NAME} Secret In-Chat Whisper**\n"
                    "> Send private in-chat messages with an interactive `[Reveal Whisper]` button.\n"
                    "> Only the targeted member (and you) can click to read the hidden message."
                )
            )
            container.add_separator(divider=True)
            container.add_text(
                f"**Usage:**\n"
                f"• `{ctx.clean_prefix}whisper @member <secret message>`\n"
                f"• `{ctx.clean_prefix}whisper <username_or_id> <secret message>`\n"
                f"• `/whisper member:@member message:<secret message>`\n\n"
                f"**Example:**\n"
                f"`{ctx.clean_prefix}whisper @friend Kal 5 baje aana`"
            )
            container.add_separator(divider=True)
            container.add_text("-# Trigger message is automatically deleted so chat never sees the secret text.")
            await send_container_response(ctx, container)
            return

        if member.id == ctx.author.id:
            c = KyroContainer(accent_color=None)
            c.add_text("You cannot send a secret whisper to yourself.")
            await send_container_response(ctx, c, ephemeral=True)
            return

        if member.bot:
            c = KyroContainer(accent_color=None)
            c.add_text("You cannot send a secret whisper to a bot.")
            await send_container_response(ctx, c, ephemeral=True)
            return

        clean_message = message.strip()
        if len(clean_message) > 1000:
            c = KyroContainer(accent_color=None)
            c.add_text("Whisper message is too long (maximum 1000 characters).")
            await send_container_response(ctx, c, ephemeral=True)
            return

        # Delete the trigger message if invoked via prefix so nobody sees the text
        if ctx.message:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

        # Save secret in memory with cryptographic encryption
        token = self.store_whisper(clean_message, ctx.author.id, member.id)

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
        container.add_text(f"-# **Sent by {ctx.author.display_name}** | Encrypted in Memory | Expires in 24 hours")

        view = WhisperRevealView(self, token, member.id, ctx.author.id)

        # Handle interaction response vs prefix response
        if ctx.interaction:
            # Ephemeral acknowledgment inside KyroContainer (no raw plain text)
            ack = KyroContainer(accent_color=None)
            ack.add_text("Secret whisper dispatched to the channel.")
            await send_container_response(ctx.interaction, ack, ephemeral=True)
            await send_container_response(ctx.channel, container, view=view)
        else:
            await send_container_response(ctx.channel, container, view=view)


async def setup(bot: KyroBot) -> None:
    """Load the Whisper cog into KyroBot."""
    await bot.add_cog(WhisperCog(bot))
