"""
Kyro Discord Bot - Enterprise SaaS Help & Module Console
Dynamic permission-aware help menu powered by Discord Components V2 Container Cards.
Filters commands so users only see actions they have permission to execute.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
import discord
from discord.ext import commands

from src.core.config import Config
from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class Help(commands.Cog):
    """Enterprise SaaS Help & Module Console with dynamic permission filtering."""
    category: str = "General"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    async def _can_run_command(
        self, cmd: commands.Command, ctx: CustomContext, is_dev: bool = False, is_server_owner: bool = False
    ) -> bool:
        """Check if the context author has permission to run this command."""
        if cmd.hidden:
            return False

        # Developer check
        if getattr(cmd.cog, "category", "") == "Developer" and not is_dev:
            return False

        # If user is bot developer or server owner, allow visibility
        if is_dev or is_server_owner:
            return True

        # Check command permission checks
        try:
            can_run = await cmd.can_run(ctx)
            return can_run
        except Exception:
            return False

    async def _get_visible_categories(self, ctx: CustomContext) -> dict[str, list[commands.Command]]:
        """Group commands that the current user has permission to execute."""
        categories: dict[str, list[commands.Command]] = {}
        is_dev = self.bot.perm_mgr.is_developer_sync(ctx.author.id)
        is_server_owner = bool(ctx.guild and ctx.author.id == ctx.guild.owner_id)

        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() in ["errorhandler"]:
                continue

            category_name = getattr(cog, "category", cog_name)
            if category_name not in categories:
                categories[category_name] = []

            for cmd in cog.get_commands():
                if await self._can_run_command(cmd, ctx, is_dev=is_dev, is_server_owner=is_server_owner):
                    if cmd not in categories[category_name]:
                        categories[category_name].append(cmd)

        return {k: v for k, v in categories.items() if v}

    def _get_category_emoji(self, cat_name: str) -> str:
        """Resolve custom application emoji for category header from assets/emoji and assets/emoji2."""
        e_reg = self.bot.custom_emojis
        mapping = {
            "General": e_reg.get("icons_utility", e_reg.get("icons_generalinfo", "")),
            "Music": e_reg.get("Music_Playing", e_reg.get("music_music", e_reg.get("a_musical_notes", ""))),
            "Utility": e_reg.get("icons_magicwand", e_reg.get("icons_utility", "")),
            "Settings": e_reg.get("icons_settings", ""),
            "Admin": e_reg.get("icons_staff", e_reg.get("icon_mod", "")),
            "Security": e_reg.get("icons_guardian", e_reg.get("icons_ban", "")),
            "Audit Logs": e_reg.get("icons_podcast", e_reg.get("icon_logging", "")),
            "Premium": e_reg.get("verified_premium", e_reg.get("icon_premium", "")),
            "Developer": e_reg.get("icon_developer", e_reg.get("icon_dev", "")),
        }
        return mapping.get(cat_name, e_reg.get("icons_folder", ""))

    def _get_category_select_emoji(self, cat_name: str) -> dict[str, Any] | None:
        """Resolve emoji dict for Select Menu options."""
        e_reg = self.bot.custom_emojis
        mapping = {
            "General": "icons_utility",
            "Music": "music_music",
            "Utility": "icons_magicwand",
            "Settings": "icons_settings",
            "Admin": "icons_staff",
            "Security": "icons_guardian",
            "Audit Logs": "icons_podcast",
            "Premium": "verified_premium",
            "Developer": "icon_developer",
        }
        emoji_name = mapping.get(cat_name, "icons_folder")
        return e_reg.get_select_emoji(emoji_name, fallback_unicode=None)

    def _build_home_container(
        self,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
        custom_id_prefix: str,
        selected_val: str = "home",
    ) -> KyroContainer:
        """Construct the Signature Kyro SaaS Overview Card with Default Accent."""
        guild = ctx.guild
        author = ctx.author
        current_prefix = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        ws_ping = round(self.bot.latency * 1000) if self.bot.latency else 0
        total_commands = sum(len(cmds) for cmds in visible_categories.values())
        e_reg = self.bot.custom_emojis

        # Custom folder emojis (no unicode fallbacks)
        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "-"))

        # Default accent container (Dark Mode) - No avatar thumbnail
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Hey, I'm {Config.BOT_NAME.lower()}**\n"
                f"> A fast, secure Discord administration and utility system crafted to manage and protect your server smoothly."
            )
        )
        container.add_separator(divider=True)

        container.add_text(
            f"{dot} **Latency:** `{ws_ping}ms`\n"
            f"{dot} **Prefix:** `{current_prefix}` | **Slash:** `/`\n"
            f"{dot} **Available Commands:** `{total_commands}`"
        )
        container.add_separator(divider=True)

        # Dropdown Options (custom emojis only, clean labels)
        home_emoji_data = e_reg.get_select_emoji("icon_home", fallback_unicode=None)
        home_opt: dict[str, Any] = {
            "label": "Home",
            "value": "home",
            "default": selected_val == "home",
        }
        if home_emoji_data:
            home_opt["emoji"] = home_emoji_data

        options = [home_opt]

        for cat_name, cmds in visible_categories.items():
            cat_opt: dict[str, Any] = {
                "label": cat_name,
                "value": cat_name.lower(),
                "default": selected_val == cat_name.lower(),
            }
            cat_emoji_data = self._get_category_select_emoji(cat_name)
            if cat_emoji_data:
                cat_opt["emoji"] = cat_emoji_data
            options.append(cat_opt)

        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_category",
                "placeholder": "Select a module to view commands...",
                "options": options,
            }
        ])

        container.add_text(f"-# Requested by {author.display_name}")
        return container

    def _build_category_container(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        visible_categories: dict[str, list[commands.Command]],
        custom_id_prefix: str,
    ) -> KyroContainer:
        """Construct category command card with default accent and folder emojis."""
        current_prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        cat_icon = self._get_category_emoji(cat_name)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "-"))

        container = KyroContainer(accent_color=None)
        cat_icon_prefix = f"{cat_icon} " if cat_icon else ""
        container.add_section(
            content=(
                f"**{cat_icon_prefix}{cat_name} Commands**\n"
                f"> Listing `{len(commands_list)}` accessible command(s) for your role in this server."
            )
        )
        container.add_separator(divider=True)

        formatted_cmds = ", ".join([f"`{cmd.name}`" for cmd in sorted(commands_list, key=lambda c: c.name)])
        container.add_text(formatted_cmds)
        container.add_separator(divider=True)

        # Dropdown options (custom emojis only, clean labels)
        home_emoji_data = e_reg.get_select_emoji("icon_home", fallback_unicode=None)
        home_opt: dict[str, Any] = {
            "label": "Home",
            "value": "home",
            "default": False,
        }
        if home_emoji_data:
            home_opt["emoji"] = home_emoji_data

        options = [home_opt]

        for c_name, cmds in visible_categories.items():
            cat_opt: dict[str, Any] = {
                "label": c_name,
                "value": c_name.lower(),
                "default": c_name.lower() == cat_name.lower(),
            }
            cat_emoji_data = self._get_category_select_emoji(c_name)
            if cat_emoji_data:
                cat_opt["emoji"] = cat_emoji_data
            options.append(cat_opt)

        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_category",
                "placeholder": "Select a module to view commands...",
                "options": options,
            }
        ])

        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    @commands.hybrid_command(
        name="help",
        aliases=["commands", "modules", "h"],
        description="Display the Kyro command directory tailored to your permissions.",
    )
    async def help_command(self, ctx: CustomContext, *, command_or_module: str | None = None) -> None:
        """Interactive help menu filtered by user permissions."""
        visible_categories = await self._get_visible_categories(ctx)

        # 1. Direct command lookup
        if command_or_module:
            query = command_or_module.lower().strip()
            target_cmd = self.bot.get_command(query)
            if target_cmd and await self._can_run_command(target_cmd, ctx):
                current_prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
                cat = getattr(target_cmd.cog, "category", "General")
                cat_icon = self._get_category_emoji(cat)
                desc = target_cmd.description or target_cmd.help or "No detailed description available."
                aliases = ", ".join([f"`{a}`" for a in target_cmd.aliases]) if target_cmd.aliases else "`None`"
                usage = f"`{current_prefix}{target_cmd.qualified_name} {target_cmd.signature}`".strip()
                e_reg = self.bot.custom_emojis
                dot = e_reg.get("heart_dot", e_reg.get("icons_rightarrow", "-"))

                container = KyroContainer(accent_color=None)
                cat_icon_prefix = f"{cat_icon} " if cat_icon else ""
                container.add_section(
                    content=(
                        f"**{cat_icon_prefix}Command: `{target_cmd.name}`**\n"
                        f"> {desc}"
                    )
                )
                container.add_separator(divider=True)
                container.add_text(
                    f"{dot} **Usage:** `{usage}`\n"
                    f"{dot} **Aliases:** {aliases} | **Category:** `{cat}`"
                )
                container.add_separator(divider=True)
                container.add_text(f"-# Requested by {ctx.author.display_name}")
                await send_container_response(ctx, container)
                return

        # 2. Main Help Console
        custom_id_prefix = f"help_console:{ctx.author.id}:{ctx.guild.id if ctx.guild else 0}:{ctx.message.id if ctx.message else 0}"
        container = self._build_home_container(ctx, visible_categories, custom_id_prefix)
        await send_container_response(ctx, container)

        def check(interaction: discord.Interaction) -> bool:
            if not interaction.data:
                return False
            custom_id = interaction.data.get("custom_id", "")
            return (
                custom_id.startswith(f"{custom_id_prefix}:")
                and interaction.user.id == ctx.author.id
            )

        while True:
            try:
                interaction: discord.Interaction = await self.bot.wait_for(
                    "interaction", check=check, timeout=120.0
                )
                custom_id = interaction.data.get("custom_id", "")
                action = custom_id.split(":")[-1]

                # Select Menu Navigation
                if action == "select_category":
                    selected = interaction.data.get("values", ["home"])[0]
                    if selected == "home":
                        new_container = self._build_home_container(ctx, visible_categories, custom_id_prefix, "home")
                    else:
                        matched_cat = next((c for c in visible_categories.keys() if c.lower() == selected), None)
                        if matched_cat:
                            new_container = self._build_category_container(
                                ctx, matched_cat, visible_categories[matched_cat], visible_categories, custom_id_prefix
                            )
                        else:
                            new_container = self._build_home_container(ctx, visible_categories, custom_id_prefix, "home")

                    await edit_container_response(interaction, new_container)

                elif action == "action_trial":
                    buy_cog = self.bot.get_cog("PremiumPurchase")
                    if buy_cog:
                        await interaction.response.send_message(
                            "Type `?buy` and select **Claim 3-Day Free Trial** to activate Pro for this server.",
                            ephemeral=True,
                        )

                elif action == "action_buy":
                    await interaction.response.send_message(
                        "Type `?buy` to open the interactive Checkout Console and select a plan.",
                        ephemeral=True,
                    )

            except asyncio.TimeoutError:
                break


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Help(bot))
