"""
Cicada 3301 Discord Bot - Discord Components V2 (Container Layout) Utility
Implements Discord's new Container (type: 17) layout with embedded TextDisplays,
Sections, Separators, and integrated Action Rows (Dropdowns/Buttons inside the card).
"""

from __future__ import annotations

import logging
from typing import Any
import discord
from discord.ext import commands

from src.core.config import Config

logger = logging.getLogger("Cicada.Containers")


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
        """Add a Section component (type: 9) if accessory is present, otherwise TextDisplay (type: 10)."""
        if not accessory:
            return self.add_text(content)

        section_data: dict[str, Any] = {
            "type": 9,
            "components": [
                {
                    "type": 10,
                    "content": content,
                }
            ],
            "accessory": accessory,
        }
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

    def to_embed(self) -> discord.Embed:
        """Convert container components into a standard discord.Embed for fallback compatibility."""
        if hasattr(self, "_fallback_embed") and self._fallback_embed is not None:
            return self._fallback_embed
        embed = discord.Embed(
            color=self.accent_color if self.accent_color is not None else None,
        )
        for comp in self.components:
            ctype = comp.get("type")
            if ctype == 10:  # TextDisplay
                text = comp.get("content", "")
                if text.startswith("-# "):
                    embed.set_footer(text=text.replace("-# ", "").strip())
                elif not embed.description:
                    embed.description = text
                else:
                    embed.description += f"\n\n{text}"
            elif ctype == 9:  # Section
                sub_comps = comp.get("components", [])
                for sc in sub_comps:
                    text = sc.get("content", "")
                    if not embed.description:
                        embed.description = text
                    else:
                        embed.description += f"\n\n{text}"
                acc = comp.get("accessory", {})
                if acc.get("type") == 11 and "media" in acc:
                    embed.set_thumbnail(url=acc["media"].get("url", ""))
            elif ctype == 12:  # Media Gallery
                items = comp.get("items", [])
                if items and "media" in items[0]:
                    embed.set_image(url=items[0]["media"].get("url", ""))
        return embed

    def build(self) -> discord.Embed:
        """Compatibility method returning a discord.Embed representation."""
        return self.to_embed()

    def to_dict(self) -> dict[str, Any]:
        """Serialize container to Discord API component structure."""
        comps = list(self.components)
        if not comps:
            comps.append({"type": 10, "content": " "})
        data: dict[str, Any] = {
            "type": 17,
            "components": comps,
        }
        if self.accent_color is not None:
            data["accent_color"] = self.accent_color
        return data

def build_container_payload(
    container: CicadaContainer | list[CicadaContainer],
    view: discord.ui.View | None = None,
    content: str | None = None,
) -> dict[str, Any]:
    """Generate the full Discord REST payload supporting single or multiple stacked containers with nested view controls."""
    if isinstance(container, list):
        container_list = container
    else:
        container_list = [container]

    root_comps = []
    for c in container_list:
        c_dict = c.to_dict()
        
        # Extract Action Rows (Type 1) to top-level message components (Discord Components V2 spec)
        inner_comps = []
        extracted_action_rows = []
        for comp in c_dict.get("components", []):
            if comp.get("type") == 1:
                extracted_action_rows.append(comp)
            else:
                inner_comps.append(comp)
        
        if not inner_comps:
            inner_comps.append({"type": 10, "content": " "})
        c_dict["components"] = inner_comps
        
        root_comps.append(c_dict)
        root_comps.extend(extracted_action_rows)

    if view is not None:
        view_comps = view.to_components()
        if view_comps:
            root_comps.extend(view_comps)

    payload: dict[str, Any] = {
        "flags": 32768,  # IS_COMPONENTS_V2 (1 << 15)
        "components": root_comps,
        "allowed_mentions": {"parse": []},
    }
    if content:
        payload["content"] = str(content)
    return payload


async def send_container_response(
    interaction_or_ctx: discord.Interaction | commands.Context | discord.abc.Messageable | discord.User | discord.Member,
    container: CicadaContainer | list[CicadaContainer],
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
    content: str | None = None,
) -> Any:
    """Send or edit a message using Components V2 Container(s)."""
    # 1. Resolve hybrid context interaction if present
    interaction = getattr(interaction_or_ctx, "interaction", None)
    if interaction is not None:
        target = interaction
    else:
        target = interaction_or_ctx

    payload = build_container_payload(container, view=view, content=content)

    if isinstance(target, discord.Interaction):
        interaction = target
        bot = getattr(interaction, "client", getattr(interaction, "bot", None))
        app_id = getattr(bot, "application_id", None) or (bot.user.id if bot and bot.user else None)
        if ephemeral:
            payload["flags"] |= 64  # EPHEMERAL

        if interaction.response.is_done():
            msg_data = await bot.http.request(
                discord.http.Route(
                    "POST",
                    f"/webhooks/{app_id}/{interaction.token}",
                ),
                json=payload,
            )
            if view and hasattr(bot, "_connection"):
                msg_id = int(msg_data["id"]) if isinstance(msg_data, dict) and "id" in msg_data else None
                bot._connection.store_view(view, msg_id)
            return msg_data
        else:
            # Send initial response via raw interaction callback
            res = await bot.http.request(
                discord.http.Route(
                    "POST",
                    f"/interactions/{interaction.id}/{interaction.token}/callback",
                ),
                json={"type": 4, "data": payload},
            )
            if view and hasattr(bot, "_connection"):
                bot._connection.store_view(view)
            return res
    else:
        obj = target

        # Handle User / Member DMs
        if isinstance(obj, (discord.User, discord.Member)):
            dm = await obj.create_dm()
            channel_id = dm.id
            bot_instance = getattr(obj, "_state", None)
            http_client = getattr(bot_instance, "http", None)
        elif isinstance(obj, discord.abc.GuildChannel) or (isinstance(obj, discord.abc.Messageable) and hasattr(obj, "id") and not hasattr(obj, "channel")):
            channel_id = obj.id
            bot_instance = getattr(obj, "bot", getattr(obj, "_state", None))
            http_client = getattr(bot_instance, "http", None) or getattr(getattr(obj, "_state", None), "http", None)
        elif hasattr(obj, "channel"):
            channel_id = obj.channel.id
            bot_instance = getattr(obj, "bot", getattr(obj, "_state", None))
            http_client = getattr(bot_instance, "http", None) or getattr(getattr(obj, "_state", None), "http", None)
        else:
            channel_id = int(obj)
            bot_instance = getattr(obj, "bot", getattr(obj, "_state", None))
            http_client = getattr(bot_instance, "http", None) or getattr(getattr(obj, "_state", None), "http", None)

        try:
            msg_data = await http_client.request(
                discord.http.Route("POST", f"/channels/{channel_id}/messages"),
                json=payload,
            )
            if view and msg_data and isinstance(msg_data, dict) and "id" in msg_data:
                if hasattr(bot_instance, "_connection"):
                    bot_instance._connection.store_view(view, int(msg_data["id"]))
            return msg_data
        except discord.Forbidden:
            raise
        except Exception as e:
            logger.warning(f"Raw Components V2 HTTP request failed ({e}), attempting standard send fallback...")
            if hasattr(obj, "send"):
                primary = container if isinstance(container, CicadaContainer) else container[0]
                return await obj.send(content=content, embed=primary.to_embed(), view=view)
            raise


async def edit_container_response(
    interaction: discord.Interaction,
    container: CicadaContainer | list[CicadaContainer],
    view: discord.ui.View | None = None,
) -> None:
    """Edit an existing Components V2 Container message safely with fallbacks."""
    bot = interaction.client
    app_id = getattr(bot, "application_id", None) or (bot.user.id if bot and bot.user else None)
    payload = build_container_payload(container, view=view)

    try:
        if interaction.response.is_done():
            await bot.http.request(
                discord.http.Route(
                    "PATCH",
                    f"/webhooks/{app_id}/{interaction.token}/messages/@original",
                ),
                json=payload,
            )
            if view and hasattr(bot, "_connection"):
                msg_id = None
                if msg_data and isinstance(msg_data, dict) and "id" in msg_data:
                    msg_id = int(msg_data["id"])
                elif interaction.message:
                    msg_id = interaction.message.id
                bot._connection.store_view(view, msg_id)
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
            if view and hasattr(bot, "_connection"):
                bot._connection.store_view(view, interaction.message.id)
    except Exception as e2:
        import logging
        logging.getLogger("Cicada.Containers").error(f"Fallback channel message edit also failed: {e2}")


