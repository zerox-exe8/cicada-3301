"""
Cicada 3301 Discord Bot - Enterprise SaaS Help & Module Console
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
from src.utils.containers import CicadaContainer, send_container_response, edit_container_response

if TYPE_CHECKING:
    from src.core.bot import CicadaBot


class Help(commands.Cog):
    """Enterprise SaaS Help & Module Console with dynamic permission filtering."""
    category: str = "General"

    def __init__(self, bot: CicadaBot) -> None:
        self.bot = bot

    async def _can_run_command(self, cmd: commands.Command, ctx: CustomContext) -> bool:
        """Check if the context author has permission to run this command."""
        if cmd.hidden:
            return False

        # Developer check
        is_dev = await self.bot.perm_mgr.is_developer(ctx.author.id)
        if getattr(cmd.cog, "category", "") == "Developer" and not is_dev:
            return False

        # If user is bot developer or server owner, allow visibility
        if is_dev or (ctx.guild and ctx.author.id == ctx.guild.owner_id):
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

        for cog_name, cog in self.bot.cogs.items():
            if cog_name.lower() in ["errorhandler"]:
                continue

            category_name = getattr(cog, "category", cog_name)
            if category_name not in categories:
                categories[category_name] = []

            for cmd in cog.get_commands():
                if await self._can_run_command(cmd, ctx):
                    if cmd not in categories[category_name]:
                        categories[category_name].append(cmd)

        return {k: v for k, v in categories.items() if v}

    def _get_category_emoji(self, cat_name: str) -> str:
        """Resolve custom application emoji for category header."""
        e_reg = self.bot.custom_emojis
        mapping = {
            "General": e_reg.get("icons_utility", e_reg.get("icon_info", "")),
            "Security": e_reg.get("icons_ban", e_reg.get("icon_mod", "")),
            "Audit Logs": e_reg.get("icons_podcast", e_reg.get("icons_settings", "")),
            "Settings": e_reg.get("icons_settings", ""),
            "Premium": e_reg.get("icons_star", e_reg.get("icons_coin", "")),
            "Developer": e_reg.get("icon_developer", ""),
        }
        return mapping.get(cat_name, e_reg.get("icons_folder", ""))

    def _get_category_select_emoji(self, cat_name: str) -> dict[str, Any]:
        """Resolve emoji dict for Select Menu options."""
        e_reg = self.bot.custom_emojis
        mapping = {
            "General": "icons_utility",
            "Security": "icons_ban",
            "Audit Logs": "icons_podcast",
            "Settings": "icons_settings",
            "Premium": "icons_star",
            "Developer": "icon_developer",
        }
        emoji_name = mapping.get(cat_name, "icons_folder")
        return e_reg.get_select_emoji(emoji_name, fallback_unicode="📁")

    def _build_home_container(
        self,
        ctx: CustomContext,
        visible_categories: dict[str, list[commands.Command]],
        custom_id_prefix: str,
        selected_val: str = "home",
    ) -> CicadaContainer:
        """Construct the Signature Cicada 3301 SaaS Overview Card."""
        guild = ctx.guild
        author = ctx.author
        current_prefix = self.bot.guild_mgr.get_prefix(guild.id if guild else None)
        ws_ping = round(self.bot.latency * 1000) if self.bot.latency else 0
        total_commands = sum(len(cmds) for cmds in visible_categories.values())

        # Check Subscription Tier
        is_pro = self.bot.premium_mgr.is_guild_premium(guild.id) if guild else False
        status_text = "Cicada Pro Active • Enterprise Tier" if is_pro else "Cicada 3301 Infrastructure • 3-Day Trial Available"

        container = CicadaContainer(accent_color=None)
        container.add_text(
            f"### ◈ CICADA 3301 // AUTONOMOUS SECURITY PROTOCOL\n\n"
            f"> ⌁ High-assurance cryptographic protection, self-healing architecture, and low-latency audit logging.\n\n"
            f"```ansi\n"
            f"\u001b[1;32m[SYSTEM TIER]\u001b[0m       :: {status_text}\n"
            f"\u001b[1;36m[ACTIVE PREFIX]\u001b[0m     :: {current_prefix} | Slash (/)\n"
            f"\u001b[1;33m[ACCESS PRIVILEGES]\u001b[0m :: {total_commands} Authorized Command(s)\n"
            f"\u001b[1;35m[SOCKET TELEMETRY]\u001b[0m  :: {ws_ping} ms (0ms Memory Bus)\n"
            f"```\n"
            f"**◈ Core Subsystems:**\n"
            f"• `[ZERO-TRUST]` Anti-raid containment & self-healing channel rollback.\n"
            f"• `[AUDIT-LOGS]` 6 dedicated high-throughput event channels.\n"
            f"• `[DYNAMIC-VOICE]` Ephemeral voice hubs with interactive in-card controllers."
        )
        container.add_separator(divider=True)

        # Dropdown Options
        e_reg = self.bot.custom_emojis
        home_emoji_data = e_reg.get_select_emoji("icon_home", fallback_unicode="🏠")
        options = [
            {
                "label": "Overview Home",
                "value": "home",
                "description": "Return to main infrastructure overview",
                "emoji": home_emoji_data,
                "default": selected_val == "home",
            }
        ]

        for cat_name, cmds in visible_categories.items():
            options.append({
                "label": f"{cat_name} ({len(cmds)})",
                "value": cat_name.lower(),
                "description": f"View {len(cmds)} accessible {cat_name} command(s)",
                "emoji": self._get_category_select_emoji(cat_name),
                "default": selected_val == cat_name.lower(),
            })

        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_category",
                "placeholder": "Select an infrastructure module...",
                "options": options,
            }
        ])

        # If server is unactivated, provide 1-click Pro Actions
        if not is_pro:
            container.add_action_row([
                {
                    "type": 2,
                    "style": 3,  # Success Green
                    "label": "Claim 3-Day Free Trial",
                    "custom_id": f"{custom_id_prefix}:action_trial",
                },
                {
                    "type": 2,
                    "style": 1,  # Primary Blurple
                    "label": "Upgrade to Pro ($4.99 / ₹399)",
                    "custom_id": f"{custom_id_prefix}:action_buy",
                },
            ])

        container.add_text("-# Cicada 3301 Autonomous Enterprise OS • Select a module above to browse commands")
        return container

    def _build_category_container(
        self,
        ctx: CustomContext,
        cat_name: str,
        commands_list: list[commands.Command],
        visible_categories: dict[str, list[commands.Command]],
        custom_id_prefix: str,
    ) -> CicadaContainer:
        """Construct category command card with sleek typography and module select menu."""
        current_prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        cat_icon = self._get_category_emoji(cat_name)
        header_text = f"{cat_icon} **{cat_name} Module ({len(commands_list)} Commands)**".strip()

        container = CicadaContainer(accent_color=None)
        container.add_text(
            f"{header_text}\n"
            f"> Commands available for your role in this server.\n"
        )
        container.add_separator(divider=True)

        cmd_lines = []
        for cmd in sorted(commands_list, key=lambda c: c.name):
            desc = cmd.description or cmd.help or "No description provided."
            # Show subcommands if hybrid_group
            if isinstance(cmd, commands.Group):
                sub_names = [f"`{sub.name}`" for sub in cmd.commands if not sub.hidden]
                sub_str = f" • Subcommands: {', '.join(sub_names)}" if sub_names else ""
                cmd_lines.append(f"• **`{current_prefix}{cmd.name}`** — {desc}{sub_str}")
            else:
                cmd_lines.append(f"• **`{current_prefix}{cmd.name}`** — {desc}")

        container.add_text("\n".join(cmd_lines))
        container.add_separator(divider=True)

        # Dropdown options
        e_reg = self.bot.custom_emojis
        home_emoji_data = e_reg.get_select_emoji("icon_home", fallback_unicode="🏠")
        options = [
            {
                "label": "Overview Home",
                "value": "home",
                "description": "Return to main infrastructure overview",
                "emoji": home_emoji_data,
                "default": False,
            }
        ]

        for c_name, cmds in visible_categories.items():
            options.append({
                "label": f"{c_name} ({len(cmds)})",
                "value": c_name.lower(),
                "description": f"View {len(cmds)} accessible {c_name} command(s)",
                "emoji": self._get_category_select_emoji(c_name),
                "default": c_name.lower() == cat_name.lower(),
            })

        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_category",
                "placeholder": "Select an infrastructure module...",
                "options": options,
            }
        ])

        container.add_text(f"-# Type {current_prefix}help <command> for detailed usage")
        return container

    @commands.hybrid_command(
        name="help",
        aliases=["commands", "modules"],
        description="Display the Cicada 3301 Enterprise command directory tailored to your permissions.",
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

                container = CicadaContainer(accent_color=None)
                container.add_text(
                    f"{cat_icon} **Command: {target_cmd.name.capitalize()}**\n\n"
                    f"• **Description:** {desc}\n"
                    f"• **Usage:** {usage}\n"
                    f"• **Aliases:** {aliases}\n"
                    f"• **Module:** `{cat}`"
                )
                container.add_separator(divider=True)
                container.add_text(f"-# Cicada 3301 Enterprise Command Reference")
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
                        # Find matching category
                        matched_cat = next((c for c in visible_categories.keys() if c.lower() == selected), None)
                        if matched_cat:
                            new_container = self._build_category_container(
                                ctx, matched_cat, visible_categories[matched_cat], visible_categories, custom_id_prefix
                            )
                        else:
                            new_container = self._build_home_container(ctx, visible_categories, custom_id_prefix, "home")

                    await edit_container_response(interaction, new_container)

                elif action == "action_trial":
                    # Delegate to buy trial command
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


async def setup(bot: CicadaBot) -> None:
    await bot.add_cog(Help(bot))
