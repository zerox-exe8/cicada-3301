"""
Kyro Discord Bot - HTML Transcript Generator
Generates clean, responsive, dark-mode Discord chat transcripts in HTML format.
"""

from __future__ import annotations

import html
import io
from typing import Any
import discord


async def generate_html_transcript(
    channel: discord.TextChannel | discord.Thread,
    ticket_data: dict[str, Any] | None = None,
    bot: discord.Client | None = None,
) -> discord.File:
    """Fetch history from a ticket channel and generate a self-contained HTML transcript."""
    messages: list[discord.Message] = []
    async for msg in channel.history(limit=500, oldest_first=True):
        messages.append(msg)

    guild_name = html.escape(channel.guild.name if channel.guild else "Discord Server")
    channel_name = html.escape(channel.name)
    ticket_num = ticket_data.get("ticket_number", channel.id) if ticket_data else channel.id
    user_id = ticket_data.get("user_id", "Unknown") if ticket_data else "Unknown"
    created_at = ticket_data.get("created_at", "") if ticket_data else ""

    messages_html = []
    for msg in messages:
        author_name = html.escape(msg.author.display_name)
        username = html.escape(msg.author.name)
        avatar_url = str(msg.author.display_avatar.url)
        timestamp = msg.created_at.strftime("%b %d, %Y • %I:%M %p UTC")
        bot_badge = '<span class="badge">BOT</span>' if msg.author.bot else ""

        # Content formatting
        content_escaped = html.escape(msg.content or "")
        content_formatted = content_escaped.replace("\n", "<br>")

        # Attachments
        attachments_html = []
        for att in msg.attachments:
            att_url = att.url
            att_name = html.escape(att.filename)
            if att.content_type and att.content_type.startswith("image/"):
                attachments_html.append(
                    f'<div class="attachment image"><a href="{att_url}" target="_blank">'
                    f'<img src="{att_url}" alt="{att_name}" loading="lazy"/></a></div>'
                )
            else:
                attachments_html.append(
                    f'<div class="attachment file"><a href="{att_url}" target="_blank">📎 {att_name}</a></div>'
                )

        # Embeds representation
        embeds_html = []
        for emb in msg.embeds:
            e_title = f'<div class="embed-title">{html.escape(emb.title)}</div>' if emb.title else ""
            e_desc = f'<div class="embed-desc">{html.escape(emb.description or "").replace(chr(10), "<br>")}</div>' if emb.description else ""
            embeds_html.append(f'<div class="embed">{e_title}{e_desc}</div>')

        msg_block = f"""
        <div class="message-row">
            <img class="avatar" src="{avatar_url}" alt="{author_name}" />
            <div class="message-body">
                <div class="message-header">
                    <span class="author-name">{author_name}</span>
                    {bot_badge}
                    <span class="author-user">@{username}</span>
                    <span class="timestamp">{timestamp}</span>
                </div>
                <div class="message-content">{content_formatted}</div>
                {''.join(attachments_html)}
                {''.join(embeds_html)}
            </div>
        </div>
        """
        messages_html.append(msg_block)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcript #{ticket_num} - {channel_name}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #1a1b1e;
            color: #dbdee1;
            padding: 24px;
            display: flex;
            justify-content: center;
        }}
        .container {{
            max-width: 900px;
            width: 100%;
            background-color: #232428;
            border-radius: 12px;
            border: 1px solid #2b2d31;
            overflow: hidden;
            box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }}
        .header {{
            background: linear-gradient(135deg, #18191c 0%, #2b2d31 100%);
            padding: 24px 32px;
            border-bottom: 1px solid #313338;
        }}
        .header h1 {{
            color: #ffffff;
            font-size: 20px;
            font-weight: 700;
            margin-bottom: 6px;
        }}
        .header-meta {{
            font-size: 13px;
            color: #949ba4;
            display: flex;
            gap: 16px;
            flex-wrap: wrap;
        }}
        .header-meta span {{ display: inline-flex; align-items: center; }}
        .chat-log {{
            padding: 24px 32px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        .message-row {{
            display: flex;
            gap: 16px;
            align-items: flex-start;
        }}
        .message-row:hover {{
            background-color: rgba(255,255,255,0.015);
        }}
        .avatar {{
            width: 40px;
            height: 40px;
            border-radius: 50%;
            object-fit: cover;
            flex-shrink: 0;
        }}
        .message-body {{
            flex: 1;
            min-width: 0;
        }}
        .message-header {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }}
        .author-name {{
            font-size: 15px;
            font-weight: 600;
            color: #f2f3f5;
        }}
        .author-user {{
            font-size: 12px;
            color: #949ba4;
        }}
        .timestamp {{
            font-size: 11px;
            color: #80848e;
            margin-left: 4px;
        }}
        .badge {{
            background-color: #5865f2;
            color: #ffffff;
            font-size: 10px;
            font-weight: 700;
            padding: 1px 4px;
            border-radius: 4px;
        }}
        .message-content {{
            font-size: 14px;
            line-height: 1.45;
            color: #dbdee1;
            word-break: break-word;
        }}
        .attachment.image img {{
            max-width: 100%;
            max-height: 350px;
            border-radius: 8px;
            margin-top: 8px;
            border: 1px solid #313338;
        }}
        .attachment.file a {{
            display: inline-block;
            margin-top: 6px;
            color: #00a8fc;
            text-decoration: none;
            background: #2b2d31;
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 13px;
        }}
        .attachment.file a:hover {{
            text-decoration: underline;
        }}
        .embed {{
            margin-top: 8px;
            padding: 12px 16px;
            background-color: #2b2d31;
            border-left: 4px solid #5865f2;
            border-radius: 4px;
            max-width: 520px;
        }}
        .embed-title {{
            font-weight: 600;
            color: #ffffff;
            margin-bottom: 4px;
        }}
        .embed-desc {{
            font-size: 13px;
            color: #dbdee1;
        }}
        .footer {{
            padding: 16px 32px;
            background-color: #1e1f22;
            border-top: 1px solid #2b2d31;
            font-size: 12px;
            color: #80848e;
            display: flex;
            justify-content: space-between;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Ticket #{ticket_num} • #{channel_name}</h1>
            <div class="header-meta">
                <span>Server: <strong>{guild_name}</strong></span>
                <span>User ID: <strong>{user_id}</strong></span>
                <span>Messages: <strong>{len(messages)}</strong></span>
            </div>
        </div>
        <div class="chat-log">
            {''.join(messages_html) if messages_html else '<p style="color:#80848e;">No messages recorded in this ticket.</p>'}
        </div>
        <div class="footer">
            <span>Generated by Kyro Ticket Engine</span>
            <span>{channel.guild.name if channel.guild else ''}</span>
        </div>
    </div>
</body>
</html>
"""

    file_bytes = io.BytesIO(full_html.encode("utf-8"))
    return discord.File(file_bytes, filename=f"transcript-ticket-{ticket_num}.html")
