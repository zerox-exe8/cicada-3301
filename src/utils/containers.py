"""
Cicada 3301 Discord Bot - Discord Components V2 (Container Layout) Utility
Implements Discord's new Container (type: 17) layout with embedded TextDisplays,
Sections, Separators, and integrated Action Rows (Dropdowns/Buttons inside the card).
"""

from __future__ import annotations

from typing import Any
import discord
from discord.ext import commands

from src.core.config import Config


class CicadaContainer:
    """Builder for Discord Components V2 Container cards."""

    def __init__(self, accent_color: int | None = None) -> None:
        self.accent_color = accent_color
        self.components: list[dict[str, Any]] = []

    def add_text(self, content: str) -> CicadaContainer:
        """Add a TextDisplay component (type: 10) inside the container."""
        self.components.append({
            "type": 10,
            "content": content,
        })
        return self

    def add_section(
        self,
        content: str,
        accessory: dict[str, Any] | None = None,
    ) -> CicadaContainer:
        """Add a Section component (type: 9) with optional accessory (Button/Thumbnail)."""
        section_data: dict[str, Any] = {
            "type": 9,
            "components": [
                {
                    "type": 10,
                    "content": content,
                }
            ],
        }
        if accessory:
            section_data["accessory"] = accessory
        self.components.append(section_data)
        return self

    def add_separator(self, divider: bool = True) -> CicadaContainer:
        """Add a visual Separator component (type: 14)."""
        self.components.append({
            "type": 14,
            "divider": divider,
        })
        return self

    def add_footer(self, text: str, icon_url: str | None = None) -> CicadaContainer:
        """Add a subtle subtext footer."""
        self.add_text(f"-# {text}")
        return self

    def add_action_row(self, items: list[dict[str, Any]]) -> CicadaContainer:
        """Add an Action Row (type: 1) containing Select Menus or Buttons inside the container."""
        self.components.append({
            "type": 1,
            "components": items,
        })
        return self

    def to_dict(self) -> dict[str, Any]:
        """Serialize container to Discord API component structure."""
        data: dict[str, Any] = {
            "type": 17,
            "components": self.components,
        }
        if self.accent_color is not None:
            data["accent_color"] = self.accent_color
        return data

    def to_payload(self) -> dict[str, Any]:
        """Generate the full Discord REST payload with IS_COMPONENTS_V2 flag and no mentions."""
        return {
            "flags": 32768,  # IS_COMPONENTS_V2 (1 << 15)
            "components": [self.to_dict()],
            "allowed_mentions": {"parse": []},
        }


async def send_container_response(
    interaction_or_ctx: discord.Interaction | commands.Context | discord.abc.Messageable,
    container: CicadaContainer,
    ephemeral: bool = False,
) -> Any:
    """Send or edit a message using Components V2 Container."""
    # 1. Resolve hybrid context interaction if present
    interaction = getattr(interaction_or_ctx, "interaction", None)
    if interaction is not None:
        target = interaction
    else:
        target = interaction_or_ctx

    if isinstance(target, discord.Interaction):
        interaction = target
        bot = getattr(interaction, "client", getattr(interaction, "bot", None))
        payload = container.to_payload()
        if ephemeral:
            payload["flags"] |= 64  # EPHEMERAL

        if interaction.response.is_done():
            return await interaction.followup.send(**payload)
        else:
            # Send initial response via raw interaction callback
            await bot.http.request(
                discord.http.Route(
                    "POST",
                    f"/interactions/{interaction.id}/{interaction.token}/callback",
                ),
                json={"type": 4, "data": payload},
            )
            return None
    else:
        # commands.Context, discord.Message, or discord.TextChannel
        obj = target
        payload = container.to_payload()

        if isinstance(obj, discord.abc.GuildChannel) or isinstance(obj, discord.abc.Messageable) and hasattr(obj, "id") and not hasattr(obj, "channel"):
            channel_id = obj.id
        elif hasattr(obj, "channel"):
            channel_id = obj.channel.id
        else:
            channel_id = int(obj)

        bot_instance = getattr(obj, "bot", getattr(obj, "_state", None))
        http_client = getattr(bot_instance, "http", None) or getattr(getattr(obj, "_state", None), "http", None)
        
        return await http_client.request(
            discord.http.Route("POST", f"/channels/{channel_id}/messages"),
            json=payload,
        )


async def edit_container_response(
    interaction: discord.Interaction,
    container: CicadaContainer,
) -> None:
    """Edit an existing Components V2 Container message safely with fallbacks."""
    bot = interaction.client
    payload = container.to_payload()

    # 1. Try interaction response callback first
    try:
        if not interaction.response.is_done():
            await bot.http.request(
                discord.http.Route(
                    "POST",
                    f"/interactions/{interaction.id}/{interaction.token}/callback",
                ),
                json={"type": 7, "data": payload},  # 7 = UPDATE_MESSAGE
            )
            return
        else:
            await bot.http.request(
                discord.http.Route(
                    "PATCH",
                    f"/webhooks/{bot.user.id}/{interaction.token}/messages/@original",
                ),
                json=payload,
            )
            return
    except Exception as e:
        import logging
        logging.getLogger("Cicada.Containers").warning(f"Interaction callback edit failed ({e}). Attempting channel PATCH fallback.")

    # 2. Fallback to direct channel message edit if interaction expired
    try:
        if interaction.message and interaction.channel_id:
            await bot.http.request(
                discord.http.Route(
                    "PATCH",
                    f"/channels/{interaction.channel_id}/messages/{interaction.message.id}",
                ),
                json=payload,
            )
    except Exception as e2:
        import logging
        logging.getLogger("Cicada.Containers").error(f"Fallback channel message edit also failed: {e2}")
