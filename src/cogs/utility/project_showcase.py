"""
Kyro Discord Bot - Community Project Showcase Cog
Interactive showcase hub for server developers to launch projects, collect community upvotes, and receive constructive feedback.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    KyroContainer,
    edit_container_response,
    send_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot

logger = logging.getLogger("Kyro.Utility.ProjectShowcase")


class ProjectSubmitModal(discord.ui.Modal, title="Launch Community Project"):
    """Interactive modal allowing developers to submit their project for community showcase."""

    project_title = discord.ui.TextInput(
        label="Project Name",
        placeholder="e.g. Kyro AI Assistant, DevFolio...",
        max_length=80,
        required=True,
    )
    demo_url = discord.ui.TextInput(
        label="Live Demo or GitHub URL",
        placeholder="https://github.com/... or https://myproject.com",
        max_length=200,
        required=True,
    )
    description = discord.ui.TextInput(
        label="Executive Description / Pitch",
        placeholder="What does it do? Who is it for? Tech stack used...",
        style=discord.TextStyle.paragraph,
        max_length=600,
        required=True,
    )
    image_url = discord.ui.TextInput(
        label="Screenshot / Banner Image URL (Optional)",
        placeholder="https://i.imgur.com/... or leave blank",
        max_length=250,
        required=False,
    )

    def __init__(self, bot: KyroBot) -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                "Projects can only be showcased in server text channels.",
                ephemeral=True,
            )
            return

        clean_url = self.demo_url.value.strip()
        if not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            await interaction.response.send_message(
                "Invalid URL format. Please provide a link starting with http:// or https://",
                ephemeral=True,
            )
            return

        valid_img = self.image_url.value.strip() if self.image_url.value else None
        if valid_img and not (valid_img.startswith("http://") or valid_img.startswith("https://")):
            valid_img = None

        await interaction.response.defer(ephemeral=True)

        try:
            # 1. Store in Database
            insert_query = """
            INSERT INTO community_projects (guild_id, user_id, title, description, demo_url, image_url, channel_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id;
            """
            row = await self.bot.db.fetch_row(
                insert_query,
                interaction.guild.id,
                interaction.user.id,
                self.project_title.value.strip(),
                self.description.value.strip(),
                clean_url,
                valid_img,
                interaction.channel.id,
            )
            project_id = row["id"] if row else 1

            # 2. Build Showcase Components V2 Card
            dot = self.bot.custom_emojis.get("heart_dot", "•")
            container = KyroContainer(accent_color=None)
            
            title_text = f"### [{self.project_title.value.strip()}]({clean_url})"
            sub_text = f"**Community Project Launch** • *Built by {interaction.user.mention}*"
            container.add_section(content=f"{title_text}\n> {sub_text}")
            container.add_separator(divider=True)

            body_elements = [
                f"**About this Creation:**\n{self.description.value.strip()}",
                f"> {dot} *Support indie development by upvoting and dropping your feedback below!*",
            ]
            container.add_text("\n\n".join(body_elements))

            if valid_img:
                container.add_media(valid_img)

            # Action Buttons: Live Demo + Upvote
            container.add_action_row([
                {
                    "type": 2,
                    "style": 5,
                    "label": "Live Demo",
                    "url": clean_url,
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": "Upvote (0)",
                    "custom_id": f"proj_upvote:{project_id}",
                },
            ])

            # 3. Post to Channel
            post_msg = await send_container_response(interaction.channel, container)

            # Save message ID
            if post_msg and hasattr(post_msg, "id"):
                await self.bot.db.execute(
                    "UPDATE community_projects SET message_id = $1 WHERE id = $2;",
                    post_msg.id,
                    project_id,
                )

                # 4. Automatically spawn feedback thread
                try:
                    thread_name = f"Feedback: {self.project_title.value.strip()[:60]}"
                    await post_msg.create_thread(
                        name=thread_name,
                        auto_archive_duration=1440,
                        reason=f"Community Project Showcase Feedback for {self.project_title.value}",
                    )
                except Exception as th_err:
                    logger.debug(f"Notice creating showcase thread: {th_err}")

            await interaction.followup.send(
                "Your project has been launched to the showcase channel!",
                ephemeral=True,
            )

        except Exception as e:
            logger.error(f"Error submitting community project: {e}", exc_info=e)
            await interaction.followup.send(
                "An error occurred while launching your project. Please try again later.",
                ephemeral=True,
            )


class ProjectShowcaseCog(commands.Cog):
    """Community Project Showcase & Upvotes Cog."""

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot

    # -------------------------------------------------------------------------
    # Upvote Listener
    # -------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        """Handle project upvote button clicks."""
        custom_id = (interaction.data or {}).get("custom_id")
        if not custom_id or not isinstance(custom_id, str) or not custom_id.startswith("proj_upvote:"):
            return

        try:
            project_id = int(custom_id.replace("proj_upvote:", ""))
        except ValueError:
            return

        # Check existing upvote
        check_query = "SELECT 1 FROM community_project_upvotes WHERE project_id = $1 AND user_id = $2;"
        existing = await self.bot.db.fetch_val(check_query, project_id, interaction.user.id)

        if existing:
            # Toggle downvote/remove
            await self.bot.db.execute(
                "DELETE FROM community_project_upvotes WHERE project_id = $1 AND user_id = $2;",
                project_id,
                interaction.user.id,
            )
            msg = "Removed your upvote from this project."
        else:
            # Add upvote
            await self.bot.db.execute(
                "INSERT INTO community_project_upvotes (project_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING;",
                project_id,
                interaction.user.id,
            )
            msg = "Upvoted this project! Thank you for supporting community builders."

        # Fetch new upvote count
        count_query = "SELECT COUNT(*) FROM community_project_upvotes WHERE project_id = $1;"
        total_votes = await self.bot.db.fetch_val(count_query, project_id) or 0

        # Update message component if message exists
        proj_row = await self.bot.db.fetch_row(
            "SELECT title, description, demo_url, image_url, user_id FROM community_projects WHERE id = $1;",
            project_id,
        )
        if proj_row and interaction.message:
            dot = self.bot.custom_emojis.get("heart_dot", "•")
            container = KyroContainer(accent_color=None)
            title_text = f"### [{proj_row['title']}]({proj_row['demo_url']})"
            sub_text = f"**Community Project Launch** • *Built by <@{proj_row['user_id']}>*"
            container.add_section(content=f"{title_text}\n> {sub_text}")
            container.add_separator(divider=True)

            body_elements = [
                f"**About this Creation:**\n{proj_row['description']}",
                f"> {dot} *Support indie development by upvoting and dropping your feedback below!*",
            ]
            container.add_text("\n\n".join(body_elements))

            if proj_row.get("image_url"):
                container.add_media(proj_row["image_url"])

            container.add_action_row([
                {
                    "type": 2,
                    "style": 5,
                    "label": "Live Demo",
                    "url": proj_row["demo_url"],
                },
                {
                    "type": 2,
                    "style": 2,
                    "label": f"Upvote ({total_votes})",
                    "custom_id": f"proj_upvote:{project_id}",
                },
            ])
            try:
                await edit_container_response(interaction.message, container)
            except Exception:
                pass

        try:
            await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Commands
    # -------------------------------------------------------------------------
    @commands.hybrid_group(
        name="showcase",
        description="Launch community projects, discover indie builds, and upvote top creations.",
        fallback="help",
    )
    async def showcase_group(self, ctx: CustomContext) -> None:
        """Showcase command help overview."""
        dot = self.bot.custom_emojis.get("heart_dot", "•")
        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Community Project Showcase Hub**\n"
                "> Showcase your apps, bots, and websites to fellow developers in the server!"
            )
        )
        container.add_separator(divider=True)
        container.add_text(
            f"> {dot} **`/showcase submit`** — Open launch modal to post your live project.\n"
            f"> {dot} **`/showcase top`** — View the top most upvoted community projects in the server."
        )
        await send_container_response(ctx, container)

    @showcase_group.command(
        name="submit",
        description="Open the launch modal to submit your project to the showcase channel.",
    )
    async def submit_project(self, ctx: CustomContext) -> None:
        """Submit project modal trigger."""
        if ctx.interaction:
            modal = ProjectSubmitModal(self.bot)
            await ctx.interaction.response.send_modal(modal)
        else:
            await ctx.send("Please use `/showcase submit` to open the interactive project launch form.")

    @showcase_group.command(
        name="top",
        description="View the highest-rated community projects in this server.",
    )
    async def top_projects(self, ctx: CustomContext) -> None:
        """Display top upvoted projects in the current guild."""
        if not ctx.guild:
            await ctx.send("This command can only be used in servers.")
            return

        query = """
        SELECT cp.id, cp.title, cp.demo_url, cp.user_id, COUNT(cpu.user_id) as votes
        FROM community_projects cp
        LEFT JOIN community_project_upvotes cpu ON cp.id = cpu.project_id
        WHERE cp.guild_id = $1
        GROUP BY cp.id, cp.title, cp.demo_url, cp.user_id
        ORDER BY votes DESC, cp.created_at DESC
        LIMIT 5;
        """
        rows = await self.bot.db.fetch_all(query, ctx.guild.id)
        dot = self.bot.custom_emojis.get("heart_dot", "•")

        container = KyroContainer(accent_color=None)
        container.add_section(
            content=(
                "**Community Project Leaderboard — Top Rated**\n"
                "> The most upvoted developer creations in this community:"
            )
        )
        container.add_separator(divider=True)

        if not rows:
            container.add_text("> *No projects have been submitted yet. Be the first with `/showcase submit`!*")
        else:
            lines = []
            for rank, r in enumerate(rows, start=1):
                votes = r.get("votes", 0)
                lines.append(
                    f"**#{rank}** [{r['title']}]({r['demo_url']}) {dot} `{votes} upvotes`\n"
                    f"> *Creator:* <@{r['user_id']}>"
                )
            container.add_text("\n\n".join(lines))

        await send_container_response(ctx, container)


async def setup(bot: KyroBot) -> None:
    """Standard extension loader entrypoint."""
    await bot.add_cog(ProjectShowcaseCog(bot))
