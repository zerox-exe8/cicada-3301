"""
Kyro Discord Bot - Translator Cog
Multilingual translation with country flag reactions, slash commands, and context menu support.
"""

from __future__ import annotations

import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.core.bot import KyroBot
from src.managers.translator_manager import FLAG_TO_LANG, LANGUAGE_NAMES
from src.utils.containers import KyroContainer

logger = logging.getLogger("Kyro.Cogs.Translator")


class ShareTranslationView(discord.ui.View):
    """View providing a button to broadcast an ephemeral translation to the channel."""

    def __init__(self, original_author: discord.User | discord.Member, target_lang_name: str, translated_text: str) -> None:
        super().__init__(timeout=180)
        self.original_author = original_author
        self.target_lang_name = target_lang_name
        self.translated_text = translated_text

    @discord.ui.button(label="Share to Channel", style=discord.ButtonStyle.secondary, emoji="📢")
    async def share_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Translation ({self.target_lang_name})\n"
                f"> {self.translated_text}"
            )
        )
        container.add_separator(divider=True)
        container.add_field("Original Author", self.original_author.mention, inline=True)
        container.add_field("Shared By", interaction.user.mention, inline=True)

        await interaction.channel.send(embed=container.to_embed())
        button.disabled = True
        button.label = "Shared"
        await interaction.response.edit_message(view=self)


class Translator(commands.Cog):
    """Multilingual translation suite supporting flag reactions and on-demand commands."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        # Context Menu Command registration
        self.ctx_menu = app_commands.ContextMenu(
            name="Translate Message",
            callback=self._context_menu_translate,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    # ─── REACTION LISTENER ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """Translate message when a country flag reaction is attached."""
        # 1. Ignore bot reactions or reactions outside guilds
        if not payload.guild_id or (self.bot.user and payload.user_id == self.bot.user.id):
            return

        emoji_str = str(payload.emoji.name)
        target_lang = FLAG_TO_LANG.get(emoji_str)
        if not target_lang:
            return

        # 2. Check guild & channel permissions
        if not self.bot.translator_mgr.is_channel_enabled(payload.guild_id, payload.channel_id):
            return

        # 3. Check reaction debounce
        if self.bot.translator_mgr.is_debounce_active(payload.message_id, payload.user_id, target_lang):
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        channel = guild.get_channel(payload.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel)):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden):
            return

        raw_text = message.clean_content.strip()
        if not raw_text:
            return

        user = guild.get_member(payload.user_id) or await self.bot.fetch_user(payload.user_id)
        if not user:
            return

        # 4. Perform translation
        translated_text, detected_lang = await self.bot.translator_mgr.translate(raw_text, target_lang)
        if not translated_text or translated_text.lower() == raw_text.lower():
            return

        target_name = LANGUAGE_NAMES.get(target_lang, target_lang.upper())
        detected_name = LANGUAGE_NAMES.get(detected_lang, detected_lang.upper())

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Translation • {target_name}\n"
                f"> {translated_text}"
            )
        )
        container.add_separator(divider=True)
        container.add_field("Original Language", detected_name, inline=True)
        container.add_field("Original Author", message.author.mention, inline=True)

        settings = self.bot.translator_mgr.get_settings(payload.guild_id)
        mode = settings.get("target_mode", "ephemeral")

        if mode == "public":
            await channel.send(embed=container.to_embed(), reference=message, mention_author=False)
        else:
            view = ShareTranslationView(message.author, target_name, translated_text)
            try:
                # Deliver privately to the reacting member via DM
                await user.send(
                    content=f"**Translation for message in {channel.mention}:**",
                    embed=container.to_embed(),
                    view=view,
                )
            except discord.Forbidden:
                # If DMs are closed, fall back to channel reply without pinging
                await channel.send(embed=container.to_embed(), reference=message, mention_author=False)

    # ─── CONTEXT MENU COMMAND ────────────────────────────────────────────────

    async def _context_menu_translate(self, interaction: discord.Interaction, message: discord.Message) -> None:
        """Right-click context menu: Translate message to English."""
        await interaction.response.defer(ephemeral=True)

        text = message.clean_content.strip()
        if not text:
            await interaction.followup.send("This message contains no readable text to translate.", ephemeral=True)
            return

        translated_text, detected_lang = await self.bot.translator_mgr.translate(text, "en")
        detected_name = LANGUAGE_NAMES.get(detected_lang, detected_lang.upper())

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### English Translation\n"
                f"> {translated_text}"
            )
        )
        container.add_separator(divider=True)
        container.add_field("Detected Language", detected_name, inline=True)
        container.add_field("Author", message.author.mention, inline=True)

        view = ShareTranslationView(message.author, "English", translated_text)
        await interaction.followup.send(embed=container.to_embed(), view=view, ephemeral=True)

    # ─── SLASH COMMANDS ───────────────────────────────────────────────────────

    @app_commands.command(name="translate", description="Translate any text into your chosen language")
    @app_commands.describe(
        text="The text or sentence you want to translate",
        language="Target language to translate into",
    )
    @app_commands.choices(
        language=[
            app_commands.Choice(name="English", value="en"),
            app_commands.Choice(name="Hindi", value="hi"),
            app_commands.Choice(name="Spanish", value="es"),
            app_commands.Choice(name="French", value="fr"),
            app_commands.Choice(name="German", value="de"),
            app_commands.Choice(name="Japanese", value="ja"),
            app_commands.Choice(name="Russian", value="ru"),
            app_commands.Choice(name="Chinese", value="zh-CN"),
            app_commands.Choice(name="Arabic", value="ar"),
            app_commands.Choice(name="Portuguese", value="pt"),
            app_commands.Choice(name="Korean", value="ko"),
        ]
    )
    async def translate_command(
        self,
        interaction: discord.Interaction,
        text: str,
        language: app_commands.Choice[str],
    ) -> None:
        """Translate text with rich KyroContainer card."""
        await interaction.response.defer()

        target_code = language.value
        target_name = language.name

        translated_text, detected_lang = await self.bot.translator_mgr.translate(text, target_code)
        detected_name = LANGUAGE_NAMES.get(detected_lang, detected_lang.upper())

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Translation • {target_name}\n"
                f"> {translated_text}"
            )
        )
        container.add_separator(divider=True)
        container.add_field("Original Language", detected_name, inline=True)
        container.add_field("Requested By", interaction.user.mention, inline=True)

        await interaction.followup.send(embed=container.to_embed())

    @app_commands.command(name="translator-settings", description="Configure server translation settings")
    @app_commands.describe(
        enabled="Enable or disable the entire translation suite",
        reactions="Enable or disable flag reaction translations",
        delivery="How reaction translations are sent (ephemeral DM or public channel reply)",
    )
    @app_commands.choices(
        delivery=[
            app_commands.Choice(name="Private DM / Ephemeral", value="ephemeral"),
            app_commands.Choice(name="Public Channel Reply", value="public"),
        ]
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def translator_settings(
        self,
        interaction: discord.Interaction,
        enabled: Optional[bool] = None,
        reactions: Optional[bool] = None,
        delivery: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        """Admin configuration for server translation."""
        if not interaction.guild:
            return

        deliv_val = delivery.value if delivery else None
        await self.bot.translator_mgr.update_settings(
            guild_id=interaction.guild.id,
            is_enabled=enabled,
            reaction_enabled=reactions,
            target_mode=deliv_val,
        )

        conf = self.bot.translator_mgr.get_settings(interaction.guild.id)
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"### Translator Settings Updated\n"
                f"> Configuration for **{interaction.guild.name}** has been updated."
            )
        )
        container.add_separator(divider=True)
        container.add_field("Translator Status", "Enabled" if conf["is_enabled"] else "Disabled", inline=True)
        container.add_field("Flag Reactions", "Active" if conf["reaction_enabled"] else "Inactive", inline=True)
        container.add_field("Delivery Mode", conf["target_mode"].capitalize(), inline=True)

        await interaction.response.send_message(embed=container.to_embed(), ephemeral=True)


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Translator(bot))
