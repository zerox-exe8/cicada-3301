"""
Kyro Discord Bot - Ultra-Realistic Discord Account Security Breach Simulation
Produces a sleek, authentic-looking Discord security alert displaying realistic
compromised session data (real user ID base64 token prefix, realistic ISP, masked email,
device telemetry) without bloated meme walls or cartoonish fake text.
"""

from __future__ import annotations

import asyncio
import base64
import random
from typing import TYPE_CHECKING
import discord
from discord.ext import commands

from src.core.context import CustomContext
from src.utils.containers import (
    KyroContainer,
    send_container_response,
    edit_container_response,
)

if TYPE_CHECKING:
    from src.core.bot import KyroBot


class HackActionView(discord.ui.View):
    """Persistent security action buttons for compromised session card."""

    def __init__(self, incident_id: str = "SEC-849201") -> None:
        super().__init__(timeout=None)
        self.incident_id = incident_id

    @discord.ui.button(
        label="Revoke Session",
        style=discord.ButtonStyle.danger,
        custom_id="hack:revoke_session",
    )
    async def revoke_session(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Deliver clean, reassuring simulation notice when clicked."""
        resp = KyroContainer(accent_color=0x2B2D31)
        resp.add_section(
            content=(
                "**Session Revocation Status**\n"
                "> Target Session: `TERMINATED (SIMULATION)`\n"
                "> Status: **Account Safe & Secure**\n\n"
                "> Relax! This was a simulated security test by Kyro. "
                "No actual tokens, passwords, or credentials were accessed or compromised."
            )
        )
        resp.add_separator(divider=True)
        resp.add_text("-# Kyro Security Labs • Safe Demonstration")
        await send_container_response(interaction, resp, ephemeral=True)

    @discord.ui.button(
        label="Security Report",
        style=discord.ButtonStyle.secondary,
        custom_id="hack:security_report",
    )
    async def security_report(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        """Display verification audit report."""
        resp = KyroContainer(accent_color=0x5865F2)
        resp.add_section(
            content=(
                "**Security Incident Verification**\n"
                "> Classification: **Entertainment Simulation**\n"
                "> Discord API Integrity: **100% Intact**\n"
                "> All displayed IPs, emails, and session hashes were synthetically generated."
            )
        )
        resp.add_separator(divider=True)
        resp.add_text("-# Kyro Security Labs • Safe Demonstration")
        await send_container_response(interaction, resp, ephemeral=True)


class HackCog(commands.Cog, name="Games-Hack"):
    """Hyper-realistic, sleek account penetration simulation suite."""
    category: str = "Games"

    def __init__(self, bot: KyroBot) -> None:
        self.bot = bot
        self.bot.add_view(HackActionView())

    @commands.hybrid_command(
        name="hack",
        aliases=["fakehack", "breach"],
        description="Simulate an authentic-looking Discord session compromise on a member.",
    )
    @commands.guild_only()
    async def fake_hack(self, ctx: CustomContext, member: discord.Member) -> None:
        """Deploy a compact, terrifyingly believable Discord security breach card."""
        # Bot defense
        if member.id == self.bot.user.id:
            shield = KyroContainer(accent_color=0x2B2D31)
            shield.add_section(
                content=(
                    "**Security Intercept: Bot Protection Active**\n"
                    f"> Access attempt from {ctx.author.mention} was deflected.\n"
                    "> Kyro application credentials cannot be probed via user gateway."
                ),
                accessory={"type": 11, "media": {"url": self.bot.user.display_avatar.url}},
            )
            shield.add_separator(divider=True)
            shield.add_text("-# Kyro Shield • Automated Gateway Defense")
            await send_container_response(ctx, shield)
            return

        # 1. Authentic User Token Prefix (Real base64 ID matching real Discord tokens)
        b64_uid = base64.b64encode(str(member.id).encode()).decode().rstrip("=")
        time_chars = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_", k=6))
        realistic_token = f"{b64_uid}.{time_chars}.***************************"

        # 2. Believable Masked Email
        clean_name = "".join(c for c in member.name.lower() if c.isalnum()) or "user"
        if len(clean_name) >= 2:
            masked_email = f"{clean_name[0]}***{clean_name[-1]}@gmail.com"
        else:
            masked_email = f"{clean_name}***@gmail.com"

        # 3. Authentic Platform / Client Telemetry
        if member.is_on_mobile():
            device_str = "Discord Mobile (Android 14 / ARM64)"
        elif member.desktop_status != discord.Status.offline:
            device_str = "Discord Desktop Client (Windows NT 10.0 x64)"
        elif member.web_status != discord.Status.offline:
            device_str = "Chrome Web Client (Windows NT 10.0)"
        else:
            device_str = "Discord Client (Windows NT 10.0 / x64)"

        # 4. Realistic Regional Network Node & IP
        networks = [
            ("103.152.112." + str(random.randint(20, 240)), "Mumbai, MH, India", "Reliance Jio Infocomm Ltd (AS55836)"),
            ("182.79.148." + str(random.randint(20, 240)), "New Delhi, DL, India", "Bharti Airtel Limited (AS45609)"),
            ("115.114.88." + str(random.randint(20, 240)), "Bengaluru, KA, India", "Tata Communications Ltd (AS4755)"),
            ("49.207.134." + str(random.randint(20, 240)), "Hyderabad, TS, India", "ACT Fibernet Broadband (AS133982)"),
        ]
        fake_ip, fake_loc, fake_isp = random.choice(networks)
        incident_id = f"SEC-{random.randint(100000, 999999)}"
        avatar_url = member.display_avatar.url

        # Sleek, compact animation phases (no bloated walls of text)
        phases = [
            {
                "bar": "[████░░░░░░░░░░░░] 25%",
                "status": f"Resolving gateway route for `{member.name}`...",
                "detail": f"Targeting Gateway Node: `{fake_ip}`",
            },
            {
                "bar": "[████████░░░░░░░░] 50%",
                "status": "Intercepting Discord authorization handshake...",
                "detail": f"Session Token Prefix: `{b64_uid[:16]}...`",
            },
            {
                "bar": "[████████████░░░░] 75%",
                "status": "Dumping client telemetry & device profile...",
                "detail": f"Client Build: `{device_str}`",
            },
            {
                "bar": "[██████████████░░] 90%",
                "status": "Decrypting network node & regional ISP...",
                "detail": f"Routing ISP: `{fake_isp.split('(')[0].strip()}`",
            },
        ]

        # Phase 1 Display
        p0 = phases[0]
        container = KyroContainer(accent_color=0xED4245)
        container.add_section(
            content=(
                f"**Security Scan in Progress: `{member.display_name}`**\n"
                f"> {p0['status']}\n"
                f"> `{p0['bar']}` • {p0['detail']}"
            ),
            accessory={"type": 11, "media": {"url": avatar_url}},
        )
        container.add_separator(divider=True)
        container.add_text(f"-# Incident Tracking: #{incident_id} • Gateway v10")

        msg = await send_container_response(ctx, container)

        # Loop through remaining phases
        for p in phases[1:]:
            await asyncio.sleep(1.3)
            step_c = KyroContainer(accent_color=0xED4245)
            step_c.add_section(
                content=(
                    f"**Security Scan in Progress: `{member.display_name}`**\n"
                    f"> {p['status']}\n"
                    f"> `{p['bar']}` • {p['detail']}"
                ),
                accessory={"type": 11, "media": {"url": avatar_url}},
            )
            step_c.add_separator(divider=True)
            step_c.add_text(f"-# Incident Tracking: #{incident_id} • Gateway v10")
            try:
                await edit_container_response(msg, step_c)
            except discord.HTTPException:
                break

        # Final Breach Card: Sleek, compact, terrifyingly believable
        await asyncio.sleep(1.4)
        final_container = KyroContainer(accent_color=0xED4245)
        final_container.add_section(
            content=(
                "**Discord Security Alert: Unauthorized Session Compromise**\n"
                f"> A session dump for {member.mention} was intercepted on Gateway v10."
            ),
            accessory={"type": 11, "media": {"url": avatar_url}},
        )
        final_container.add_separator(divider=True)

        dossier = (
            f"**Account:** {member.mention} (`{member.name}`)\n"
            f"**User ID:** `{member.id}`\n"
            f"**Session Token:** `{realistic_token}`\n"
            f"**Registered Email:** `{masked_email}`\n"
            f"**Session Platform:** `{device_str}`\n"
            f"**Network IP:** `{fake_ip}` (`{fake_loc}`)\n"
            f"**Network Gateway:** `{fake_isp}`"
        )
        final_container.add_text(dossier)
        final_container.add_separator(divider=True)
        final_container.add_text(f"-# Discord System Audit • Incident ID: #{incident_id}")

        view = HackActionView(incident_id=incident_id)
        try:
            await edit_container_response(msg, final_container, view=view)
        except discord.HTTPException:
            pass


async def setup(bot: KyroBot) -> None:
    bot.add_view(HackActionView())
    await bot.add_cog(HackCog(bot))
