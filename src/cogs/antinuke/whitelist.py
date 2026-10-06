from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Union
import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import KyroContainer, send_container_response, edit_container_response
from src.managers.antinuke_manager import PROTECTION_MODULES

if TYPE_CHECKING:
    from src.core.bot import KyroBot


MODULE_LABELS: dict[str, str] = {
    "vanity": "Vanity URL",
    "everyone": "Everyone Guard",
    "role": "Roles",
    "channel": "Channels",
    "ban": "Bans",
    "kick": "Kicks",
    "bot": "Bot Adds",
    "webhook": "Webhooks",
    "prune": "Prunes",
    "automod": "AutoMod",
    "integration": "Integrations",
    "emoji": "Emojis",
    "guild_update": "Server Updates",
}


class AntinukeWhitelistCog(commands.Cog):
    """Whitelist management for Kyro Antinuke."""
    category: str = "Security"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    def _build_usage_card(self, ctx: CustomContext) -> KyroContainer:
        """Construct the Components V2 usage guide for whitelist commands (same style as role)."""
        prefix = self.bot.guild_mgr.get_prefix(ctx.guild.id if ctx.guild else None)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Whitelist Commands**")
        container.add_separator(divider=True)
        container.add_text(
            f"{dot} `{prefix}whitelist add <@user / bot / role>`\n"
            f"{dot} `{prefix}whitelist remove <@user / bot / role>`\n"
            f"{dot} `{prefix}whitelist list/show`"
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    @commands.hybrid_group(
        name="whitelist",
        aliases=["wl"],
        description="Manage users or bots immune to antinuke triggers.",
        invoke_without_command=True,
    )
    @commands.guild_only()
    async def whitelist(self, ctx: CustomContext) -> None:
        """Show Whitelist usage guide (same style as role command)."""
        if ctx.invoked_subcommand is not None:
            return

        container = self._build_usage_card(ctx)
        await send_container_response(ctx, container)

    def _build_setup_container(
        self,
        ctx: CustomContext,
        target_label: str,
        custom_id_prefix: str,
    ) -> KyroContainer:
        """Interactive whitelist setup card with two dropdowns (type + modules)."""
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                f"**Whitelist Setup**\n"
                f"> {target_label}"
            )
        )
        container.add_separator(divider=True)
        container.add_text(f"{dot} Step 1 — pick **Full Whitelist**, or pick **Custom Modules** then choose modules below.")
        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_mode",
                "placeholder": "Choose whitelist type...",
                "options": [
                    {
                        "label": "Full Whitelist",
                        "value": "full",
                        "description": "Immune to every antinuke module",
                    },
                    {
                        "label": "Custom Modules",
                        "value": "custom",
                        "description": "Immune only to modules picked below",
                    },
                ],
            }
        ])
        container.add_action_row([
            {
                "type": 3,
                "custom_id": f"{custom_id_prefix}:select_modules",
                "placeholder": "Choose modules (multi-select)...",
                "min_values": 1,
                "max_values": len(PROTECTION_MODULES),
                "options": [
                    {
                        "label": MODULE_LABELS.get(m, m.replace("_", " ").title()),
                        "value": m,
                    }
                    for m in PROTECTION_MODULES
                ],
            }
        ])
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    def _build_applied_container(
        self,
        ctx: CustomContext,
        target_label: str,
        tier: str,
    ) -> KyroContainer:
        """Success card after a whitelist entry is applied."""
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Whitelist**")
        container.add_separator(divider=True)
        container.add_text(f"{dot} **Target:** {target_label}\n{dot} **Access:** {tier}")
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        return container

    async def _run_interactive_setup(
        self,
        ctx: CustomContext,
        target: discord.Member | discord.User | discord.Role,
        is_role: bool,
        target_label: str,
    ) -> None:
        """Two-dropdown interactive flow: whitelist type + module multi-select."""
        custom_id_prefix = f"wl_setup:{ctx.author.id}:{ctx.guild.id if ctx.guild else 0}:{ctx.message.id if ctx.message else 0}"
        await send_container_response(
            ctx, self._build_setup_container(ctx, target_label, custom_id_prefix)
        )

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
                data: dict[str, Any] = interaction.data or {}
                action = (data.get("custom_id", "").split(":")[-1])
                values: list[str] = data.get("values", [])

                if action == "select_mode" and values and values[0] == "full":
                    if is_role:
                        await self.bot.antinuke_mgr.add_role_whitelist(
                            ctx.guild.id, target.id, ctx.author.id, is_full=True, scope=""
                        )
                    else:
                        await self.bot.antinuke_mgr.add_whitelist(
                            ctx.guild.id, target.id, ctx.author.id, is_full=True, scope=""
                        )
                    await edit_container_response(
                        interaction,
                        self._build_applied_container(ctx, target_label, "`[Full Whitelist]`"),
                    )
                    break
                elif action == "select_modules" and values:
                    picked = [v for v in values if v in PROTECTION_MODULES]
                    if not picked:
                        continue
                    scope_str = ",".join(picked)
                    if is_role:
                        await self.bot.antinuke_mgr.add_role_whitelist(
                            ctx.guild.id, target.id, ctx.author.id, is_full=False, scope=scope_str
                        )
                    else:
                        await self.bot.antinuke_mgr.add_whitelist(
                            ctx.guild.id, target.id, ctx.author.id, is_full=False, scope=scope_str
                        )
                    await edit_container_response(
                        interaction,
                        self._build_applied_container(ctx, target_label, f"`[Scoped: {scope_str}]`"),
                    )
                    break
                else:
                    # "Custom Modules" picked — ack with same card so user can now pick modules.
                    await edit_container_response(
                        interaction,
                        self._build_setup_container(ctx, target_label, custom_id_prefix),
                    )

            except asyncio.TimeoutError:
                break

    @whitelist.command(name="add", description="Add a user, bot or role to the antinuke whitelist.")
    @app_commands.describe(
        target="User, bot, role or their ID to whitelist",
        scope="Do not type here — pick type and modules from the dropdowns.",
    )
    async def whitelist_add(
        self,
        ctx: CustomContext,
        target: Union[discord.Member, discord.User, discord.Role],
        scope: Optional[str] = None,
    ) -> None:
        """Add user/bot/role to whitelist."""
        is_owner = ctx.author.id == ctx.guild.owner_id
        is_eo = self.bot.antinuke_mgr.is_extra_owner(ctx.guild.id, ctx.author.id)
        if not (is_owner or is_eo):
            await ctx.send_error("Only the **Server Owner** or **Extra Owners** can manage the whitelist.")
            return

        is_role = isinstance(target, discord.Role)
        if is_role:
            target_label = f"{target.mention} `「{target.id}」`"
        else:
            target_label = f"**{target.name}** `「{target.id}」`"

        if is_role and target.is_default():
            await ctx.send_error("The `@everyone` role cannot be whitelisted — that would disable Antinuke for the whole server.")
            return

        scope_text = (scope or "").strip()
        if scope_text:
            # Typed scopes are disabled — everything goes through the dropdowns.
            await ctx.send_error("Type karke scope mat likho — `scope` khaali chhod ke dobara chalao, dropdown se select karo.")
            return

        # Everything goes through the interactive two-dropdown setup.
        await self._run_interactive_setup(ctx, target, is_role, target_label)

    @whitelist.command(name="remove", description="Remove a user, bot or role from the antinuke whitelist.")
    @app_commands.describe(target="User, bot or role to remove from whitelist")
    async def whitelist_remove(self, ctx: CustomContext, target: Union[discord.Member, discord.User, discord.Role]) -> None:
        """Remove user/bot/role from whitelist."""
        is_owner = ctx.author.id == ctx.guild.owner_id
        is_eo = self.bot.antinuke_mgr.is_extra_owner(ctx.guild.id, ctx.author.id)
        if not (is_owner or is_eo):
            await ctx.send_error("Only the **Server Owner** or **Extra Owners** can manage the whitelist.")
            return

        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        if isinstance(target, discord.Role):
            curr_role_wl = self.bot.antinuke_mgr.get_role_whitelist(ctx.guild.id)
            if target.id not in curr_role_wl:
                await ctx.send_error(f"{target.mention} is not in the whitelist.")
                return

            await self.bot.antinuke_mgr.remove_role_whitelist(ctx.guild.id, target.id)

            container = KyroContainer(accent_color=None)
            container.add_section(content="**Antinuke Whitelist Removed**")
            container.add_separator(divider=True)
            container.add_text(f"{dot} **Target:** {target.mention} `「{target.id}」` has been removed.")
            await send_container_response(ctx, container)
            return

        curr_wl = self.bot.antinuke_mgr.get_whitelist(ctx.guild.id)
        if target.id not in curr_wl:
            await ctx.send_error(f"**{target.name}** is not in the whitelist.")
            return

        await self.bot.antinuke_mgr.remove_whitelist(ctx.guild.id, target.id)

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Whitelist Removed**")
        container.add_separator(divider=True)
        container.add_text(f"{dot} **Target:** **{target.name}** `「{target.id}」` has been removed.")
        await send_container_response(ctx, container)

    @whitelist.command(name="list", aliases=["show"], description="List all whitelisted users, bots and roles.")
    async def whitelist_list(self, ctx: CustomContext) -> None:
        """Display all whitelisted members, bots and roles."""
        wl_dict = self.bot.antinuke_mgr.get_whitelist(ctx.guild.id)
        role_wl_dict = self.bot.antinuke_mgr.get_role_whitelist(ctx.guild.id)
        e_reg = self.bot.custom_emojis
        dot = e_reg.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(content="**Antinuke Whitelist**")
        container.add_separator(divider=True)

        # Extra Owners live in the same registry but have their own list command —
        # hide them here so the whitelist view stays clean (immunity unaffected).
        lines = []
        for uid, data in wl_dict.items():
            if data.get("is_extra_owner"):
                continue
            u = self.bot.get_user(uid)
            u_name = f"**{u.name}**" if u else f"<@{uid}>"

            if data.get("is_full"):
                lines.append(f"{dot} {u_name} `「{uid}」` **—** `[Full Whitelist]`")
            else:
                scopes = ", ".join(data.get("scope", set()))
                lines.append(f"{dot} {u_name} `「{uid}」` **—** `[Scoped: {scopes}]`")

        role_lines = []
        for rid, data in role_wl_dict.items():
            role = ctx.guild.get_role(rid) if ctx.guild else None
            r_name = role.mention if role else f"<@&{rid}>"
            if data.get("is_full"):
                role_lines.append(f"{dot} {r_name} `「{rid}」` **—** `[Full Whitelist]`")
            else:
                scopes = ", ".join(data.get("scope", set()))
                role_lines.append(f"{dot} {r_name} `「{rid}」` **—** `[Scoped: {scopes}]`")

        if not lines and not role_lines:
            container.add_text(f"{dot} No entities currently whitelisted.")
            container.add_separator(divider=True)
            container.add_text(f"-# Requested by {ctx.author.display_name}")
            await send_container_response(ctx, container)
            return

        if lines:
            container.add_text("\n".join(lines[:25]))
        if role_lines:
            if lines:
                container.add_separator(divider=True)
            container.add_text("**Whitelisted Roles**")
            container.add_text("\n".join(role_lines[:25]))
        container.add_separator(divider=True)
        container.add_text(f"-# Requested by {ctx.author.display_name}")
        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Load AntinukeWhitelistCog."""
    await bot.add_cog(AntinukeWhitelistCog(bot))
