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
    category: str = "Moderation"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    async def _can_run_command(
        self, cmd: commands.Command, ctx: CustomContext, is_dev: bool = False, is_server_owner: bool = False
    ) -> bool:
        """Check if the command should be visible in the help menu."""
        if cmd.hidden:
            return False

        # Developer check - owner/developer only
        if getattr(cmd.cog, "category", "") == "Developer" and not is_dev:
            return False

        return True

    async def _get_visible_categories(self, ctx: CustomContext) -> dict[str, list[commands.Command]]:
        """Group commands that the current user has permission to execute."""
        categories: dict[str, list[commands.Command]] = {}
        is_dev = self.bot.perm_mgr.is_developer_sync(ctx.author.id)
        is_server_owner = bool(ctx.guild and ctx.author.id == ctx.guild.owner_id)

        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() in ["errorhandler"]:
                continue

            category_name = getattr(cog, "category", cog_name)
            # Remove Developer module completely - owner only, never displayed in public help
            if category_name.lower() == "developer":
                continue

            # Merge any legacy General / Utility commands directly into Moderation
            if category_name.lower() in ("general", "utility"):
                category_name = "Moderation"

            if category_name not in categories:
                categories[category_name] = []

            for cmd in cog.get_commands():
                if cmd.hidden:
                    continue

                if isinstance(cmd, commands.Group) and cmd.commands:
                    has_sub = False
                    for sub in sorted(cmd.commands, key=lambda s: s.name):
                        if not sub.hidden and await self._can_run_command(sub, ctx, is_dev=is_dev, is_server_owner=is_server_owner):
                            if sub not in categories[category_name]:
                                categories[category_name].append(sub)
                                has_sub = True
                    if not has_sub or getattr(cmd, "fallback", None) or getattr(cmd, "invoke_without_command", False):
                        if await self._can_run_command(cmd, ctx, is_dev=is_dev, is_server_owner=is_server_owner):
                            if cmd not in categories[category_name]:
                                categories[category_name].append(cmd)
                else:
                    if await self._can_run_command(cmd, ctx, is_dev=is_dev, is_server_owner=is_server_owner):
                        if cmd not in categories[category_name]:
                            categories[category_name].append(cmd)

        return {k: v for k, v in categories.items() if v}

    def _get_category_emoji(self, cat_name: str) -> str:
        """Resolve custom application emoji for category header from assets/emoji and assets/emoji2."""
        e_reg = self.bot.custom_emojis
        mapping = {
            "Music": e_reg.get("music", e_reg.get("icon_music", e_reg.get("Music_Playing", ""))),
            "Ticket": e_reg.get("icon_ticket", e_reg.get("ticket_support", e_reg.get("ticket", ""))),
            "Welcomer": e_reg.get("icons_join", e_reg.get("icon_join", "")),
            "Moderation": e_reg.get("icon_moderation", e_reg.get("icon_mod", e_reg.get("icons_staff", ""))),
            "Premium": e_reg.get("verified_premium", e_reg.get("icon_premium", "")),
            "Security": e_reg.get("icons_guardian", e_reg.get("icons_ban", "")),
            "Audit Logs": e_reg.get("icons_podcast", e_reg.get("icon_logging", "")),
            "Games": e_reg.get("icons_magicwand", e_reg.get("icons_tada", e_reg.get("icon_gift", ""))),
        }
        return mapping.get(cat_name, e_reg.get("icon_moderation", ""))

    def _get_category_select_emoji(self, cat_name: str) -> dict[str, Any] | None:
        """Resolve emoji dict for Select Menu options."""
        e_reg = self.bot.custom_emojis
        mapping = {
            "Music": "music",
            "Ticket": "icon_ticket",
            "Welcomer": "icons_join",
            "Moderation": "icon_moderation",
            "Premium": "verified_premium",
            "Security": "icons_guardian",
            "Audit Logs": "icons_podcast",
            "Games": "icons_magicwand",
        }
        emoji_name = mapping.get(cat_name, "icon_moderation")
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
                f"**Hey, I'm {Config.BOT_NAME}**\n"
                f"> All-in-one Discord ecosystem built for lossless audio streaming, support tickets, and visual server utilities."
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

        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {author.display_name}**")
        container.add_separator(divider=True)

        buttons = []
        if Config.INVITE_URL:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": "Invite Kyro",
                "url": Config.INVITE_URL,
            })
        if Config.SUPPORT_URL:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": "Support Server",
                "url": Config.SUPPORT_URL,
            })
        if buttons:
            container.add_action_row(buttons)

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

        formatted_cmds = ", ".join([f"`{cmd.qualified_name}`" for cmd in sorted(commands_list, key=lambda c: c.qualified_name)])
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

        container.add_separator(divider=True)
        container.add_text(f"-# **Requested by {ctx.author.display_name}**")
        container.add_separator(divider=True)

        buttons = []
        if Config.INVITE_URL:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": "Invite Kyro",
                "url": Config.INVITE_URL,
            })
        if Config.SUPPORT_URL:
            buttons.append({
                "type": 2,
                "style": 5,
                "label": "Support Server",
                "url": Config.SUPPORT_URL,
            })
        if buttons:
            container.add_action_row(buttons)

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
                cat = getattr(target_cmd.cog, "category", "Moderation")
                if cat.lower() in ("general", "utility"):
                    cat = "Moderation"
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
                        c = KyroContainer()
                        c.add_section(
                            content=(
                                "**Kyro Prime Trial**\n"
                                "> Type `?buy` and select **Claim 3-Day Free Trial** to activate Pro for this server."
                            )
                        )
                        await send_container_response(interaction, c, ephemeral=True)

                elif action == "action_buy":
                    c = KyroContainer()
                    c.add_section(
                        content=(
                            "**Kyro Checkout**\n"
                            "> Type `?buy` to open the interactive Checkout Console and select a plan."
                        )
                    )
                    await send_container_response(interaction, c, ephemeral=True)

            except asyncio.TimeoutError:
                break


async def setup(bot: KyroBot) -> None:
    await bot.add_cog(Help(bot))
